# ARCHITECTURAL PLAN: CAN FD VW MEB Bus Monitor

## 1. REPOSITORY STRUCTURE (GitHub)

```
vw-meb-canfd-simulator/
├── .github/
│   └── workflows/
│       └── ci.yml                    # CI: lint Python, run tests
├── docs/
│   ├── architecture.md               # This architecture description
│   ├── canfd_protocol.md             # CAN FD parameters VW MEB (500k/2M)
│   ├── meb_can_ids.md                # Known Extended CAN IDs for MEB ECUs
│   ├── uds_services.md               # UDS on CAN FD (ISO 14229 / ISO 15765-2)
│   └── hardware_setup.md             # OBD-II wiring, SLCAN config
├── host/                             # Python app for PC (Windows 11 / Linux)
│   ├── requirements.txt
│   ├── slcan_client.py               # SLCAN protocol over serial (usb2canfdv)
│   ├── capture.py                    # Passive CAN FD frame capture + timestamps
│   ├── analyzer.py                   # Offline analysis: filters, UDS decode, stats
│   ├── cli.py                        # CLI: python -m host.cli --port COM14 --duration 300
│   ├── tests/
│   │   ├── test_slcan_client.py      # pytest
│   │   ├── test_capture.py
│   │   └── test_analyzer.py
│   └── scripts/
│       └── run_capture.bat           # Windows wrapper
├── hardware/
│   └── obd2_pinout.md                # OBD-II pins: CAN-H(6), CAN-L(14), GND(4/5)
├── README.md                         # General description, quick start
├── LICENSE
└── .gitignore
```

---

## 2. HOST APPLICATION (Windows 11 / Linux, Python 3.11+)

### 2.1 Dependencies (`requirements.txt`)

```
pyserial>=3.5
crcmod>=1.7
pyyaml>=6.0
rich>=13.0        # TUI logging, progress bars
pandas>=2.0       # CSV analysis
pytest>=7.0
pytest-mock>=3.12
```

### 2.2 Modules

| File | Purpose |
|------|---------|
| `slcan_client.py` | SLCAN ASCII protocol: `O` (open), `C` (close), `t`/`T` (tx std/ext), `r`/`R` (rx), `\r` termination; handle `~` (timestamp), `\a` (bell/error); **RX-only mode** |
| `capture.py` | Passive capture: open SLCAN, set filters (optional), stream frames to CSV/JSONL with µs timestamps; handle buffer overflow, reconnection |
| `analyzer.py` | Offline: load CSV → filter by CAN ID range, decode UDS (ISO-TP reassembly), statistics (bus load, error frames, ID frequency), export reports |
| `cli.py` | Args: `--port COM14 --baud 115200 --duration 300 --output logs/capture.csv --filter "0x18DA*" --silent` |

### 2.3 Windows Scripts (`.bat`)

```bat
:: run_capture.bat
cd host
python -m cli --port %1 --baud 115200 --duration %2 --output logs/capture_%DATE:~6,4%%DATE:~3,2%%DATE:~0,2%_%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%.csv
```

---

## 3. COMMUNICATION PROTOCOL (CAN FD Frames — VW MEB)

### 3.1 CAN FD Bit Timing (MEB Standard)

| Phase | Bitrate | Sample Point | SJW |
|-------|---------|--------------|-----|
| Arbitration | 500 kbps | 80% | 1 |
| Data | 2 Mbps (some ECUs 5 Mbps) | 75% | 1 |

### 3.2 Known MEB Extended CAN IDs (29-bit, SAE J1939-style)

| CAN ID (Hex) | Source ECU | Target | Description |
|--------------|------------|--------|-------------|
| `0x18DAF110` | Gateway/Charger | Battery (0x10) | UDS Request (0x22, 0x31, 0x10) |
| `0x18DA10F1` | Battery (0x10) | Gateway/Charger | UDS Response (0x62, 0x71, 0x50) |
| `0x18DAF111` | Gateway | Thermal (0x11) | Thermal management UDS |
| `0x18DA11F1` | Thermal | Gateway | Thermal response |
| `0x18DAF112` | Gateway | Charging (0x12) | Charging control UDS |
| `0x18DA12F1` | Charging | Gateway | Charging response |
| `0x18FEF100` | Gateway | Broadcast | Gateway status / NM |
| `0x18FF00F1` | Battery | Broadcast | Battery status (SoC, Voltage, Current) |
| `0x18FF11F1` | Thermal | Broadcast | Thermal status (Temps, Pump, Valve) |

*Exact IDs from spot2000/Volkswagen-MEB-EV-CAN-parameters and jagheterfredrik/meb-preheat.*

### 3.3 UDS on CAN FD (ISO 15765-2)

| SID | Service | Use Case |
|-----|---------|----------|
| 0x10 | Diagnostic Session Control | Default (0x01), Extended (0x03), Safety (0x04) |
| 0x22 | ReadDataByIdentifier | Battery PID (0x0104=Voltage), Thermal PID |
| 0x2E | WriteDataByIdentifier | Configuration (rare, protected) |
| 0x31 | RoutineControl | Preheat (0x0101), Battery Heating |
| 0x3E | TesterPresent | Keep session alive |
| 0x85 | ControlDTCSetting | DTC on/off |

---

## 4. CAPTURE PIPELINE

```
Vehicle OBD-II → WeAct USB2CANFDV (SLCAN) → USB/Serial → PC (host/capture.py)
                                                                    ↓
                                                         CSV/JSONL: timestamp, dir, can_id, dlc, data[], flags
                                                                    ↓
                                                         analyzer.py: filter → ISO-TP reassemble → UDS decode → report
```

### 4.1 CSV Output Format

```csv
timestamp_us,direction,can_id_hex,dlc,data_hex,flags
1729680000123456,RX,18DAF110,8,0222010400000000,
1729680000124567,RX,18DA10F1,8,0662010403E80000,
```

### 4.2 Filtering (CLI `--filter`)

- Single ID: `--filter 0x18DAF110`
- Range: `--filter "0x18DAF110-0x18DAF11F"`
- Prefix: `--filter "0x18DA*"`
- Multiple: `--filter 0x18DAF110,0x18DA10F1,0x18FF00F1`

---

## 5. INTEGRATION AND TESTING

### 5.1 Verification Stages

| Stage | Description | Success Criteria |
|-------|-------------|------------------|
| 1. SLCAN Open | `slcan_client.py` opens COM14 @ 115200, sends `O\r` | Receives `\r` (OK) |
| 2. Passive RX | Listen on vehicle CAN bus (ignition ON) | Frames received, no TX sent |
| 3. CAN FD Frames | Verify DLC > 8, FD flag in SLCAN (`F` prefix) | DLC 12/16/20/24/32/48/64 captured |
| 4. Known IDs | Filter `0x18DA*` → UDS traffic visible | Battery/Thermal/Charging IDs present |
| 5. Long Capture | 5+ min capture, no buffer loss | Sequence numbers continuous, 0 CRC errors |
| 6. Analysis | `analyzer.py` decodes UDS 0x22/0x62 pairs | Voltage/SoC/Temps extracted correctly |

### 5.2 Diagnostics / Monitoring

| Metric | Target |
|--------|--------|
| Frame rate | Up to ~3000 fps (CAN FD 2M, 64 bytes) |
| Timestamp resolution | 1 µs (PC) / SLCAN `~` timestamp |
| Buffer overflow | Zero (non-blocking read, 100ms timeout) |
| Reconnection | Auto-reconnect on serial disconnect |

---

## 6. IMPLEMENTATION PLAN (STEP BY STEP)

| # | Task | Output Artifact |
|---|------|-----------------|
| 1 | Update repo: rename purpose, update README, ARCHITECTURE_PLAN | This commit |
| 2 | Create `host/` skeleton: `requirements.txt`, `slcan_client.py` (RX-only) | Working SLCAN open/close |
| 3 | Implement `capture.py` — streaming capture to CSV with timestamps | `python -m cli --port COM14 --duration 10` writes CSV |
| 4 | Add CAN FD frame parsing (DLC 9-64, Extended ID) | Correct DLC/data in CSV |
| 5 | Implement `analyzer.py` — load CSV, filter IDs, ISO-TP reassembly | `python -m analyzer --input capture.csv --filter "0x18DA*"` |
| 6 | Add UDS decode: 0x22/0x62, 0x31/0x71, 0x10/0x50 | Human-readable output |
| 7 | Create `docs/meb_can_ids.md` — curated ID table from references | Reference for filtering |
| 8 | Create `docs/canfd_protocol.md` — MEB bit timing, frame format | Specification |
| 9 | Create `docs/uds_services.md` — UDS on CAN FD specifics | Reference |
| 10 | Create `docs/hardware_setup.md` — OBD-II wiring, SLCAN config | Setup guide |
| 11 | Windows `.bat` wrapper + CI (GitHub Actions: lint + pytest) | Automated checks |
| 12 | Field test: WeAct on COM14 + VW MEB vehicle (ID.3/ID.4) | Real capture log |

---

## 7. RISKS AND MITIGATIONS

| Risk | Mitigation |
|------|------------|
| SLCAN buffer overflow at high bus load | Non-blocking read, dedicated RX thread, 100ms timeout, flow control |
| Vehicle requires ignition/awake for CAN traffic | Document: ignition ON, or 12V on OBD pin 8 (Ethernet wake) |
| CAN FD 5 Mbps data phase not supported by WeAct SLCAN | Verify firmware; fallback to 2 Mbps; log data-phase bitrate |
| UDS ISO-TP multi-frame reassembly complexity | Implement per ISO 15765-2: FC (Flow Control), block size, STmin |
| Legal/privacy: capturing vehicle data | Disclaimer: own vehicle only, no VIN logging without consent |

---

## 8. DEFINITION OF DONE

1. Public GitHub repo, CI green (lint + pytest).
2. `python -m host.cli --port COM14 --duration 60 --output test.csv` captures frames.
3. Captured CSV contains valid CAN FD frames (Extended ID, DLC up to 64).
4. `python -m analyzer --input test.csv --filter "0x18DA*"` decodes UDS pairs.
5. Known MEB IDs (Battery 0x18DAF110/0x18DA10F1, Thermal, Charging) visible in capture.
6. Documentation complete: `docs/*.md` cover setup, IDs, UDS, protocol.