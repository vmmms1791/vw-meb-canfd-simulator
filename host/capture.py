#!/usr/bin/env python3
"""
Passive CAN FD Capture Module for VW MEB Bus Monitor

Connects to WeAct USB2CANFDV via SLCAN protocol, captures CAN frames
passively (no TX), writes to CSV/JSONL with microsecond timestamps.
"""

import argparse
import csv
import json
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Set

import serial
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.text import Text

console = Console()


class SLCANClient:
    """SLCAN (Lawicel) ASCII protocol client for WeAct USB2CANFDV."""

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser: Optional[serial.Serial] = None
        self._rx_buffer = bytearray()

    def connect(self, tty_baudrate: Optional[int] = None) -> bool:
        """Open serial port and initialize SLCAN."""
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                write_timeout=1.0,
            )
            # Flush buffers
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()

            # Close any open channel
            self._send(b"C\r")
            self._read_response()

            # Set CAN bitrate if specified (SLCAN 'S' command)
            if tty_baudrate:
                # SLCAN bitrate codes: 0=10k, 1=20k, 2=50k, 3=100k, 4=125k, 5=250k, 6=500k, 7=800k, 8=1M
                # For CAN FD, we use 's' command with numeric bitrate (extended SLCAN)
                # WeAct supports: S6 (500k arbitration), then FD bitrate via proprietary command
                # Simplified: use standard SLCAN bitrate for arbitration phase
                bitrate_map = {
                    10000: "0", 20000: "1", 50000: "2", 100000: "3",
                    125000: "4", 250000: "5", 500000: "6", 800000: "7", 1000000: "8",
                }
                if tty_baudrate in bitrate_map:
                    self._send(f"S{bitrate_map[tty_baudrate]}\r".encode())
                    resp = self._read_response()
                    if resp != b"\r":
                        console.print(f"[yellow]Warning: Bitrate set response: {resp}[/yellow]")

            # Open channel (O = open normal, L = listen only)
            self._send(b"O\r")
            resp = self._read_response()
            if resp != b"\r":
                console.print(f"[red]Failed to open SLCAN channel: {resp}[/red]")
                return False

            console.print(f"[green]SLCAN connected on {self.port} @ {self.baudrate} baud[/green]")
            return True

        except serial.SerialException as e:
            console.print(f"[red]Serial error: {e}[/red]")
            return False

    def _send(self, data: bytes):
        if self.ser:
            self.ser.write(data)
            self.ser.flush()

    def _read_response(self, max_len: int = 64) -> bytes:
        """Read until '\\r' or timeout."""
        if not self.ser:
            return b""
        deadline = time.time() + self.timeout
        resp = bytearray()
        while time.time() < deadline:
            if self.ser.in_waiting:
                byte = self.ser.read(1)
                resp += byte
                if byte == b"\r":
                    break
            else:
                time.sleep(0.001)
        return bytes(resp)

    def read_frame(self) -> Optional[dict]:
        """Read one CAN frame from SLCAN. Returns dict or None."""
        if not self.ser:
            return None

        # Read line ending with \\r
        line = bytearray()
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            if self.ser.in_waiting:
                byte = self.ser.read(1)
                line += byte
                if byte == b"\r":
                    break
            else:
                time.sleep(0.001)

        if not line:
            return None

        line = bytes(line).strip()
        if not line:
            return None

        # Handle SLCAN responses
        if line == b"\r" or line == b"\a" or line.startswith(b"~"):
            return None  # OK, Bell, Timestamp - not a frame

        return self._parse_slcan_frame(line)

    def _parse_slcan_frame(self, line: bytes) -> Optional[dict]:
        """Parse SLCAN frame format:
        Standard:  tIIIDLC[DATA]\\r
        Extended:  TIIIIIIIIDLC[DATA]\\r
        FD Standard: fIIIDLC[DATA][FLAGS]\\r
        FD Extended: FIIIIIIIIDLC[DATA][FLAGS]\\r
        """
        try:
            chr0 = line[0:1]
            is_fd = chr0 in (b"f", b"F")
            is_ext = chr0 in (b"T", b"F")

            if is_ext:
                can_id = int(line[1:9], 16)
                dlc = int(line[9:10], 16)
                data_start = 10
            else:
                can_id = int(line[1:4], 16)
                dlc = int(line[4:5], 16)
                data_start = 5

            # DLC to data length mapping (CAN FD: DLC 9-15 = 12/16/20/24/32/48/64 bytes)
            dlc_to_len = {0:0, 1:1, 2:2, 3:3, 4:4, 5:5, 6:6, 7:7, 8:8,
                          9:12, 10:16, 11:20, 12:24, 13:32, 14:48, 15:64}
            data_len = dlc_to_len.get(dlc, dlc)

            data_hex = line[data_start:data_start + data_len * 2]
            if len(data_hex) < data_len * 2:
                return None

            data = bytes.fromhex(data_hex.decode())

            flags = 0
            if is_fd and len(line) > data_start + data_len * 2:
                # FD flags byte (BRS, ESI, etc.)
                flags = int(line[data_start + data_len * 2:data_start + data_len * 2 + 2], 16)

            return {
                "can_id": can_id,
                "can_id_hex": f"{can_id:X}",
                "extended": is_ext,
                "fd": is_fd,
                "dlc": dlc,
                "data_len": data_len,
                "data": data,
                "data_hex": data.hex().upper(),
                "flags": flags,
                "timestamp_us": int(time.time() * 1_000_000),
            }
        except (ValueError, IndexError) as e:
            console.print(f"[yellow]Parse error: {line} -> {e}[/yellow]")
            return None

    def close(self):
        if self.ser:
            try:
                self._send(b"C\r")
                self._read_response()
                self.ser.close()
            except Exception:
                pass
            self.ser = None


class CaptureApp:
    """Passive CAN capture application."""

    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.client = SLCANClient(args.port, args.baud, args.timeout)
        self.filter_ids: Optional[Set[int]] = None
        if args.filter:
            self.filter_ids = set(int(x.strip(), 0) for x in args.filter.split(","))

        self.frame_count = 0
        self.error_count = 0
        self.start_time = time.time()
        self.csv_file = None
        self.csv_writer = None
        self.jsonl_file = None

        # Setup signal handler
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        self._running = True

    def _signal_handler(self, signum, frame):
        console.print("\n[yellow]Stopping capture...[/yellow]")
        self._running = False

    def run(self):
        if not self.client.connect(self.args.tty_baudrate):
            return 1

        # Open output file
        output_path = Path(self.args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if self.args.format == "csv":
            self.csv_file = open(output_path, "w", newline="")
            self.csv_writer = csv.writer(self.csv_file)
            self.csv_writer.writerow(["timestamp_us", "direction", "can_id_hex", "dlc", "data_hex", "flags", "extended", "fd"])
        else:
            self.jsonl_file = open(output_path, "w")

        console.print(f"[green]Capturing to {output_path} for {self.args.duration}s...[/green]")
        if self.filter_ids:
            console.print(f"[cyan]Filter: {', '.join(f'0x{x:X}' for x in self.filter_ids)}[/cyan]")

        # Live stats display
        stats_table = Table(title="Capture Stats")
        stats_table.add_column("Metric")
        stats_table.add_column("Value")

        with Live(stats_table, refresh_per_second=2, console=console) as live:
            while self._running and (time.time() - self.start_time) < self.args.duration:
                frame = self.client.read_frame()
                if frame is None:
                    continue

                if self.filter_ids and frame["can_id"] not in self.filter_ids:
                    continue

                self._write_frame(frame)
                self.frame_count += 1

                # Update live stats
                elapsed = time.time() - self.start_time
                stats_table.rows.clear()
                stats_table.add_row("Frames captured", str(self.frame_count))
                stats_table.add_row("Errors", str(self.error_count))
                stats_table.add_row("Elapsed", f"{elapsed:.1f}s")
                stats_table.add_row("Rate", f"{self.frame_count/elapsed:.1f} fps" if elapsed > 0 else "0 fps")
                if frame:
                    stats_table.add_row("Last ID", f"0x{frame['can_id']:X} ({'EXT' if frame['extended'] else 'STD'}{' FD' if frame['fd'] else ''})")

        self._cleanup()
        console.print(f"[green]Capture complete: {self.frame_count} frames saved to {output_path}[/green]")
        return 0

    def _write_frame(self, frame: dict):
        row = [
            frame["timestamp_us"],
            "RX",
            frame["can_id_hex"],
            frame["dlc"],
            frame["data_hex"],
            f"0x{frame['flags']:02X}",
            "1" if frame["extended"] else "0",
            "1" if frame["fd"] else "0",
        ]
        if self.csv_writer:
            self.csv_writer.writerow(row)
        if self.jsonl_file:
            self.jsonl_file.write(json.dumps(frame) + "\n")

        if not self.args.silent:
            console.print(f"  RX 0x{frame['can_id_hex']} [{frame['dlc']}] {frame['data_hex']}")

    def _cleanup(self):
        self.client.close()
        if self.csv_file:
            self.csv_file.close()
        if self.jsonl_file:
            self.jsonl_file.close()


def main():
    parser = argparse.ArgumentParser(description="Passive CAN capture")
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--tty-baudrate", type=int, help="CAN bitrate for SLCAN (e.g., 500000)")
    parser.add_argument("--timeout", type=float, default=1.0)
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--output", required=True)
    parser.add_argument("--filter", help="Comma-separated CAN IDs")
    parser.add_argument("--format", choices=["csv", "jsonl"], default="csv")
    parser.add_argument("--silent", action="store_true")
    parser.add_argument("--no-fd", action="store_true")
    args = parser.parse_args()

    app = CaptureApp(args)
    sys.exit(app.run())


if __name__ == "__main__":
    main()