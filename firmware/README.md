# Firmware

## Directories

- `wiegand-sniffer/` — Debug tool for validating Wiegand capture from the RP10
- `ics-decoder/` — Production firmware for iCS Decoder emulation

## ics-decoder

Production firmware that emulates the Lab401 iCS Decoder for the iCopy-X.

### Protocol

| Direction | Data |
|-----------|------|
| iCopy-X → Device | `Who\r\n` |
| Device → iCopy-X | `ISE\r\n` |
| iCopy-X → Device | `RD\r\n` |
| Device → iCopy-X | `OK\r\n` + `$A_CARD_START$` block, or `??\r\n` |

### Card Payload Format

```
$A_CARD_START$
wiedata#:<binary bits>
Bit#:<bit count>
FC#:<facility code>
ID#:<card number>
Hex#:<hex value>
Blk7#:<64-bit hex>
Bits#:<48-bit padded binary>
$A_CARD_STOP$
```

### Hardware

- MCU: ATmega32U4 Pro Micro (5V 16MHz)
- RFID: HD RP10 via Wiegand D0/D1
- USB: CDC serial to iCopy-X
