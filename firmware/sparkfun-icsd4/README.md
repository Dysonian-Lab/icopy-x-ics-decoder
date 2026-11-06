# SparkFun iCS D4 — Diagnostic Sniffer & iCS Decoder Accessory

Firmware for the SparkFun Qwiic Pro Micro USB-C (ATmega32U4) that serves a dual role:

1. **Primary**: iCS Decoder accessory for the iCopy-X — responds to `Who` → `ISE` and `RD` → `OK` + card block, maintaining 100% reverse compatibility with the production `icsdecooderori.ino` handshake. **Does not touch the iCopy-X no-flash firmware.**

2. **Secondary**: Benchtop Wiegand diagnostic sniffer — captures raw Wiegand frames into an 8-slot ring buffer, streams them to a PC serial monitor in SNIFF mode, and lets an operator analyze non-standard Wiegand payloads that the iCopy-X middleware failed to parse.

## Supported Wiegand Formats (RD Output)

| Format | Bits | FC Field | CN Field | Example |
|--------|------|----------|----------|---------|
| H10301 | 26 | bits 1-8 (8-bit) | bits 9-24 (16-bit) | FC#:100 ID#:613 |
| Kantech / Corporate 1000 | 34 | bits 1-16 (16-bit) | bits 17-32 (16-bit) | — |
| Corporate 1000 | 35 | bits 1-13 (13-bit) | bits 14-33 (20-bit) | — |
| Corporate 1000 | 37 | bits 1-17 (17-bit) | bits 18-35 (18-bit) | — |
| **Corporate 1000** | **48** | **bits 3-24 (22-bit)** | **bits 25-47 (23-bit)** | **FC#:7874 ID#:1341** |
| **Avigilon 56-bit** | **56** | **bits 2-21 (20-bit)** | **bits 22-55 (34-bit)** | **FC#:858 ID#:2493837** |

Formats not listed return `FC#:0 ID#:0` but still return `OK` with the raw `Hex#` data.

## Serial Commands

| Command | Description |
|---------|-------------|
| `Who` | iCopy-X handshake → `ISE` |
| `RD` | Read production card block (or `??` if no valid card) |
| `STATUS` | Print most recent raw frame from ring buffer |
| `DUMP [n]` | Print ring slot (0-7) |
| `CLEAR` | Reset ring buffer & live state |
| `MODE BRIDGE\|SNIFF` | Toggle silent capture vs auto-print |
| `TIMEOUT <ms>` | Set frame gap timeout (5-100ms) |
| `BITS` | Show live bit accumulation count |
| `BRUTE` | Brute-force FC/CN field positions on captured frame |
| `HELP` / `/?` | Show this menu |

## Hardware

| Component | Details |
|-----------|---------|
| MCU | SparkFun Qwiic Pro Micro USB-C (ATmega32U4) **5V / 16MHz** |
| Connection | USB-C native — no hardware modification required |
| RFID Reader | HID multiCLASS SE RP10 / RP40 |

### Board Selection in Arduino IDE

**Tools → Board → SparkFun AVR Boards → SparkFun Qwiic Pro Micro (ATmega32U4)**

This is the **official SparkFun board**. Amazon clone Pro Micros (especially USB-C variants) are known to be difficult or impossible to flash due to different bootloaders and USB-to-serial chips. If you have a clone that won't flash, use an official SparkFun Qwiic Pro Micro USB-C.

### Wiring

| Pro Micro Pin | RP10 Wire | Function |
|---------------|-----------|----------|
| VCC | Red | +5V power to reader |
| GND | Black | Common ground |
| Pin 2 (D0, INT0) | Green | Wiegand D0 |
| Pin 3 (D1, INT1) | White | Wiegand D1 |

Keep D0/D1 leads short (<15 cm) to preserve Wiegand timing integrity. The RP10 draws ~75 mA standby, ~100 mA peak.

## Flashing

1. Install **SparkFun AVR Boards** via Arduino IDE Boards Manager:
   `https://raw.githubusercontent.com/sparkfun/Arduino_Boards/main/IDE_Board_Manager/package_sparkfun_index.json`
2. Select **Tools → Board → SparkFun AVR Boards → SparkFun Qwiic Pro Micro (ATmega32U4)**
3. Open `icsd4.ino`
4. Select the correct COM port under **Tools → Port**
5. Click **Upload**

> **One-shot flash warning:** The Pro Micro is difficult to reflash. Verify your configuration before uploading. This sketch has not been compiled in this environment — verify with Arduino IDE before the production flash.

## Protocol

The device enumerates as a USB CDC serial port at 115200 8N1. The iCopy-X communicates with a simple text protocol:

| Direction | Data |
|-----------|------|
| iCopy-X → Device | `Who\r\n` |
| Device → iCopy-X | `ISE\r\n` |
| iCopy-X → Device | `RD\r\n` |
| Device → iCopy-X | `OK\r\n` + `$A_CARD_START$` block, or `??\r\n` |

### Card Block Format

```
$A_CARD_START$
wiedata#:<binary bitstream>
Bit#:<bit count>
FC#:<facility code>
ID#:<card number>
Hex#:<raw hex padded to byte boundary>
Blk7#:<64-bit zero-padded hex>
Bits#:<binary bitstream>
$A_CARD_STOP$
```

## Files

| File | Purpose |
|------|---------|
| `icsd4.ino` | Firmware sketch |
| `memory-bank/icsd4-manual.md` | Full usage manual |

## License

PolyForm Noncommercial License 1.0.0 — see project LICENSE. For pentesting and RFID research only.
