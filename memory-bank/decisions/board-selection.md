# Development Board Selection - ATmega32U4 Pro Micro (Type-C)

Date: 2026-08-12

## Decision
Use Teyleten Robot Type-C Pro Micro ATmega32U4 5V 16MHz (Amazon B0B6HYLC44) as development platform.

## Rationale
- 5V native operation: no level shifter needed for RP10 Wiegand
- USB-C onboard: direct match for iCopy-X host port
- Native USB CDC for iCopy-X accessory enumeration
- Hardware interrupts on pins 2/3 for Wiegand
- Mature Arduino ecosystem, proven in access control
- ~$6/board (3-pack $17.99), very cost-effective

## Notes
- Product listing has contradictory description text mentioning micro-USB for programming — title and feature bullets confirm Type-C
- Clone quality varies — verify genuine ATmega32U4 chip on arrival
