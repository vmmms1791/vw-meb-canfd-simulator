#!/usr/bin/env python3
"""
Offline CAN Capture Analyzer for VW MEB Bus Monitor

Loads CSV/JSONL captures, filters by CAN ID, decodes UDS (ISO-TP reassembly),
and provides bus statistics.
"""

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.progress import track

console = Console()


class ISO15765Decoder:
    """ISO 15765-2 (ISO-TP) decoder for UDS over CAN FD."""

    def __init__(self):
        self.sessions: Dict[int, dict] = {}  # key: (src_id, dst_id)

    def feed_frame(self, frame: dict) -> Optional[dict]:
        """Feed a CAN frame, return reassembled UDS message if complete."""
        can_id = frame["can_id"]
        data = frame["data"]
        if len(data) < 1:
            return None

        pci_type = (data[0] >> 4) & 0xF

        if pci_type == 0:  # Single Frame
            return self._handle_single_frame(frame)
        elif pci_type == 1:  # First Frame
            return self._handle_first_frame(frame)
        elif pci_type == 2:  # Consecutive Frame
            return self._handle_consecutive_frame(frame)
        elif pci_type == 3:  # Flow Control
            return self._handle_flow_control(frame)
        return None

    def _handle_single_frame(self, frame: dict) -> dict:
        data = frame["data"]
        length = data[0] & 0xF
        payload = data[1:1+length]
        return {
            "type": "single",
            "src_id": frame["can_id"],
            "dst_id": None,
            "payload": payload,
            "service": payload[0] if payload else None,
            "frame": frame,
        }

    def _handle_first_frame(self, frame: dict) -> None:
        data = frame["data"]
        length = ((data[0] & 0xF) << 8) | data[1]
        payload = data[2:]

        key = frame["can_id"]  # Simplified
        self.sessions[key] = {
            "expected_len": length,
            "received": payload,
            "sn": 0,
            "frame": frame,
        }
        return None

    def _handle_consecutive_frame(self, frame: dict) -> Optional[dict]:
        data = frame["data"]
        sn = data[0] & 0xF
        payload = data[1:]

        # Find matching session (simplified)
        for key, sess in list(self.sessions.items()):
            if sess["sn"] == ((sn - 1) & 0xF):
                sess["received"] += payload
                sess["sn"] = sn
                if len(sess["received"]) >= sess["expected_len"]:
                    # Complete
                    result = {
                        "type": "reassembled",
                        "src_id": frame["can_id"],
                        "payload": sess["received"][:sess["expected_len"]],
                        "service": sess["received"][0] if sess["received"] else None,
                        "frames": [sess["frame"], frame],
                    }
                    del self.sessions[key]
                    return result
        return None

    def _handle_flow_control(self, frame: dict) -> None:
        # Not needed for passive capture analysis
        return None


class AnalyzerApp:
    """Offline capture analyzer."""

    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.filter_ids: Optional[Set[int]] = None
        if args.filter:
            self.filter_ids = set(int(x.strip(), 0) for x in args.filter.split(","))

        self.frames: List[dict] = []
        self.uds_decoder = ISO15765Decoder()
        self.stats = {
            "total_frames": 0,
            "filtered_frames": 0,
            "can_fd_frames": 0,
            "extended_frames": 0,
            "standard_frames": 0,
            "id_counter": Counter(),
            "error_frames": 0,
            "time_span": 0,
        }

    def run(self):
        console.print(f"[cyan]Loading {self.args.input}...[/cyan]")
        self._load_capture()

        if self.filter_ids:
            console.print(f"[cyan]Filtering to {len(self.filter_ids)} IDs...[/cyan]")
            self._apply_filter()

        console.print(f"[green]Loaded {self.stats['total_frames']} frames, {self.stats['filtered_frames']} after filter[/green]")

        if self.args.stats:
            self._print_stats()

        if self.args.decode_uds:
            self._decode_uds()

        if self.args.dbc:
            self._decode_signals()

        if self.args.output:
            self._save_report()

        return 0

    def _load_capture(self):
        path = Path(self.args.input)
        if path.suffix.lower() == ".jsonl":
            with open(path) as f:
                for line in track(f, description="Loading JSONL"):
                    frame = json.loads(line)
                    self._process_frame(frame)
        else:  # CSV
            df = pd.read_csv(path)
            for _, row in track(df.iterrows(), total=len(df), description="Loading CSV"):
                frame = {
                    "timestamp_us": int(row["timestamp_us"]),
                    "direction": row["direction"],
                    "can_id": int(row["can_id_hex"], 16),
                    "can_id_hex": row["can_id_hex"],
                    "dlc": int(row["dlc"]),
                    "data_hex": row["data_hex"],
                    "data": bytes.fromhex(row["data_hex"]),
                    "flags": int(row.get("flags", "0"), 0),
                    "extended": bool(int(row.get("extended", "0"))),
                    "fd": bool(int(row.get("fd", "0"))),
                }
                self._process_frame(frame)

        if self.frames:
            self.stats["time_span"] = (self.frames[-1]["timestamp_us"] - self.frames[0]["timestamp_us"]) / 1_000_000

    def _process_frame(self, frame: dict):
        self.stats["total_frames"] += 1
        self.stats["id_counter"][frame["can_id"]] += 1
        if frame.get("fd"):
            self.stats["can_fd_frames"] += 1
        if frame.get("extended"):
            self.stats["extended_frames"] += 1
        else:
            self.stats["standard_frames"] += 1
        self.frames.append(frame)

    def _apply_filter(self):
        self.frames = [f for f in self.frames if f["can_id"] in self.filter_ids]
        self.stats["filtered_frames"] = len(self.frames)
        # Recalculate stats
        self.stats["id_counter"] = Counter(f["can_id"] for f in self.frames)
        self.stats["can_fd_frames"] = sum(1 for f in self.frames if f.get("fd"))
        self.stats["extended_frames"] = sum(1 for f in self.frames if f.get("extended"))
        self.stats["standard_frames"] = sum(1 for f in self.frames if not f.get("extended"))

    def _print_stats(self):
        table = Table(title="Bus Statistics")
        table.add_column("Metric")
        table.add_column("Value")

        table.add_row("Total frames", str(self.stats["total_frames"]))
        table.add_row("Filtered frames", str(self.stats["filtered_frames"]))
        table.add_row("CAN FD frames", str(self.stats["can_fd_frames"]))
        table.add_row("Extended ID frames", str(self.stats["extended_frames"]))
        table.add_row("Standard ID frames", str(self.stats["standard_frames"]))
        table.add_row("Time span", f"{self.stats['time_span']:.2f} s")
        if self.stats["time_span"] > 0:
            table.add_row("Avg frame rate", f"{self.stats['filtered_frames'] / self.stats['time_span']:.1f} fps")

        console.print(table)

        # Top IDs
        id_table = Table(title="Top CAN IDs")
        id_table.add_column("CAN ID (Hex)")
        id_table.add_column("CAN ID (Dec)")
        id_table.add_column("Count")
        id_table.add_column("%")

        total = self.stats["filtered_frames"] or 1
        for can_id, count in self.stats["id_counter"].most_common(20):
            id_table.add_row(
                f"0x{can_id:X}",
                str(can_id),
                str(count),
                f"{100*count/total:.1f}%"
            )
        console.print(id_table)

    def _decode_uds(self):
        console.print("\n[cyan]Decoding UDS payloads...[/cyan]")
        uds_table = Table(title="UDS Messages")
        uds_table.add_column("Timestamp")
        uds_table.add_column("Direction")
        uds_table.add_column("CAN ID")
        uds_table.add_column("Service")
        uds_table.add_column("DID / Info")
        uds_table.add_column("Payload")

        uds_count = 0
        for frame in self.frames:
            data = frame["data"]
            if len(data) < 1:
                continue

            sid = data[0]
            # Check if it's a UDS service (positive response 0x40-0x7F, or request 0x00-0x3F)
            is_response = 0x40 <= sid <= 0x7F
            is_request = 0x00 <= sid <= 0x3F

            if is_response or is_request:
                uds_count += 1
                timestamp = datetime.fromtimestamp(frame["timestamp_us"] / 1_000_000).strftime("%H:%M:%S.%f")[:-3]
                direction = "RX" if frame["direction"] == "RX" else "TX"

                did_info = ""
                payload_hex = frame["data_hex"]

                if sid == 0x62:  # ReadDataByIdentifier Positive Response
                    if len(data) >= 3:
                        did = (data[1] << 8) | data[2]
                        did_info = f"DID 0x{did:04X}"
                        payload_hex = data[3:].hex().upper()
                elif sid == 0x22:  # ReadDataByIdentifier Request
                    if len(data) >= 3:
                        did = (data[1] << 8) | data[2]
                        did_info = f"DID 0x{did:04X}"
                elif sid == 0x71:  # RoutineControl Positive Response
                    if len(data) >= 3:
                        routine = (data[1] << 8) | data[2]
                        did_info = f"Routine 0x{routine:04X}"
                elif sid == 0x31:  # RoutineControl Request
                    if len(data) >= 4:
                        routine = (data[2] << 8) | data[3]
                        did_info = f"Routine 0x{routine:04X} (type 0x{data[1]:02X})"
                elif sid == 0x50:  # Session Control Positive Response
                    did_info = f"Session 0x{data[1]:02X}" if len(data) > 1 else ""
                elif sid == 0x10:  # Session Control Request
                    did_info = f"Session 0x{data[1]:02X}" if len(data) > 1 else ""
                elif sid == 0x7F:  # Negative Response
                    if len(data) >= 3:
                        req_sid = data[1]
                        nrc = data[2]
                        did_info = f"Req 0x{req_sid:02X} NRC 0x{nrc:02X}"

                service_name = self._sid_name(sid)
                uds_table.add_row(timestamp, direction, f"0x{frame['can_id_hex']}", service_name, did_info, payload_hex)

        console.print(f"[green]Found {uds_count} UDS messages[/green]")
        if uds_count > 0:
            console.print(uds_table)

    def _sid_name(self, sid: int) -> str:
        names = {
            0x10: "SessionControl", 0x50: "SessionControl+",
            0x22: "ReadDID", 0x62: "ReadDID+",
            0x2E: "WriteDID", 0x6E: "WriteDID+",
            0x31: "RoutineControl", 0x71: "RoutineControl+",
            0x3E: "TesterPresent", 0x7E: "TesterPresent+",
            0x85: "ControlDTC", 0xC5: "ControlDTC+",
            0x7F: "NegResponse",
        }
        return names.get(sid, f"0x{sid:02X}")

    def _decode_signals(self):
        console.print(f"[cyan]DBC signal decoding not yet implemented: {self.args.dbc}[/cyan]")
        # TODO: Use cantools to load DBC and decode signals

    def _save_report(self):
        output_path = Path(self.args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        report = {
            "summary": self.stats,
            "top_ids": [
                {"can_id_hex": f"0x{can_id:X}", "can_id_dec": can_id, "count": count}
                for can_id, count in self.stats["id_counter"].most_common(50)
            ],
        }

        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

        console.print(f"[green]Report saved to {output_path}[/green]")


def main():
    parser = argparse.ArgumentParser(description="Offline CAN capture analyzer")
    parser.add_argument("--input", required=True, help="Input CSV/JSONL file")
    parser.add_argument("--filter", help="Comma-separated CAN ID filter (hex)")
    parser.add_argument("--decode-uds", action="store_true", help="Decode UDS payloads")
    parser.add_argument("--dbc", help="DBC file for signal decoding")
    parser.add_argument("--stats", action="store_true", help="Print bus statistics")
    parser.add_argument("--output", help="Output report JSON file")
    args = parser.parse_args()

    app = AnalyzerApp(args)
    sys.exit(app.run())


if __name__ == "__main__":
    main()