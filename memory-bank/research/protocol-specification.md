# iCS Decoder Protocol Specification

Date: 2026-08-13

## Source
Developer notes from doegox (RFID researcher, Proxmark3 contributor) via private communication.

## Status
Protocol confirmed by reverse-engineering trace from genuine iCopy-X + iCS Decoder pair. Implementation validated by developer's working serial bridge.

## Discovery
- Host sends: `Who\r\n`
- Device responds: `ISE\r\n`

## Read Command
- Host sends: `RD\r\n`
- Device responds with either:
  - `OK\r\n` followed by card payload block
  - `??\r\n` if no badge present or error

## Card Payload Format
```
$A_CARD_START$
wiedata#:<binary bitstream>
Bit#:<bit count>
FC#:<facility code>
ID#:<card number>
Hex#:<hex value>
Blk7#:<64-bit hex>
Bits#:<48-bit padded binary>
$A_CARD_STOP$
```

## Example Output
```
$A_CARD_START$
wiedata#:11100101100110111001000001
Bit#:26
FC#:203
ID#:14112
Hex#:2007966e41
Blk7#:0000000007966e41
Bits#:00000010000000000111100101100110111001000001
$A_CARD_STOP$
```

## Hardware Details
- Uses HID Multiclass SE RP10E reader
- RP10 reads iCLASS SE/SEOS cards via 13.56 MHz interface
- RP10 outputs card data in Wiegand format on D0/D1
- Pro Micro captures Wiegand bits and formats payload
- Device enumerates as USB CDC serial to iCopy-X

## Implementation Notes
- Developer implemented a working serial bridge based on trace analysis
- Developer does not have a genuine iCS Decoder for further validation
- No other commands beyond Who/RD are known
- Baud rate and VID/PID of genuine device are unknown

## Notes
- Exact protocol is proprietary and closed-source
- No public documentation exists from Lab401 or iCopy-X manufacturer
- Must be validated with USB protocol capture of genuine iCopy-X + iCS Decoder pair
