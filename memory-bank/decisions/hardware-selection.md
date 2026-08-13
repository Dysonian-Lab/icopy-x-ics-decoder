# Hardware Selection Decision

Date: 2026-08-12

## Context
- Target Device: iCopy-X (lab-401/icopy-x open firmware)
- RFID Reader: HD RP10 (125kHz Wiegand output)
- Requirement: Serial-over-USB interface responding to "Who" and "RD" commands

## Decision
Arduino Nano (ATmega328P) is **NOT suitable** due to lack of native USB CDC.
Selected: Teyleten Robot Type-C Pro Micro ATmega32U4 5V 16MHz (Amazon B0B6HYLC44)

## Rationale
- iCopy-X requires USB enumeration as a CDC serial device
- ATmega328P relies on external USB-UART bridge (CH340/FTDI) which cannot act as a USB device
- ATmega32U4 has native USB support for CDC
- 5V native operation matches RP10 Wiegand logic levels — no level shifter needed
- USB-C onboard matches iCopy-X host port
- ~$6/board (3-pack $17.99), very cost-effective
