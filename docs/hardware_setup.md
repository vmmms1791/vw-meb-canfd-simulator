# Hardware Setup — VW MEB CAN FD Bus Monitor

## Required Hardware

| Component | Specification | Notes |
|-----------|---------------|-------|
| **Host PC** | Windows 11 / Linux (Ubuntu 22.04+) | Python 3.11+, USB 2.0+ |
| **CAN Interface** | WeAct USB2CANFDV (factory SLCAN firmware) | VID:PID 0483:5740, appears as COM port |
| **OBD-II Cable** | Standard OBD-II male → DB9 female + CAN-H/L/GND wires | Or custom cable with OBD-II connector |
| **Target Vehicle** | VW MEB platform (ID.3, ID.4, ID.5, ID.7, Enyaq, Q4 e-tron, Born) | Ignition ON required for CAN traffic |

## WeAct USB2CANFDV Connection

### Pinout (OBD-II J1962 Connector)

```
OBD-II Pin  | Signal    | WeAct Pin  | Wire Color (typical)
------------|-----------|------------|---------------------
6           | CAN-H     | CAN-H      | Orange/White
14          | CAN-L     | CAN-L      | Orange/Brown
4           | Chassis GND | GND      | Black/Brown
5           | Signal GND  | GND      | Black
16          | Battery +12V | —       | (Not connected to WeAct)
8           | Ethernet Wake | —     | (Optional: 12V for gateway wake)
```

### WeAct USB2CANFDV Board Connections

| WeAct Pin | Function | Connect To |
|-----------|----------|------------|
| CAN-H | CAN High | OBD-II Pin 6 |
| CAN-L | CAN Low | OBD-II Pin 14 |
| GND | Ground | OBD-II Pin 4/5 |
| 3V3/5V | Power | **Do not connect** (USB powered) |

### Wiring Diagram

```
┌─────────────┐     CAN-H (Orange)     ┌──────────────┐
│  Vehicle    │ ◄─────────────────────► │  WeAct       │
│  OBD-II     │     CAN-L (Orange)     │  USB2CANFDV  │
│  Port       │ ◄─────────────────────► │              │
│  (J1962)    │     GND (Black)        │  [USB] ──────► PC
│             │ ◄─────────────────────► │              │
└─────────────┘                        └──────────────┘
```

## Software Setup

### Windows 11

1. **Install Python 3.11+**
   ```powershell
   winget install Python.Python.3.11
   ```

2. **Install Dependencies**
   ```powershell
   cd host
   pip install -r requirements.txt
   ```

3. **Verify WeAct Detection**
   - Connect WeAct via USB
   - Check Device Manager → Ports (COM & LPT)
   - Should appear as "USB Serial Device (COM14)" or similar
   - Note the COM port number

4. **Run Capture**
   ```powershell
   python -m cli capture --port COM14 --baud 115200 --tty-baudrate 500000 --duration 60 --output logs/capture.csv
   ```

### Linux (Ubuntu 22.04+)

1. **Install Python & Serial Tools**
   ```bash
   sudo apt update && sudo apt install python3.11 python3-pip
   cd host
   pip install -r requirements.txt
   ```

2. **Add User to Dialout Group**
   ```bash
   sudo usermod -a -G dialout $USER
   # Log out/in or reboot
   ```

3. **Verify WeAct Detection**
   ```bash
   dmesg | grep tty
   ls -l /dev/ttyUSB* /dev/ttyACM*
   # Typically /dev/ttyACM0
   ```

4. **Run Capture**
   ```bash
   python -m cli capture --port /dev/ttyACM0 --baud 115200 --tty-baudrate 500000 --duration 60 --output logs/capture.csv
   ```

## Vehicle Preparation

### Minimum Requirements
- **Ignition ON** (Terminal 15 active) — dashboard lights on, not just accessory
- **High Voltage System Active** — for battery/thermal data, vehicle must be "awake"
- **Doors Closed** — some ECUs sleep when doors open

### For Full CAN Traffic (All ECUs)
1. **Start Vehicle** (press brake + start button) — HV system active
2. **Or Use Diagnostic Mode**:
   - ODIS/VCDS connected via DoIP
   - Or apply 12V to OBD Pin 8 (Ethernet wake) + Terminal 15

### For Specific ECU Traffic
| ECU | Condition |
|-----|-----------|
| Battery (BMS) | HV system active (READY light) |
| Thermal/Climate | Climate control ON, or preheat active |
| DC-DC | HV system active (12V system powered from HV) |
| Gateway | Ignition ON (Terminal 15) |
| Charging | Cable connected, charging active |

## SLCAN Configuration for MEB

### Bitrate Settings

| Parameter | Value | SLCAN Command |
|-----------|-------|---------------|
| Arbitration Phase | 500 kbps | `S6\r` |
| Data Phase | 2 Mbps | Firmware default / proprietary |

### WeAct Firmware Notes
- **Factory SLCAN Firmware**: Supports CAN FD, but data phase bitrate may be fixed at 2 Mbps
- **Custom Firmware**: For 5 Mbps data phase, flash custom build from WeAct repo
- **Listen-Only Mode**: Use `L\r` instead of `O\r` for pure passive capture

### Python SLCAN Client Settings
```python
# In cli.py / capture.py
--port COM14           # Serial port
--baud 115200          # USB serial baudrate
--tty-baudrate 500000  # CAN arbitration bitrate (S6)
```

## Troubleshooting

### No Frames Captured
1. **Check Ignition**: Must be ON (Terminal 15)
2. **Check Wiring**: CAN-H to Pin 6, CAN-L to Pin 14, GND to Pin 4/5
3. **Check Termination**: Vehicle has 120Ω termination; WeAct has selectable 120Ω (ensure enabled)
4. **Check SLCAN**: Send `O\r` manually via terminal, verify `\r` response

### Only Classic CAN Frames (No FD)
1. **Firmware**: Verify WeAct has CAN FD capable SLCAN firmware
2. **Bitrate**: Ensure `S6\r` sent before `O\r`
3. **ECU Support**: Some ECUs (Gateway, Climate) use classic CAN only

### Buffer Overflow / Missed Frames
1. **Reduce Filter**: Use `--filter` to limit to specific IDs
2. **Silent Mode**: Use `--silent` to disable console output
3. **Faster PC**: Close other apps, use SSD for log output

### WeAct Not Detected
1. **Driver**: Windows may need STM32 Virtual COM Port driver
2. **Cable**: Try different USB cable (data + power, not charge-only)
3. **Bootloader**: Hold BOOT button on WeAct while plugging in to enter DFU mode

## Safety Notes

⚠️ **High Voltage Danger**: MEB vehicles have 400V+ battery systems
- Never probe HV connectors
- OBD-II is low voltage (12V) safe
- Follow manufacturer service procedures

⚠️ **Legal/Privacy**
- Only capture data from **your own vehicle**
- VIN, location, driving behavior may be present in CAN traffic
- GDPR/privacy laws apply to personal data

## References
- WeAct USB2CANFDV: https://github.com/WeActStudio/WeActStudio.USB2CANFDV1.SLCAN_Firmware.git
- OBD-II Pinout: SAE J1962
- VW MEB Platform: SSP 747 (ID.7), SSP 698 (ID.3/4)
- CAN FD Specification: ISO 11898-1:2015