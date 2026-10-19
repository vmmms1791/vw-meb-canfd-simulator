# VW MEB CAN FD Simulator

**CAN FD VW MEB Simulator** — research project for CAN FD bus analysis and electric vehicle data exchange simulation on VW MEB platform using MiniSTM32H7xx (Zephyr RTOS) as ECU simulator and WeAct USB2CANFDV (SLCAN) as host interface.

## Hardware Setup

- **Host PC**: Windows 11
- **Simulator**: MiniSTM32H7xx (Zephyr RTOS) — acts as VW MEB ECU (Battery, Thermal, Charging)
- **Interface**: WeAct USB2CANFDV (factory SLCAN firmware) — listens, sends requests, receives responses
- **Connection**: 3 wires (CAN-H, CAN-L, GND) between boards

## Quick Start

```bash
# 1. Build firmware
cd firmware
./build_firmware.bat

# 2. Flash firmware
./flash_firmware.bat

# 3. Run scenario (from host/)
cd ../host
pip install -r requirements.txt
python -m cli --port COM3 --scenario preheat --duration 60
```

## Repository Structure

```
├── firmware/          # Zephyr application (MiniSTM32H7xx)
├── host/              # Python SLCAN client + scenarios (Windows)
├── docs/              # Architecture, protocol, hardware docs
├── hardware/          # Connection diagrams, pinouts
└── .github/workflows/ # CI: build + test
```

## Documentation

- [Architecture Plan](ARCHITECTURE_PLAN.md)
- [CAN FD Protocol](docs/canfd_protocol.md)
- [UDS Services](docs/uds_services.md)
- [Hardware Setup](docs/hardware_setup.md)

## References

- [WeAct USB2CANFDV SLCAN Firmware](https://github.com/WeActStudio/WeActStudio.USB2CANFDV1.SLCAN_Firmware.git)
- [MiniSTM32H7xx](https://github.com/WeActStudio/MiniSTM32H7xx.git)
- [VW MEB EV CAN Parameters](https://github.com/spot2000/Volkswagen-MEB-EV-CAN-parameters.git)
- [MEB Preheat](https://github.com/jagheterfredrik/meb-preheat.git)
- [candleLight](https://github.com/koendv/candleLight_fw_weact_usb2canfdv1.git)
- [CANnectivity](https://github.com/CANnectivity/cannectivity.git)

## License

MIT License — see [LICENSE](LICENSE) for details.