#!/usr/bin/env python3
"""
VW MEB CAN FD Bus Monitor - Unified CLI Facade

Usage:
    python -m host.cli capture --port COM14 --duration 60 --output logs/capture.csv
    python -m host.cli analyze --input logs/capture.csv --filter "0x5A2,0x5AC,0x17FC007B"
    python -m host.cli poll --port COM14 --dbc ../docs/meb_can_ids.md --interval 1.0
"""

import argparse
import sys
from pathlib import Path

# Add host to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from capture import CaptureApp
from poll import PollApp
from analyzer import AnalyzerApp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="meb-monitor",
        description="VW MEB CAN FD Bus Monitor - capture, analyze, and poll CAN traffic",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Capture 60 seconds of CAN traffic from WeAct on COM14
  %(prog)s capture --port COM14 --baud 115200 --duration 60 --output logs/capture.csv

  # Capture with SLCAN baudrate override (CAN FD 2M data phase)
  %(prog)s capture --port COM14 --baud 115200 --tty-baudrate 2000000 --duration 300 --output logs/long.csv

  # Analyze captured CSV, filter known MEB IDs, decode UDS
  %(prog)s analyze --input logs/capture.csv --filter "0x5A2,0x5AC,0x17FC007B,0x3B5,0x3C0" --decode-uds

  # Poll specific UDS DIDs periodically (requires active UDS session)
  %(prog)s poll --port COM14 --baud 115200 --tty-baudrate 2000000 --did 0x0104 --interval 1.0

Known MEB CAN IDs (see docs/meb_can_ids.md):
  Battery:     0x5A2, 0x5AC, 0xF7, 0x503 (11-bit) | 0x16A954A6, 0x12DD54D2 (29-bit)
  Battery UDS: 0x17FC007B -> 0x17FE007B (29-bit, 142 params)
  Thermal:     0x3B5, 0x668, 0x5E1, 0x5E9 (11-bit)
  Thermal UDS: 0x746 -> 0x7B0 (11-bit, DIFFERENT from Battery!)
  DC-DC:       0x5CD (11-bit) | UDS 0x17FC00B9 -> 0x17FE00B9 (29-bit)
  Gateway:     0x3C0 (Remote Start flag), 0x58C, 0x3DB, 0x3DC (11-bit)
        """
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="Sub-command")

    # Common arguments for all subcommands
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--port", required=True, help="Serial port (e.g., COM14, /dev/ttyUSB0)")
    common.add_argument("--baud", type=int, default=115200, help="Serial baudrate (default: 115200)")
    common.add_argument("--tty-baudrate", type=int, help="CAN bus bitrate for SLCAN 'S' command (e.g., 500000, 2000000)")
    common.add_argument("--timeout", type=float, default=1.0, help="Serial read timeout seconds (default: 1.0)")

    # capture subcommand
    cap = subparsers.add_parser("capture", parents=[common], help="Passive CAN capture to CSV/JSONL")
    cap.add_argument("--duration", type=int, default=60, help="Capture duration in seconds (default: 60)")
    cap.add_argument("--output", required=True, help="Output CSV/JSONL file path")
    cap.add_argument("--filter", help="Comma-separated CAN ID filter (hex), e.g., '0x5A2,0x5AC,0x17FC007B'")
    cap.add_argument("--format", choices=["csv", "jsonl"], default="csv", help="Output format (default: csv)")
    cap.add_argument("--silent", action="store_true", help="Suppress live output, only write to file")
    cap.add_argument("--no-fd", action="store_true", help="Disable CAN FD mode (classic CAN only)")

    # analyze subcommand
    ana = subparsers.add_parser("analyze", help="Offline analysis of captured CSV/JSONL")
    ana.add_argument("--input", required=True, help="Input CSV/JSONL file")
    ana.add_argument("--filter", help="Comma-separated CAN ID filter (hex)")
    ana.add_argument("--decode-uds", action="store_true", help="Decode UDS payloads (ISO-TP reassembly)")
    ana.add_argument("--dbc", help="DBC file for signal decoding (e.g., dbc/vw_meb_cantools.dbc)")
    ana.add_argument("--stats", action="store_true", help="Print bus statistics (load, ID frequency, errors)")
    ana.add_argument("--output", help="Output report file (CSV/JSON)")

    # poll subcommand
    pol = subparsers.add_parser("poll", parents=[common], help="Active UDS polling of specific DIDs")
    pol.add_argument("--did", action="append", help="DID to poll (hex), e.g., --did 0x0104 --did 0x0105")
    pol.add_argument("--request-id", default="0x17FC007B", help="UDS request CAN ID (default: Battery 0x17FC007B)")
    pol.add_argument("--response-id", default="0x17FE007B", help="Expected response CAN ID (default: Battery 0x17FE007B)")
    pol.add_argument("--interval", type=float, default=1.0, help="Poll interval seconds (default: 1.0)")
    pol.add_argument("--count", type=int, help="Number of polls (default: infinite)")
    pol.add_argument("--session", choices=["default", "extended", "safety"], default="extended", help="UDS session type")
    pol.add_argument("--output", help="Output CSV file for polled values")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "capture":
            app = CaptureApp(args)
            app.run()
        elif args.command == "analyze":
            app = AnalyzerApp(args)
            app.run()
        elif args.command == "poll":
            app = PollApp(args)
            app.run()
        else:
            parser.print_help()
            sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()