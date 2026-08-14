# Development Board Selection - ATmega32U4 Pro Micro (USB-C)

Date: 2026-08-13

## Decision
Use SparkFun Qwiic Pro Micro - USB-C (ATmega32U4) 5V/16MHz as the sole development platform.

## Rationale
- 5V native operation: no level shifter needed for RP10 Wiegand
- USB-C onboard: direct match for iCopy-X host port
- Native USB CDC for iCopy-X accessory enumeration
- Hardware interrupts on pins 2/3 for Wiegand
- Mature Arduino ecosystem, proven in access control
- Genuine SparkFun board — reliable USB enumeration, no clone issues

## Notes
- This is the only board this project supports. Do not use clones or alternative Pro Micro variants.
