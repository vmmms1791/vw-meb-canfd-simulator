# UDS Services on CAN FD — VW MEB Platform

## Overview

VW MEB vehicles use **UDS (ISO 14229-1)** over **CAN FD (ISO 11898-1)** with **ISO-TP (ISO 15765-2)** transport protocol.

Key differences from classic CAN:
- **Larger payloads**: Up to 64 bytes per CAN FD frame (vs 8 bytes)
- **Multi-frame efficiency**: Fewer frames needed for large DID reads
- **Mixed addressing**: Some ECUs use 11-bit, others 29-bit CAN IDs

## Addressing Schemes

### Battery (BMS) — 29-bit Extended (SAE J1939-style)
| Direction | CAN ID | Description |
|-----------|--------|-------------|
| Request | `0x17FC007B` | Tester → BMS |
| Response | `0x17FE007B` | BMS → Tester |

**Format**: `0x18DA` + Source + Target (but actual IDs are `0x17FC007B`/`0x17FE007B` per spot2000 CSV)

### Thermal/Climate — 11-bit Standard (Functional Addressing)
| Direction | CAN ID | Description |
|-----------|--------|-------------|
| Request | `0x746` | Tester → Climate |
| Response | `0x7B0` | Climate → Tester |

**Important**: Different bit-length from Battery! Do not assume all UDS uses 29-bit.

### DC-DC Converter — 29-bit Extended
| Direction | CAN ID | Description |
|-----------|--------|-------------|
| Request | `0x17FC00B9` | Tester → DC-DC |
| Response | `0x17FE00B9` | DC-DC → Tester |

**ODX Diagnostic Address**: `8105` (separate from CAN ID, used in DoIP/ODX context)

## Supported UDS Services (Observed)

| SID | Service | Sub-function | MEB Usage |
|-----|---------|--------------|-----------|
| `0x10` | Diagnostic Session Control | `0x01` Default, `0x03` Extended, `0x04` Safety | Required before any diagnostic access |
| `0x22` | ReadDataByIdentifier | — | **Primary service** — read 142+ battery params, climate, DC-DC |
| `0x2E` | WriteDataByIdentifier | — | Configuration (rare, security-protected) |
| `0x31` | RoutineControl | `0x01` Start, `0x02` Stop, `0x03` Results | Preheat (0x0101), Battery heating, Self-tests |
| `0x3E` | TesterPresent | `0x00` No response, `0x80` Suppress response | Keep session alive (periodic) |
| `0x85` | ControlDTCSetting | `0x01` On, `0x02` Off | DTC management |

## ReadDataByIdentifier (0x22) — Battery Parameters

From spot2000 CSV (ID.3 v164) — **142 parameters** on `0x17FC007B` → `0x17FE007B`:

### Electrical (Voltage/Current)
| DID | Parameter | Unit | Resolution |
|-----|-----------|------|------------|
| `0x0104` | Battery Pack Voltage | V | 0.01 |
| `0x0105` | Battery Pack Current | A | 0.1 (signed) |
| `0x0106` | State of Charge (SoC) | % | 1 |
| `0x0107` | State of Health (SoH) | % | 1 |
| `0x0108` | Minimum Cell Voltage | V | 0.001 |
| `0x0109` | Maximum Cell Voltage | V | 0.001 |
| `0x010A` | Pack Temperature (avg) | °C | 1 (offset -40) |

### Cell Temperatures (Multiple DIDs)
| DID Range | Description |
|-----------|-------------|
| `0x0110`-`0x012F` | Individual cell voltages (96 cells typical) |
| `0x0130`-`0x014F` | Individual cell temperatures |
| `0x0150`-`0x016F` | Module temperatures |

### Energy/Capacity
| DID | Parameter | Unit |
|-----|-----------|------|
| `0x0170` | Total Energy Charged | Wh |
| `0x0171` | Total Energy Discharged | Wh |
| `0x0172` | Available Energy | Wh |
| `0x0173` | Nominal Capacity | Ah |

### Multi-frame Responses
Many DIDs return **multi-frame ISO-TP responses** (>8 bytes). Example:
```
Request:  0x17FC007B [0x22, 0x01, 0x04]
Response: 0x17FE007B [0x10, 0x14, 0x62, 0x01, 0x04, 0x03, 0xE8, 0x00]  (First Frame, 20 bytes)
Response: 0x17FE007B [0x21, 0x00, 0x00, ...]  (Consecutive Frame)
```

## RoutineControl (0x31) — Preheat / Battery Heating

| Routine ID | Description | Sub-function |
|------------|-------------|--------------|
| `0x0101` | High Voltage Battery Preheat | `0x01` Start, `0x03` Results |
| `0x0102` | Battery Heating (AC) | `0x01` Start |
| `0x0201` | Cabin Preheat (Climate) | `0x01` Start |

**Request Format**: `0x31 0x01 0x01 0x01` (Start routine 0x0101)
**Response Format**: `0x71 0x01 0x01 0x00` (Routine started)

## ISO-TP (ISO 15765-2) on CAN FD

### Frame Types (PCI - Protocol Control Information)

| PCI Type | Value | Description |
|----------|-------|-------------|
| Single Frame (SF) | `0x0` | Payload ≤ 7 bytes (classic) or ≤ 63 bytes (FD) |
| First Frame (FF) | `0x1` | First frame of multi-frame, includes total length |
| Consecutive Frame (CF) | `0x2` | Subsequent frames, includes sequence number (0x0-0xF) |
| Flow Control (FC) | `0x3` | Receiver controls flow (Block Size, STmin) |

### CAN FD Specifics
- **Single Frame**: Up to 63 bytes payload (DLC=15)
- **First Frame**: 2-byte length (12-bit = up to 4095 bytes), then up to 61 bytes data
- **Consecutive Frame**: 1-byte SN, up to 63 bytes data
- **Flow Control**: Same as classic CAN

### Flow Control Parameters (Typical MEB)
| Parameter | Value | Description |
|-----------|-------|-------------|
| Block Size (BS) | 0 | No block limit (send all CFs) |
| STmin | 0x00-0x7F (0-127ms) or 0xF1-0xF9 (100µs-900µs) | Minimum separation time |

## Negative Response Codes (NRC)

| NRC | Name | Meaning |
|-----|------|---------|
| `0x11` | ServiceNotSupported | SID not supported |
| `0x12` | SubFunctionNotSupported | Sub-function not supported |
| `0x13` | IncorrectMessageLength | Wrong DLC/data length |
| `0x22` | ConditionsNotCorrect | Session/state not correct |
| `0x31` | RequestOutOfRange | DID/routine out of range |
| `0x33` | SecurityAccessDenied | Security required |
| `0x78` | ResponsePending | ECU needs more time (send 0x3E TesterPresent) |

## Session Management Flow

```
1. Tester → ECU: 0x10 0x03 (Extended Session Request)
2. ECU → Tester: 0x50 0x03 (Positive Response)
3. Tester → ECU: 0x22 0x01 0x04 (Read Battery Voltage)
4. ECU → Tester: 0x62 0x01 0x04 0x03 0xE8 (100.0V)
5. Periodic: 0x3E 0x00 (TesterPresent every 1-2s)
6. Tester → ECU: 0x10 0x01 (Default Session) — cleanup
```

## Implementation Notes for Capture/Analysis

1. **Passive Capture**: Only observes traffic, cannot initiate UDS sessions
2. **Session Detection**: Look for 0x10/0x50 pairs to identify active sessions
3. **Multi-frame Reassembly**: Required for DIDs returning >7 bytes (most battery DIDs)
4. **Address Filtering**: Filter by request/response ID pairs per ECU
5. **Timestamp Correlation**: Use µs timestamps to match request/response pairs

## References
- ISO 14229-1:2020 (UDS)
- ISO 15765-2:2016 (ISO-TP)
- ISO 15765-3 (Implementation)
- spot2000/Volkswagen-MEB-EV-CAN-parameters (DID tables)
- jagheterfredrik/meb-preheat (RoutineControl examples)