# VW MEB CAN FD Bus Monitor

**CAN FD VW MEB Bus Monitor** — tool for passive listening and analysis of CAN FD bus traffic on VW MEB platform vehicles using WeAct USB2CANFDV (SLCAN) as the capture interface.

## Hardware Setup

- **Host PC**: Windows 11 / Linux
- **Interface**: WeAct USB2CANFDV (factory SLCAN firmware) — passive CAN FD listener
- **Connection**: OBD-II cable (CAN-H, CAN-L, GND) to vehicle diagnostic port
- **Target**: VW MEB platform vehicles (ID.3, ID.4, ID.5, ID.7, Enyaq, Q4 e-tron, Born, etc.)

## Quick Start

```bash
# 1. Install dependencies
cd host
pip install -r requirements.txt

# 2. Run capture (WeAct on COM14)
python -m cli --port COM14 --baud 115200 --duration 300 --output logs/capture.csv

# 3. Analyze captured data
python -m analyzer --input logs/capture.csv --filter "0x18DA*" --decode-uds
```

## Repository Structure

```
├── host/                 # Python SLCAN client + capture/analysis tools (Windows/Linux)
│   ├── requirements.txt
│   ├── slcan_client.py   # SLCAN protocol over serial (usb2canfdv)
│   ├── capture.py        # Passive CAN FD frame capture with timestamps
│   ├── analyzer.py       # Offline analysis: filtering, UDS decoding, statistics
│   ├── cli.py            # CLI entry point
│   └── scripts/
│       └── run_capture.bat
├── docs/                 # Protocol docs, MEB CAN IDs, UDS services
│   ├── canfd_protocol.md
│   ├── meb_can_ids.md
│   ├── uds_services.md
│   └── hardware_setup.md
├── hardware/             # Connection diagrams, pinouts
│   └── obd2_pinout.md
├── .github/workflows/    # CI: lint, test
└── LICENSE
```

## Documentation

- [CAN FD Protocol](docs/canfd_protocol.md) — MEB CAN FD parameters (500k/2M bit/s)
- [MEB CAN IDs](docs/meb_can_ids.md) — Known Extended IDs for Battery, Thermal, Charging, Gateway
- [UDS Services](docs/uds_services.md) — UDS on CAN FD (ISO 14229 / ISO 15765-2)
- [Hardware Setup](docs/hardware_setup.md) — OBD-II wiring, SLCAN configuration

## References

- [WeAct USB2CANFDV SLCAN Firmware](https://github.com/WeActStudio/WeActStudio.USB2CANFDV1.SLCAN_Firmware.git)
- [VW MEB EV CAN Parameters](https://github.com/spot2000/Volkswagen-MEB-EV-CAN-parameters.git)
- [MEB Preheat](https://github.com/jagheterfredrik/meb-preheat.git)
- [candleLight](https://github.com/koendv/candleLight_fw_weact_usb2canfdv1.git)
- [CANnectivity](https://github.com/CANnectivity/cannectivity.git)
- [SAE J1939 / ISO 11898 / ISO 15765-2](https://www.iso.org/standard/63652.html)

## License

MIT License — see [LICENSE](LICENSE) for details.