# OBD-II (J1962) Pinout for VW MEB Vehicles

## Standard OBD-II Connector (Female on Vehicle)

```
    ┌─────────────────────────────────────┐
    │  1  2  3  4  5  6  7  8             │
    │  9 10 11 12 13 14 15 16             │
    └─────────────────────────────────────┘
```

## Pin Assignments (VW MEB Specific)

| Pin | Signal | Standard (SAE J1962) | VW MEB Usage | Notes |
|-----|--------|---------------------|--------------|-------|
| 1 | — | Manufacturer discretion | **CAN-H (Chassis/Comfort)** | Some MEB: comfort CAN |
| 2 | — | SAE J1850 Bus+ | — | Not used |
| 3 | — | Manufacturer discretion | **CAN-L (Chassis/Comfort)** | Some MEB: comfort CAN |
| 4 | Chassis Ground | Chassis Ground | **GND** | **Connect to WeAct GND** |
| 5 | Signal Ground | Signal Ground | **GND** | **Connect to WeAct GND** |
| 6 | **CAN-H (High Speed)** | ISO 15765-4 CAN-H | **CAN-H (Powertrain/Drive)** | **Connect to WeAct CAN-H** |
| 7 | K-Line | ISO 9141-2 K-Line | — | Not used on MEB |
| 8 | — | Manufacturer discretion | **Ethernet Wake / DoIP** | 12V wake for gateway (optional) |
| 9 | — | Manufacturer discretion | **CAN-H (Chassis/Comfort)** | Duplicate of Pin 1 on some |
| 10 | — | SAE J1850 Bus- | — | Not used |
| 11 | — | Manufacturer discretion | **CAN-L (Chassis/Comfort)** | Duplicate of Pin 3 on some |
| 12 | — | Manufacturer discretion | — | Not used |
| 13 | — | Manufacturer discretion | — | Not used |
| 14 | **CAN-L (High Speed)** | ISO 15765-4 CAN-L | **CAN-L (Powertrain/Drive)** | **Connect to WeAct CAN-L** |
| 15 | L-Line | ISO 9141-2 L-Line | — | Not used |
| 16 | Battery +12V | Battery Positive | **+12V (Always On)** | **Do NOT connect to WeAct** |

## MEB CAN Bus Topology

### High-Speed CAN (500 kbps) — Pins 6 & 14
- **Powertrain CAN**: Battery (BMS), Motor, DC-DC, Charger, Thermal
- **Gateway**: Central gateway (J533) routes between buses
- **This is the primary bus for diagnostics and monitoring**

### Comfort/Chassis CAN (500/100 kbps) — Pins 1/3, 9/11
- Body Control Module (BCM)
- Lights, Windows, Doors, Seats
- Not typically used for powertrain monitoring

### Ethernet (100/1000 Mbps) — Pins 8, (others)
- DoIP (Diagnostics over IP)
- Software updates, ODIS diagnostics
- Not accessible via CAN adapter

## Wiring for WeAct USB2CANFDV

### Minimal Connection (Powertrain CAN Only)
```
OBD-II Pin 6 (CAN-H) ──────► WeAct CAN-H
OBD-II Pin 14 (CAN-L) ──────► WeAct CAN-L
OBD-II Pin 4 (GND) ─────────► WeAct GND
OBD-II Pin 5 (GND) ─────────► WeAct GND (optional, redundant)
```

### Full Connection (Including Comfort CAN)
```
OBD-II Pin 6  ──────► WeAct CAN-H  (Primary)
OBD-II Pin 14 ──────► WeAct CAN-L  (Primary)
OBD-II Pin 1  ──────► WeAct CAN-H2 (Secondary, if dual-CAN adapter)
OBD-II Pin 3  ──────► WeAct CAN-L2 (Secondary)
OBD-II Pin 4/5 ─────► WeAct GND
```

> **Note**: WeAct USB2CANFDV has **single CAN channel**. For dual-CAN, use two adapters or a dual-channel interface (e.g., VNCI 6154A).

## Voltage Levels

| Signal | Recessive (Logic 1) | Dominant (Logic 0) |
|--------|---------------------|-------------------|
| CAN-H  | ~2.5V               | ~3.5V             |
| CAN-L  | ~2.5V               | ~1.5V             |
| Differential | 0V             | ~2V               |

**Measured at OBD-II pins with ignition ON, bus idle.**

## Termination

- **Vehicle Side**: 120Ω between CAN-H and CAN-L at each end of bus (inside ECUs)
- **WeAct Side**: Built-in 120Ω termination (selectable via jumper/solder bridge)
- **Ensure**: Only **two** 120Ω terminations total on the bus (one at each end)

## Diagnostic Protocols on Each Pin

| Pin(s) | Protocol | Baudrate | Use Case |
|--------|----------|----------|----------|
| 6, 14 | ISO 15765-4 (CAN) / ISO 14229 (UDS) | 500 kbps | Primary diagnostics, monitoring |
| 6, 14 | ISO 15765-4 (CAN FD) | 500k/2M | Battery, DC-DC UDS |
| 1, 3 | ISO 15765-4 (CAN) | 500/100 kbps | Body diagnostics (optional) |
| 8 | DoIP (TCP/IP over Ethernet) | 100/1000 Mbps | ODIS, software updates |
| 7, 15 | K/L-Line (ISO 9141/14230) | 10.4 kbps | Legacy (not on MEB) |

## Cable Recommendations

| Type | Pros | Cons |
|------|------|------|
| **OBD-II to DB9 + Flying Leads** | Standard, easy to connect to WeAct screw terminals | Bulky |
| **OBD-II to 4-pin JST/PH** | Compact, secure | Need crimping |
| **Custom OBD-II to WeAct Header** | Direct plug, no loose wires | Permanent modification |

## Safety Warning

⚠️ **Pin 16 is +12V (Battery Positive, Always Live)**
- **Never connect Pin 16 to WeAct** — will damage the adapter
- WeAct is USB-powered; no external power needed
- Only connect CAN-H, CAN-L, GND

⚠️ **High Voltage System**
- MEB vehicles have 400V+ HV battery
- OBD-II is isolated from HV, but follow safety procedures
- Never probe orange HV cables or connectors

## References
- SAE J1962: OBD-II Connector Standard
- ISO 15765-4: Diagnostics on CAN (DoCAN)
- VW SSP 747: ID.7 Electrical System
- VW SSP 698: ID.3/ID.4 Electrical System