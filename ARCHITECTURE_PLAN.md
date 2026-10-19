# ARCHITECTURAL PLAN: CAN FD VW MEB Simulator

## 1. REPOSITORY STRUCTURE (GitHub)

```
vw-meb-canfd-simulator/
├── .github/
│   └── workflows/
│       └── ci.yml                    # CI: build Zephyr app, lint Python
├── docs/
│   ├── architecture.md               # Architecture description
│   ├── canfd_protocol.md             # CAN FD parameters VW MEB
│   ├── uds_services.md               # UDS services for simulation
│   └── hardware_setup.md             # Connection diagram, pins
├── firmware/                         # Zephyr app for MiniSTM32H7xx
│   ├── CMakeLists.txt
│   ├── prj.conf
│   ├── app.overlay
│   ├── README.md
│   ├── src/
│   │   ├── main.c                    # Entry point, initialization
│   │   ├── can_simulator.c/.h        # ECU simulator logic
│   │   ├── uds_handler.c/.h          # UDS request handling
│   │   ├── meb_parameters.c/.h       # PID tables VW MEB (from spot2000/jagheterfredrik)
│   │   ├── display.c/.h              # ST7735R: "OK" / error output
│   │   ├── canfd_config.c/.h         # CAN FD config (500k/2M bit/s)
│   │   └── diagnostics.c/.h          # Self-diagnostics: timeouts, bus-off, CRC errors
│   └── tests/
│       └── test_uds_handler.c        # Unit tests (Unity/Zephyr ztest)
├── host/                             # Python app for PC (Windows 11)
│   ├── requirements.txt
│   ├── slcan_client.py               # SLCAN protocol over serial (usb2canfdv)
│   ├── meb_scenarios.py              # Request scenarios: preheat, read PID
│   ├── logger.py                     # CSV/JSONL logging
│   ├── cli.py                        # CLI: python -m host.cli --scenario preheat
│   ├── tests/
│   │   └── test_slcan_client.py      # pytest
│   └── scripts/
│       ├── flash_firmware.bat        # west flash / dfu-util / STM32CubeProgrammer
│       ├── build_firmware.bat        # west build -p always -b mini_stm32h743
│       ├── monitor_serial.bat        # PuTTY / python -m serial.tools.miniterm
│       └── run_scenario.bat          # Run scenario + logging
├── hardware/
│   ├── connection_diagram.md         # CAN-H, CAN-L, GND between boards
│   └── pinout.md                     # STM32H7 pins: CAN1/2, SPI (LCD), USB
├── CMakeLists.txt                    # Root (optional, for west workspace)
├── west.yml                          # Manifest for west (Zephyr + modules)
├── README.md                         # General description, quick start
├── LICENSE
└── .gitignore
```

---

## 2. FIRMWARE (MiniSTM32H7xx, Zephyr RTOS)

### 2.1 Key Configurations (`prj.conf`)
```properties
# Core and console
CONFIG_STDOUT_CONSOLE=y
CONFIG_LOG=y
CONFIG_LOG_MODE_IMMEDIATE=y
CONFIG_LOG_DEFAULT_LEVEL=3

# CAN FD (STM32H7 FDCAN1/2)
CONFIG_CAN=y
CONFIG_CAN_FD_MODE=y
CONFIG_CAN_STM32_FDCAN=y
CONFIG_CAN_STATISTICS=y
CONFIG_CAN_FD_MAX_DLC=15

# Display ST7735R (SPI4)
CONFIG_GPIO=y
CONFIG_SPI=y
CONFIG_DISPLAY=y
CONFIG_ST7735R=y
CONFIG_HEAP_MEM_POOL_SIZE=16384
CONFIG_MAIN_STACK_SIZE=4096
CONFIG_DCACHE=n

# USB Console (CDC ACM) — for debug
CONFIG_USB_DEVICE_STACK=y
CONFIG_USB_CDC_ACM=y
CONFIG_SERIAL=y
CONFIG_UART_LINE_CTRL=y
CONFIG_BOARD_SERIAL_BACKEND_CDC_ACM=n
CONFIG_USB_DEVICE_STACK_NEXT=n

# Scheduler / timers
CONFIG_MULTITHREADING=y
CONFIG_NUM_PREEMPT_PRIORITIES=8
CONFIG_SYS_CLOCK_HW_CYCLES_PER_SEC=240000000
```

### 2.2 DeviceTree Overlay (`app.overlay`)
```dts
/ {
    chosen {
        zephyr,canbus = &fdcan1;
        zephyr,display = &st7735r;
        zephyr,console = &cdc_acm_uart0;
    };
};

&fdcan1 {
    status = "okay";
    bus-speed = <500000>;       // Arbitration 500 kbps
    bus-speed-data = <2000000>; // Data 2 Mbps (CAN FD)
    sample-point = <800>;       // 80%
    data-sample-point = <750>;  // 75%
    sjw = <1>;
    data-sjw = <1>;
    st,fdcan-tdc-enable;
    st,fdcan-tdco = <0>;
    pinctrl-0 = <&fdcan1_pins_a>;
    pinctrl-names = "default";
};

&spi4 {
    status = "okay";
    pinctrl-0 = <&spi4_pins_a>;
    pinctrl-names = "default";
    st7735r: st7735r@0 {
        compatible = "sitronix,st7735r";
        reg = <0>;
        spi-max-frequency = <40000000>;
        reset-gpios = <&gpioe 10 GPIO_ACTIVE_LOW>;
        dc-gpios = <&gpioe 11 GPIO_ACTIVE_LOW>;
        led-gpios = <&gpioe 12 GPIO_ACTIVE_HIGH>;
        width = <160>;
        height = <80>;
        rotation = <90>;
        rgb-bgr-ordered;
    };
};
```

### 2.3 Module Architecture (C)

| Module | Responsibility |
|--------|----------------|
| `main.c` | Init subsystems, launch threads: CAN RX, Display, Diagnostics |
| `canfd_config.c` | FDCAN setup: filters (Standard/Extended ID), bitrates, TDC |
| `uds_handler.c` | UDS parsing (ISO 14229): SID 0x10, 0x22, 0x2E, 0x31, 0x3E; NRC |
| `meb_parameters.c` | Static tables: Battery PID (0x01..0x40), Preheat PID, Charging PID |
| `can_simulator.c` | State machine: WAIT_REQUEST → PROCESS → SEND_RESPONSE → WAIT; response timeouts |
| `display.c` | ST7735R: init, render "OK" (green), error (red + code), heartbeat |
| `diagnostics.c` | Monitoring: Bus-Off, Error Passive, CRC/Stuff/ACK errors, RX timeout counter |

### 2.4 Communication Protocol (CAN FD Frames)

| Direction | CAN ID (Ext) | DLC | Data | Description |
|-----------|--------------|-----|------|-------------|
| PC → SIM (Request) | 0x18DAF110 | 8 | `02 22 01 04 00 00 00 00` | UDS ReadDataByIdentifier (Battery Voltage) |
| SIM → PC (Response) | 0x18DA10F1 | 8 | `06 62 01 04 03 E8 00 00` | Positive Response: 100.0V |
| PC → SIM (Preheat) | 0x18DAF110 | 8 | `04 31 01 01 01 00 00 00` | RoutineControl: Start Preheat |
| SIM → PC | 0x18DA10F1 | 8 | `04 71 01 01 00 00 00 00` | RoutineControl Response |

*IDs in VW MEB format (29-bit Extended, SAE J1939-ish). Exact IDs from spot2000/jagheterfredrik repos.*

---

## 3. HOST APPLICATION (Windows 11, Python 3.11+)

### 3.1 Dependencies (`requirements.txt`)
```
pyserial>=3.5
crcmod>=1.7
pyyaml>=6.0
rich>=13.0        # TUI logging
pytest>=7.0
pytest-mock>=3.12
```

### 3.2 Modules

| File | Purpose |
|------|---------|
| `slcan_client.py` | SLCAN ASCII protocol: `O` (open), `C` (close), `t`/`T` (tx std/ext), `r`/`R` (rx), `\r` termination; handle `~` (timestamp), `\a` (bell/error) |
| `meb_scenarios.py` | Scenarios: `preheat()`, `read_battery_pids()`, `read_charging_status()`, `custom_uds(sid, did)` |
| `logger.py` | Write to `logs/YYYYMMDD_HHMMSS.csv` (timestamp, dir, can_id, dlc, data, interpretation) |
| `cli.py` | Args: `--port COM3 --baud 115200 --scenario preheat --duration 60 --log-dir logs` |

### 3.3 Windows Scripts (`.bat`)

```bat
:: build_firmware.bat
cd firmware
west build -p always -b mini_stm32h743 .
if errorlevel 1 exit /b 1
echo Build OK: build/zephyr/zephyr.bin

:: flash_firmware.bat
cd firmware
west flash
if errorlevel 1 (
    echo "Ignore status 74 if 'Download done' present. Press RESET on board."
)
```

---

## 4. INTEGRATION AND TESTING

### 4.1 Verification Stages
| Stage | Description | Success Criteria |
|-------|-------------|------------------|
| 1. Build | `west build` passes | `zephyr.bin` created |
| 2. Flash | `west flash` → "Download done" | Firmware loaded, manual RESET → boot |
| 3. Loopback | Connect CAN-H/H, CAN-L/L on one board (USB2CANFDV) | Echo frames returned |
| 4. Cross-link | Connect two boards with 3 wires | STM32 display: "OK", PC receives responses |
| 5. Scenario | Run `preheat` scenario 60 sec | 0 CRC errors, all UDS Positive Response |

### 4.2 Diagnostics on STM32 Display
| State | Text | Background |
|-------|------|------------|
| Initialization | `INIT...` | Yellow |
| Waiting for request | `WAIT REQ` | Blue |
| Communication OK | `OK` (heartbeat 1s) | Green |
| RX Timeout | `ERR: RX TO` | Red |
| Bus-Off | `ERR: BUS OFF` | Red |
| CRC Error | `ERR: CRC` | Red |
| UDS NRC | `NRC: 0xXX` | Orange |

---

## 5. CI / GITHUB ACTIONS

```yaml
# .github/workflows/ci.yml
on: [push, pull_request]
jobs:
  build-firmware:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup Zephyr
        uses: zephyrproject-rtos/zephyr-build-action@v1
      - name: Build
        run: west build -p always -b mini_stm32h743 firmware
      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: zephyr-bin
          path: firmware/build/zephyr/zephyr.bin
  test-host:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install -r host/requirements.txt
      - run: pytest host/tests -v
```

---

## 6. IMPLEMENTATION PLAN (STEP BY STEP)

| # | Task | Output Artifact |
|---|------|-----------------|
| 1 | Create GitHub repo `vw-meb-canfd-simulator`, init folder structure | Repo with `.gitignore`, `README.md`, `LICENSE` |
| 2 | Configure `west.yml` with Zephyr + modules (STM32 HAL, CAN) | `west.yml` |
| 3 | Create `firmware/` — CMakeLists.txt, prj.conf, app.overlay per schema | Zephyr project skeleton |
| 4 | Implement `canfd_config.c` — FDCAN1 500k/2M, Ext ID filters | Working CAN init |
| 5 | Implement `display.c` — ST7735R, status rendering | Display shows "INIT" → "WAIT REQ" |
| 6 | Implement `meb_parameters.c` — PID tables from spot2000/jagheterfredrik | Data for UDS 0x22 |
| 7 | Implement `uds_handler.c` — parser SID 0x10/0x22/0x31, response generator | Correct UDS Positive Response |
| 8 | Implement `can_simulator.c` — main loop: RX → UDS → TX | Echo response to valid requests |
| 9 | Implement `diagnostics.c` — error counters, Bus-Off detection | Display shows errors |
| 10 | Create `host/slcan_client.py` — SLCAN over pyserial | Open port, send/receive frames |
| 11 | Create `host/meb_scenarios.py` — Preheat, Battery Read scenarios | Ready scenarios |
| 12 | Write `.bat` scripts for build/flash/run | Windows automation |
| 13 | Integration test: 2 boards, 3 wires, Preheat 60 sec | Error-free log, display "OK" |
| 14 | Configure CI (GitHub Actions) | Autobuild passes |
| 15 | Documentation: `docs/architecture.md`, `hardware_setup.md` | Full reproduction guide |

---

## 7. RISKS AND MITIGATIONS

| Risk | Mitigation |
|------|------------|
| `west flash` status 74 on Windows | Document: ignore if "Download done", manual RESET |
| CAN FD bit-timing mismatch | Use `canfd_config.c` with exact regs from STM32H7 RM; verify with oscilloscope |
| SLCAN buffer overflow | `slcan_client.py`: non-blocking read, 100ms timeouts, flow control |
| Incomplete PID tables | Export from spot2000/jagheterfredrik to JSON → parse in `meb_parameters.c` |
| Display init fails | Verify `app.overlay` SPI4 pins; `CONFIG_DCACHE=n` mandatory |

---

## 8. DEFINITION OF DONE

1. Public GitHub repo, CI green.
2. `build_firmware.bat` → `flash_firmware.bat` → firmware loads.
3. Two boards connected with 3 wires.
4. `python -m host.cli --scenario preheat --duration 60` runs 60 sec error-free.
5. STM32 display shows constant **green "OK"**.
6. `logs/` creates CSV with full CAN trace + UDS interpretation.