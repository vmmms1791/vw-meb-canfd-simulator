# CAN FD Protocol — VW MEB Platform

## Bit Timing (MEB Standard)

| Phase | Bitrate | Sample Point | SJW | Prescaler | TSEG1 | TSEG2 |
|-------|---------|--------------|-----|-----------|-------|-------|
| Arbitration | 500 kbps | 80% | 1 | Calculated per MCU clock | — | — |
| Data | 2 Mbps | 75% | 1 | Calculated per MCU clock | — | — |

*Some ECUs may use 5 Mbps data phase (e.g., high-speed battery communication).*

## Frame Format

### CAN FD Base Frame Format (ISO 11898-1:2015)

```
SOF | Identifier (11/29 bit) | FDF | res | BRS | ESI | DLC | Data (0-64 bytes) | CRC | ACK | EOF
```

| Field | Standard CAN | CAN FD |
|-------|--------------|--------|
| FDF (FD Format) | 0 (dominant) | 1 (recessive) |
| BRS (Bit Rate Switch) | N/A | 1 = data phase at higher bitrate |
| ESI (Error State Indicator) | N/A | 0 = error active, 1 = error passive |
| DLC | 0-8 bytes | 0-8, 12, 16, 20, 24, 32, 48, 64 bytes |

### DLC to Data Length Mapping (CAN FD)

| DLC | Data Length |
|-----|-------------|
| 0-8 | 0-8 bytes |
| 9 | 12 bytes |
| 10 | 16 bytes |
| 11 | 20 bytes |
| 12 | 24 bytes |
| 13 | 32 bytes |
| 14 | 48 bytes |
| 15 | 64 bytes |

## MEB-Specific CAN FD Usage

### Battery (BMS) Communication
- **Arbitration**: 500 kbps (standard)
- **Data**: 2 Mbps (CAN FD with BRS=1)
- **Frame Types**: Mixed standard (11-bit broadcast) + extended (29-bit UDS)
- **Max DLC**: 64 bytes (for multi-DID UDS responses)

### Thermal/Climate Communication
- **Primarily**: Classic CAN (11-bit, 500 kbps)
- **UDS**: 11-bit standard IDs (0x746/0x7B0) — **not extended!**
- **Data Phase**: Usually not used (classic CAN frames)

### DC-DC Converter
- **Broadcast**: Classic CAN (11-bit, 0x5CD)
- **UDS**: Extended CAN FD (29-bit, 0x17FC00B9/0x17FE00B9)

### Gateway/Terminal
- **Classic CAN only**: 11-bit IDs at 500 kbps
- **No CAN FD observed** on gateway broadcast messages

## SLCAN Protocol (WeAct USB2CANFDV)

The WeAct USB2CANFDV uses Lawicel SLCAN ASCII protocol over USB CDC-ACM.

### Commands Used

| Command | Description | Example |
|---------|-------------|---------|
| `O\r` | Open channel (normal) | `O\r` → `\r` |
| `L\r` | Open channel (listen only) | `L\r` → `\r` |
| `C\r` | Close channel | `C\r` → `\r` |
| `S<n>\r` | Set bitrate (standard) | `S6\r` → `\r` (500k) |
| `tIIIL...` | TX standard frame | `t12340102\r` |
| `TIIIIIIIL...` | TX extended frame | `T12345678801020304\r` |
| `fIIIL...` | TX FD standard | `f12380102030405060708\r` |
| `FIIIIIIIL...` | TX FD extended | `F12345678810102030405060708\r` |
| `r` | RX standard (incoming) | `r123401020304\r` |
| `R` | RX extended | `R12345678801020304\r` |
| `~timestamp` | Timestamp (100µs units) | `~1A2B\r` |
| `\a` | Bell (error/buffer full) | `\a` |

### Bitrate Codes (S command)

| Code | Bitrate |
|------|---------|
| 0 | 10 kbps |
| 1 | 20 kbps |
| 2 | 50 kbps |
| 3 | 100 kbps |
| 4 | 125 kbps |
| 5 | 250 kbps |
| **6** | **500 kbps** (MEB arbitration) |
| 7 | 800 kbps |
| 8 | 1 Mbps |

*Note: For CAN FD data phase bitrate (2M/5M), WeAct firmware may use proprietary commands or fixed configuration.*

### Frame Reception Format

**Standard CAN (11-bit):**
```
tIIILDDDDDDDD\r
```
- `t`: Standard frame
- `III`: 3 hex chars = 11-bit ID
- `L`: 1 hex char = DLC (0-8)
- `DD...`: 2*L hex chars = data bytes

**Extended CAN (29-bit):**
```
TIIIIIIILDDDDDDDD\r
```
- `T`: Extended frame
- `IIIIIIII`: 8 hex chars = 29-bit ID
- `L`: DLC
- `DD...`: data

**CAN FD Standard:**
```
fIIIL...DD...F\r
```
- `f`: FD standard frame
- `F` at end: FD flags (BRS, ESI)

**CAN FD Extended:**
```
FIIIIIIIL...DD...F\r
```

## Implementation Notes for WeAct USB2CANFDV

1. **Default Firmware**: Ships with SLCAN firmware supporting CAN FD
2. **Serial Baudrate**: 115200 (USB CDC-ACM, actual throughput limited by USB)
3. **CAN FD Support**: 
   - Arbitration 500k via `S6\r`
   - Data phase 2M/5M configured in firmware (may need custom build)
4. **Buffer**: ~1KB RX buffer, can overflow at high bus load
5. **Timestamp**: `~` prefix gives 100µs resolution timer value
6. **Listen-Only Mode**: Use `L\r` instead of `O\r` for passive capture

## References
- ISO 11898-1:2015 (CAN FD)
- ISO 15765-2 (ISO-TP)
- Lawicel SLCAN Protocol Specification
- WeAct USB2CANFDV SLCAN Firmware: https://github.com/WeActStudio/WeActStudio.USB2CANFDV1.SLCAN_Firmware.git