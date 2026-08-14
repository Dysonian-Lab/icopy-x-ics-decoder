# iCS Decoder Hardware Architecture Research

Date: 2026-08-13

## Findings
- Commercial iCS Decoder is a Wiegand-to-USB-C bridge dongle
- MCU uses ATmega32U4 with native USB CDC
- No security/decryption on the bridge — iCopy-X host handles all processing
- Power: 5V from USB-C VBUS, LDO regulation, ESD protection
- RP10 reader draws ~75mA standby, 100mA peak

## Platform
- SparkFun Qwiic Pro Micro - USB-C (ATmega32U4) 5V/16MHz
- 5V logic matches RP10 Wiegand directly — no level shifting needed
- Protocol verification still required before firmware finalization
