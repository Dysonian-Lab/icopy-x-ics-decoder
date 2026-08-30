# iCS Decoder Protocol Specification (Confirmed)

Source: Reverse-engineered from iCopy-X firmware + genuine iCS Decoder behavior
Date: 2026-08-17

## Handshake

Host → Device: `Who\r\n`
Device → Host: `ISE\r\n`

## Card Polling

Host → Device: `RD\r\n`
Device → Host: `??\r\n` (no card)
Device → Host: `OK\r\n` + card block (card present)

## Payload Format

```
$A_CARD_START$
wiedata#:<RAW_BINARY_STREAM>
Bit#:<BIT_COUNT>
FC#:<FACILITY_CODE>
ID#:<CARD_NUMBER>
Hex#:<RAW_HEX_PAYLOAD>
Blk7#:<64BIT_HEX_PADDING>
Bits#:<48BIT_ALIGNED_BINARY>
$A_CARD_STOP$
```

## Field Specifications

| Field | Format | Description |
|-------|--------|-------------|
| `wiedata#:` | ASCII binary | Exact-length binary string matching Wiegand bit count |
| `Bit#:` | Base-10 integer | Total captured bits (26, 34, 35, 37, etc.) |
| `FC#:` | Base-10 integer | Facility code (0 if format has no FC field) |
| `ID#:` | Base-10 integer | Card number |
| `Hex#:` | Zero-padded hex | Raw bits padded to byte boundary |
| `Blk7#:` | 16-char hex | 64-bit zero-padded hex for Proxmark3 block write |
| `Bits#:` | 48-char binary | Left-padded to 48 characters |

## Example: 26-bit H10301

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

## Implementation Notes

- Line endings: `\r\n`
- Blk7# is always 16 hex chars (64 bits) regardless of actual bit count
- Bits# is always 48 binary chars, left-padded with zeros
- Hex# is byte-boundary padded: 26 bits → 8 hex chars, 34 bits → 10 hex chars
- FC# outputs 0 for formats without a facility code field
- Protocol strings (`Who`, `ISE`, `RD`, `$A_CARD_START$`, etc.) are iCopy-X firmware conventions, not HID standards

## Reference Implementations

- Competitor: https://github.com/iCopy-X-Community/icopyx-diy-ics-decoder
- Open firmware stub: `src/lib/activity_main.py:7997-8017` in lab-401/icopy-x
