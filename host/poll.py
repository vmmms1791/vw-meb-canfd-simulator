#!/usr/bin/env python3
"""
Active UDS Polling Module for VW MEB Bus Monitor

Sends UDS requests (0x22 ReadDataByIdentifier) to specific ECUs
and captures responses. Requires active UDS session.
"""

import argparse
import csv
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import serial
from rich.console import Console
from rich.live import Live
from rich.table import Table

console = Console()

# UDS Services
UDS_READ_DATA_BY_ID = 0x22
UDS_SESSION_CONTROL = 0x10
UDS_TESTER_PRESENT = 0x3E

# Session types
SESSION_DEFAULT = 0x01
SESSION_EXTENDED = 0x03
SESSION_SAFETY = 0x04


class SLCANClient:
    """SLCAN client with TX support for polling."""

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser: Optional[serial.Serial] = None

    def connect(self, tty_baudrate: Optional[int] = None) -> bool:
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                write_timeout=1.0,
            )
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()

            self._send(b"C\r")
            self._read_response()

            if tty_baudrate:
                bitrate_map = {
                    10000: "0", 20000: "1", 50000: "2", 100000: "3",
                    125000: "4", 250000: "5", 500000: "6", 800000: "7", 1000000: "8",
                }
                if tty_baudrate in bitrate_map:
                    self._send(f"S{bitrate_map[tty_baudrate]}\r".encode())
                    self._read_response()

            # Open in normal mode (not listen-only)
            self._send(b"O\r")
            resp = self._read_response()
            if resp != b"\r":
                console.print(f"[red]Failed to open SLCAN: {resp}[/red]")
                return False

            console.print(f"[green]SLCAN connected on {self.port} (TX enabled)[/green]")
            return True

        except serial.SerialException as e:
            console.print(f"[red]Serial error: {e}[/red]")
            return False

    def _send(self, data: bytes):
        if self.ser:
            self.ser.write(data)
            self.ser.flush()

    def _read_response(self, max_len: int = 64) -> bytes:
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

    def send_frame(self, can_id: int, data: bytes, extended: bool = True, fd: bool = False) -> bool:
        """Send CAN frame via SLCAN."""
        if not self.ser:
            return False

        # Build SLCAN frame
        if extended:
            prefix = b"F" if fd else b"T"
            id_str = f"{can_id:08X}"
        else:
            prefix = b"f" if fd else b"t"
            id_str = f"{can_id:03X}"

        dlc = len(data)
        dlc_hex = f"{dlc:X}"
        data_hex = data.hex().upper()

        frame = prefix + id_str.encode() + dlc_hex.encode() + data_hex.encode() + b"\r"
        self._send(frame)

        # Read response (OK or error)
        resp = self._read_response()
        return resp == b"\r"

    def read_frame(self, timeout: Optional[float] = None) -> Optional[dict]:
        """Read one CAN frame."""
        if not self.ser:
            return None

        t_out = timeout or self.timeout
        line = bytearray()
        deadline = time.time() + t_out
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
        if not line or line in (b"\r", b"\a") or line.startswith(b"~"):
            return None

        return self._parse_slcan_frame(line)

    def _parse_slcan_frame(self, line: bytes) -> Optional[dict]:
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

            dlc_to_len = {0:0, 1:1, 2:2, 3:3, 4:4, 5:5, 6:6, 7:7, 8:8,
                          9:12, 10:16, 11:20, 12:24, 13:32, 14:48, 15:64}
            data_len = dlc_to_len.get(dlc, dlc)

            data_hex = line[data_start:data_start + data_len * 2]
            if len(data_hex) < data_len * 2:
                return None

            data = bytes.fromhex(data_hex.decode())

            flags = 0
            if is_fd and len(line) > data_start + data_len * 2:
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
        except (ValueError, IndexError):
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


class PollApp:
    """Active UDS polling application."""

    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.client = SLCANClient(args.port, args.baud, args.timeout)
        self.dids: List[int] = [int(x, 0) for x in args.did] if args.did else [0x0104]  # Default: Battery Voltage
        self.request_id = int(args.request_id, 0)
        self.response_id = int(args.response_id, 0)
        self.interval = args.interval
        self.count = args.count
        self.session_type = {"default": SESSION_DEFAULT, "extended": SESSION_EXTENDED, "safety": SESSION_SAFETY}[args.session]

        self.csv_file = None
        self.csv_writer = None
        self.poll_count = 0
        self.response_count = 0
        self._running = True

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        console.print("\n[yellow]Stopping poll...[/yellow]")
        self._running = False

    def run(self):
        if not self.client.connect(self.args.tty_baudrate):
            return 1

        # Open output CSV if requested
        if self.args.output:
            output_path = Path(self.args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            self.csv_file = open(output_path, "w", newline="")
            self.csv_writer = csv.writer(self.csv_file)
            self.csv_writer.writerow(["timestamp", "did_hex", "value_hex", "value_decoded", "raw_response"])

        console.print(f"[green]Starting UDS poll:[/green]")
        console.print(f"  Request ID:  0x{self.request_id:X}")
        console.print(f"  Response ID: 0x{self.response_id:X}")
        console.print(f"  DIDs:        {', '.join(f'0x{d:04X}' for d in self.dids)}")
        console.print(f"  Session:     {self.args.session} (0x{self.session_type:02X})")
        console.print(f"  Interval:    {self.args.interval}s")

        # Start diagnostic session
        if not self._start_session():
            console.print("[red]Failed to start diagnostic session[/red]")
            return 1

        # Polling loop
        stats_table = Table(title="Poll Stats")
        stats_table.add_column("Metric")
        stats_table.add_column("Value")

        with Live(stats_table, refresh_per_second=2, console=console) as live:
            while self._running and (self.count is None or self.poll_count < self.count):
                for did in self.dids:
                    if not self._running:
                        break

                    self._poll_did(did)
                    self.poll_count += 1

                    # Update stats
                    stats_table.rows.clear()
                    stats_table.add_row("Polls sent", str(self.poll_count))
                    stats_table.add_row("Responses", str(self.response_count))
                    stats_table.add_row("Success rate", f"{100*self.response_count/max(1,self.poll_count):.1f}%")

                    if self.poll_count < self.count or self.count is None:
                        time.sleep(self.interval)

        self._cleanup()
        console.print(f"[green]Poll complete: {self.poll_count} polls, {self.response_count} responses[/green]")
        return 0

    def _start_session(self) -> bool:
        """Send 0x10 Diagnostic Session Control."""
        session_data = bytes([UDS_SESSION_CONTROL, self.session_type])
        console.print(f"[cyan]Starting session 0x{self.session_type:02X}...[/cyan]")

        if not self.client.send_frame(self.request_id, session_data, extended=True):
            return False

        # Wait for response
        for _ in range(10):
            frame = self.client.read_frame(timeout=0.5)
            if frame and frame["can_id"] == self.response_id:
                data = frame["data"]
                if len(data) >= 2 and data[0] == 0x50 and data[1] == self.session_type:
                    console.print(f"[green]Session started: 0x{self.session_type:02X}[/green]")
                    return True
                elif len(data) >= 3 and data[0] == 0x7F:
                    console.print(f"[red]Session rejected: NRC 0x{data[2]:02X}[/red]")
                    return False
        return False

    def _poll_did(self, did: int):
        """Send 0x22 ReadDataByIdentifier for a specific DID."""
        # Build UDS request: 0x22 DID_HIGH DID_LOW
        req_data = bytes([UDS_READ_DATA_BY_ID, (did >> 8) & 0xFF, did & 0xFF])

        if not self.client.send_frame(self.request_id, req_data, extended=True):
            console.print(f"[red]Failed to send request for DID 0x{did:04X}[/red]")
            return

        # Wait for response
        deadline = time.time() + (self.args.timeout or 1.0)
        while time.time() < deadline:
            frame = self.client.read_frame(timeout=0.1)
            if frame and frame["can_id"] == self.response_id:
                data = frame["data"]
                if len(data) >= 3 and data[0] == 0x62 and data[1] == (did >> 8) & 0xFF and data[2] == did & 0xFF:
                    # Positive response
                    value_bytes = data[3:]
                    self.response_count += 1
                    self._log_response(did, value_bytes, frame)
                    return
                elif len(data) >= 3 and data[0] == 0x7F and data[1] == UDS_READ_DATA_BY_ID:
                    # Negative response
                    nrc = data[2]
                    console.print(f"[yellow]DID 0x{did:04X} NRC: 0x{nrc:02X}[/yellow]")
                    return

        console.print(f"[yellow]DID 0x{did:04X} timeout[/yellow]")

    def _log_response(self, did: int, value_bytes: bytes, frame: dict):
        """Log and display response."""
        value_hex = value_bytes.hex().upper()
        value_decoded = self._decode_did(did, value_bytes)

        console.print(f"  [green]DID 0x{did:04X}[/green] = {value_hex} ({value_decoded})")

        if self.csv_writer:
            self.csv_writer.writerow([
                datetime.fromtimestamp(frame["timestamp_us"] / 1_000_000).isoformat(),
                f"0x{did:04X}",
                value_hex,
                value_decoded,
                frame["data_hex"],
            ])

    def _decode_did(self, did: int, data: bytes) -> str:
        """Decode known DIDs (from spot2000 CSV)."""
        # Battery DIDs (0x0100-0x01FF range)
        if did == 0x0104:  # Battery Voltage (0.01V resolution)
            if len(data) >= 2:
                val = int.from_bytes(data[:2], "big") * 0.01
                return f"{val:.2f} V"
        elif did == 0x0105:  # Battery Current (0.1A, signed)
            if len(data) >= 2:
                val = int.from_bytes(data[:2], "big", signed=True) * 0.1
                return f"{val:.1f} A"
        elif did == 0x0106:  # SoC (%)
            if len(data) >= 1:
                return f"{data[0]} %"
        elif did == 0x0107:  # SoH (%)
            if len(data) >= 1:
                return f"{data[0]} %"
        elif did == 0x0108:  # Cell Voltage Min
            if len(data) >= 2:
                val = int.from_bytes(data[:2], "big") * 0.001
                return f"{val:.3f} V"
        elif did == 0x0109:  # Cell Voltage Max
            if len(data) >= 2:
                val = int.from_bytes(data[:2], "big") * 0.001
                return f"{val:.3f} V"
        elif did == 0x010A:  # Pack Temperature
            if len(data) >= 1:
                # Usually offset by -40°C
                return f"{data[0] - 40} °C"

        # Generic hex dump
        return " ".join(f"{b:02X}" for b in data)

    def _cleanup(self):
        self.client.close()
        if self.csv_file:
            self.csv_file.close()


def main():
    parser = argparse.ArgumentParser(description="Active UDS polling")
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--tty-baudrate", type=int)
    parser.add_argument("--timeout", type=float, default=1.0)
    parser.add_argument("--did", action="append", help="DID to poll (hex)")
    parser.add_argument("--request-id", default="0x17FC007B")
    parser.add_argument("--response-id", default="0x17FE007B")
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--count", type=int)
    parser.add_argument("--session", choices=["default", "extended", "safety"], default="extended")
    parser.add_argument("--output", help="Output CSV file")
    args = parser.parse_args()

    app = PollApp(args)
    sys.exit(app.run())


if __name__ == "__main__":
    main()