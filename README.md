# iCopy-X iCS Decoder

Firmware and middleware to emulate the Lab401 iCS Decoder for the iCopy-X. Reads iCLASS SE / iCLASS SEOS cards via the HD RP10 reader and presents them to the iCopy-X as a USB CDC serial accessory.

## How It Works

### Hardware Layer (ICS Decoder Dongle)
1. RP10 reads iCLASS SE / iCLASS SEOS card via 13.56 MHz interface
2. For SEOS cards: Performs ISO 7816 handshake, challenge-response auth, and EAX decryption
3. Outputs decrypted PACS payload via USB serial ($A_CARD_START$...$A_CARD_STOP$)

### Middleware Layer (iCopy-X)
1. Parses SIO PACS payload with NN right-shift bit extraction
2. Extracts FC/CN from 26-bit Wiegand frame
3. Auto-detects target blank type (HF iClass or LF T5577)
4. Writes credential to blank via PM3 executor

## SEOS SIO Parsing (Black Hat Asia 2025)

SEOS cards do NOT expose credential data in plaintext. The ICS Decoder hardware performs the full cryptographic handshake and decryption.

### NN Right-Shift Extraction

**Format:** `[NN] [Payload Bytes]`
- `NN` = number of trailing zero padding bits (byte 0)
- Right-shift bitstream by NN bits, then parse 26-bit Wiegand frame

**26-bit Wiegand Frame (H10301):**
```
[P_even (1b)] [FC (8b)] [CN (16b)] [P_odd (1b)]
```

**Extraction:**
```python
shift_nn = payload[0]
bitstream = int.from_bytes(payload[1:], byteorder="big")
shifted = bitstream >> shift_nn
fc = (shifted >> 17) & 0xFF      # Facility Code
cn = (shifted >> 1) & 0xFFFF     # Card Number
```

### ASN.1 TLV Container

If decoder outputs raw container (Tag 0x85):
```python
if data[0] == 0x85:
    length = data[1]
    data = data[2:2 + length]
# Then apply NN right-shift as above
```

## Dual-Frequency Target Support

| Target | Frequency | Card Types | Detection | Write Method |
|--------|-----------|------------|-----------|--------------|
| HF iClass | 13.56 MHz | Picopass 2k/16k, Magic iClass | `hf iclass rdbl` | `hf iclass wrbl` |
| LF T5577 | 125 kHz | T5577 (HID Prox) | `lf t55xx detect` | `lf hid clone -w H10301 --fc --cn` |

### HF Write (iClass)
- Uses `iclasswrite.writeDataBlocks()` → `hf iclass wrbl`
- Writes Block 7 (PACS credential) to legacy iClass/Picopass blanks

### LF Write (T5577)
- Uses `lf hid clone -w H10301 --fc {fc} --cn {cn}`
- Lets Proxmark3 handle H10301 framing and parity calculation natively
- **Do NOT use `lf hid clone -r` with manual bit-packing** - causes corrupted cards

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
SIO#:<decrypted PACS payload with NN prefix>
SIO_CONTAINER#:<raw ASN.1 TLV container>
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
| `SIO#:` | Hex string | Decrypted PACS payload with NN padding byte |
| `SIO_CONTAINER#:` | Hex string | Raw ASN.1 TLV container (Tag 0x85) |

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

### Example SEOS SIO Output

```
$A_CARD_START$
Blk7#:00000000029D6BDD
SIO#:061B7D0040
FC#:78
ID#:46574
$A_CARD_STOP$
```

In this example:
- `SIO#:061B7D0040` - Decrypted PACS payload with NN=6 padding bits
- After right-shift by 6: `0x029D6BDD` (26-bit Wiegand frame with parity)
- FC = `(0x029D6BDD >> 17) & 0xFF` = 78
- CN = `(0x029D6BDD >> 1) & 0xFFFF` = 46574

## Build Instructions

### Prerequisites

- Windows 10/11, macOS, or Linux
- Arduino IDE 2.x or PlatformIO
- USB-C cable to connect Pro Micro to PC

### Arduino IDE

1. Install **SparkFun AVR Boards** via Boards Manager (add `https://raw.githubusercontent.com/sparkfun/Arduino_Boards/main/IDE_Board_Manager/package_sparkfun_index.json` in Preferences)
2. Select **Tools → Board → SparkFun AVR Boards → SparkFun Qwiic Pro Micro (ATmega32U4)**
3. Open `firmware/ics-decoder/ics-decoder.ino`
4. Select the correct COM port under **Tools → Port**
5. Click **Upload**

### PlatformIO

```bash
pio run -t upload
```

## iCopy-X Middleware Integration

The iCopy-X middleware (`src/middleware/ics_decoder.py`) handles:

1. **Serial Communication** - Detects ICS Decoder via USB serial
2. **SIO Parsing** - Extracts FC/CN from SEOS PACS payload
3. **Target Detection** - Auto-detects HF iClass or LF T5577 blanks
4. **Write Routing** - Routes to appropriate PM3 write command

### Key Functions

| Function | Purpose |
|----------|---------|
| `detect_decoder()` | Scan serial ports for ICS Decoder |
| `read_card(ser)` | Send RD command, read card block |
| `parse_block(text)` | Parse $A_CARD_START$...$A_CARD_STOP$ block |
| `extract_and_shift_wiegand(data)` | Unified NN right-shift + Wiegand parsing |
| `detect_target()` | Auto-detect target type (HF/LF) |
| `write_to_card(blk7)` | Write to HF iClass blank |
| `write_to_t5577(fc, cn)` | Write to LF T5577 blank |

### PM3 Commands Used

| Command | Purpose |
|---------|---------|
| `hf iclass rdbl --blk 00 -k 2020666666668888` | Detect HF iClass blank |
| `hf iclass wrbl --blk {b} -d {data} -k {key}` | Write block to iClass |
| `lf t55xx detect` | Detect LF T5577 blank |
| `lf hid clone -w H10301 --fc {fc} --cn {cn}` | Clone HID Prox to T5577 |

**IMPORTANT:** `hf iclass info` HANGS on iCopy-X hardware (FPGA mismatch) - DO NOT USE

## Development

### Directory Structure

```
├── firmware/
│   ├── ics-decoder/       # Production iCS Decoder firmware
│   └── wiegand-sniffer/   # Debug tool for validating Wiegand capture
├── src/
│   └── middleware/
│       └── ics_decoder.py # iCopy-X middleware (SIO parsing + write routing)
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
