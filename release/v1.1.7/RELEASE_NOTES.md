# Release Notes for v1.1.7-ics

## Base Upstream
- Lab401 v1.1.7 (merge commit f2c05e1)

## Upstream Additions
- int(raw_blk7, 16) != 0 zero-guard
- Added ics_credentials.py
- Added ics_info_view.py
- Base64 raw response capture
- Wiegand-26 parity verification

## Preserved Custom Features
- Thread serialization (_pm3_lock)
- Serial auto-discovery (/dev/ttyUSB*, ttyACM0 exclusion)
- Debug logging hooks

## Package Type
- Host-side No-Flash IPK (requires prior PM3 v4.23346 flash base)

## Verification
- 32/32 PM3 command audit PASS
