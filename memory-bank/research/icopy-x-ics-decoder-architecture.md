# iCS Decoder Hardware Architecture Research

Date: 2026-08-12

## Source
Amazon product B0B6HYLC44 (Teyleten Robot Type-C Pro Micro ATmega32U4) — used as reference platform.

## Findings
- Commercial iCS Decoder is a Wiegand-to-USB-C bridge dongle
- MCU likely uses ATmega32U4 or similar with native USB, or USB-to-UART bridge + simple MCU
- No security/decryption on the bridge — iCopy-X host handles all processing
- Power: 5V from USB-C VBUS, LDO regulation, ESD protection
- RP10 reader draws ~75mA standby, 100mA peak

## Implications for Clone
- ATmega32U4 Pro Micro is viable replacement
- 5V logic matches RP10 Wiegand directly — no level shifting needed
- Protocol verification still required before firmware implementation
