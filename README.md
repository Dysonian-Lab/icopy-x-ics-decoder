# iCopy-X iCS Decoder

Firmware to emulate the Lab401 iCS Decoder for the iCopy-X. Reads iCLASS SE / iCLASS SEOS cards via the HD RP10 reader and presents them to the iCopy-X as a USB CDC serial accessory.

## How It Works

1. RP10 reads iCLASS SE / iCLASS SEOS card via its 13.56 MHz interface
2. RP10 outputs card data in Wiegand format on D0/D1
3. ATmega32U4 captures Wiegand bits and extracts Facility Code / Card Number
4. ATmega32U4 formats the card payload and sends it to the iCopy-X over USB-C

## Hardware

| Component | Details |
|-----------|---------|
| MCU | SparkFun Qwiic Pro Micro - USB-C (ATmega32U4) 5V/16MHz |
| RFID Reader | HID multiCLASS SE RP10 / RP40 |
| Connection | USB-C to iCopy-X |

> **Note:** The SparkFun Qwiic Pro Micro has native USB-C and requires no hardware modification.

## Wiring

![Wiring Schematic](docs/images/wiring-schematic.svg)

### Pro Micro Pinout

![Pro Micro Pinout](docs/images/pro-micro-pinout.svg)

| Pro Micro Pin | RP10 Wire | Function |
|---------------|-----------|----------|
| VCC | Red | +5V power to reader |
| GND | Black | Common ground |
| Pin 2 (D0, INT0) | Green | Wiegand D0 |
| Pin 3 (D1, INT1) | White | Wiegand D1 |

> Keep D0/D1 leads short (<15 cm) to preserve Wiegand timing integrity. The RP10 draws ~75 mA standby, ~100 mA peak.

## Protocol

The device enumerates as a USB CDC serial port. The iCopy-X communicates with a simple text protocol:

| Direction | Data |
|-----------|------|
| iCopy-X → Device | `Who\r\n` |
| Device → iCopy-X | `ISE\r\n` |
| iCopy-X → Device | `RD\r\n` |
| Device → iCopy-X | `OK\r\n` + `$A_CARD_START$` block, or `??\r\n` |

### Card Payload Format

```
$A_CARD_START$
wiedata#:<binary bitstream>
Bit#:<bit count>
FC#:<facility code>
ID#:<card number>
Hex#:<raw hex padded to byte boundary>
Blk7#:<64-bit zero-padded hex>
Bits#:<48-bit left-padded binary>
$A_CARD_STOP$
```

### Field Specifications

| Field | Format | Description |
|-------|--------|-------------|
| `wiedata#:` | ASCII binary | Exact-length binary string matching Wiegand bit count |
| `Bit#:` | Base-10 integer | Total captured bits (26, 34, 35, 37, etc.) |
| `FC#:` | Base-10 integer | Facility code (0 if format has no FC field) |
| `ID#:` | Base-10 integer | Card number |
| `Hex#:` | Zero-padded hex | Raw bits padded to nearest byte boundary |
| `Blk7#:` | 16-char hex | 64-bit zero-padded hex for Proxmark3 block write |
| `Bits#:` | 48-char binary | Left-padded with zeros to 48 characters |

### Padding Notes

- **No artificial bit insertion is used.** Some reverse-engineered implementations add extra padding bits (`+0x2000000000 + (1<<bitnum)`) to Hex# and Bits# fields. This is **not required** by the iCopy-X parser. The confirmed format uses simple zero-padding only.
- `Hex#` is padded to the nearest byte boundary: 26 bits → 8 hex chars, 34 bits → 10 hex chars
- `Blk7#` is always 16 hex chars (64 bits), zero-padded on the left
- `Bits#` is always 48 binary chars, zero-padded on the left

### Example Output (26-bit H10301)

```
$A_CARD_START$
wiedata#:10011001000011000000111001
Bit#:26
FC#:100
ID#:12345
Hex#:02643039
Blk7#:0000000002643039
Bits#:000000000000000000000010011001000011000000111001
$A_CARD_STOP$
```

## Build Instructions

### Prerequisites

- Windows 10/11, macOS, or Linux
- Arduino IDE 2.x or PlatformIO
- USB-C cable to connect Pro Micro to PC

### Arduino IDE

1. Install **SparkFun AVR Boards** via Boards Manager (add `https://raw.githubusercontent.com/sparkfun/Arduino_Boards/master/IDE_Board_Manager/package_sparkfun_index.json` in Preferences)
2. Select **Tools → Board → SparkFun AVR Boards → SparkFun Qwiic Pro Micro (ATmega32U4)**
3. Open `firmware/ics-decoder/ics-decoder.ino`
4. Select the correct COM port under **Tools → Port**
5. Click **Upload**

### PlatformIO

```bash
pio run -t upload
```

## Development

### Directory Structure

```
├── firmware/
│   ├── ics-decoder/       # Production iCS Decoder firmware
│   └── wiegand-sniffer/   # Debug tool for validating Wiegand capture
├── docs/
│   ├── build-instructions.md
│   └── wiring.md
├── memory-bank/            # Project research, decisions, progress
└── README.md
```

### Firmware Variants

- **`ics-decoder`** — Production firmware implementing the complete Who/ISE/RD protocol
- **`wiegand-sniffer`** — Debug tool that outputs raw Wiegand data to Serial Monitor for validation

## License

PolyForm Noncommercial License 1.0.0 — see [LICENSE](LICENSE).

## Disclaimer

This project is for pentesting and RFID research purposes only. The iCS Decoder protocol is proprietary and reverse-engineered. This software cannot be used in a commercial context.
