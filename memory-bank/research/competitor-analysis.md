# Competitor Analysis: iCopy-X-Community/icopyx-diy-ics-decoder

Date: 2026-08-14
Source: https://github.com/iCopy-X-Community/icopyx-diy-ics-decoder

## Overview

A working proof-of-concept Arduino-based iCS Decoder clone. Uses Teensy 3.2, HID RP10E reader, optional OLED display. Based on tcprst/wiegandDisplay project. Tested end-to-end with iCopy-X.

## Hardware

- MCU: Teensy 3.2 (ARM Cortex M4, 96MHz, 3.3V)
- Reader: HID multiCLASS SE RP10E
- Display: 128x128 SSD1327 OLED (optional)
- Enclosure: Custom 3D-printed wood-textured box

## Wiegand Implementation

- Library: WiegandNG (jpliew/Wiegand-NG-Multi-Bit-Wiegand-Library-for-Arduino)
- Pins: D0=14, D1=12
- Buffer size: 150 bits (observed max 143 with iClass readers)
- Packet gap: 15ms (25ms between packets)
- Formats decoded: 26-bit (H10301) and 34-bit (H10306) with parity validation
- Parity: Odd/even parity checks displayed but not enforced for serial output

## Protocol Implementation

- Debug serial: USB CDC at 115200 baud
- iCopy-X serial: Serial1 (hardware UART) at 9600 baud
- Commands: `Who` → `ISE`, `RD` → `OK` then async card block
- Card block format matches observed genuine device trace

## Payload Format Details

```cpp
Serial1.println("$A_CARD_START$");
Serial1.print("wiedata#:");
serial_print_bin(Serial1, card->rawbits, 0, card->bitnum);
Serial1.println();
Serial1.print("Bit#:");
Serial1.println(card->bitnum);
Serial1.print("FC#:");
Serial1.println(card->fc);
Serial1.print("ID#:");
Serial1.println(card->cn);
Serial1.print("Hex#:");
serial_print_hex(Serial1, card->rawbits + 0x2000000000 + (1<<card->bitnum), 0, 40);
Serial1.println();
Serial1.print("Blk7#:");
serial_print_hex(Serial1, card->rawbits + (1<<card->bitnum), 0, 64);
Serial1.println();
Serial1.print("Bits#:");
serial_print_bin(Serial1, card->rawbits + 0x2000000000 + (1<<card->bitnum), 0, 44);
Serial1.println();
Serial1.println("$A_CARD_STOP$");
```

Key difference: Hex# uses 40-bit field, Bits# uses 44-bit field. Both include padding arithmetic.

## USB Enumeration Workaround

Teensy enumerates as `/dev/ttyACM*`. iCopy-X expects `/dev/ttyUSB0`.
Workaround: `ln -s /dev/ttyACM1 /dev/ttyUSB0` on iCopy-X host.

## Status

Working proof-of-concept with demo video. Open questions remain about exact iCopy-X parser requirements.
