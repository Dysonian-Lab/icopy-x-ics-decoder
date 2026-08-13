# Wiring Diagram — ICS Decoder

## Components
- **MCU:** Teyleten Robot Type-C Pro Micro ATmega32U4 5V 16MHz
- **RFID Reader:** HD RP10 multiCLASS SE
- **Host:** iCopy-X via USB-C

## Schematic

![Wiring Schematic](images/wiring-schematic.svg)

## Pro Micro Pinout

![Pro Micro Pinout](images/pro-micro-pinout.svg)

## RP10 Wiegand Interface

| RP10 Wire | Color | Function |
|-----------|-------|----------|
| Pin 1 | Red | VCC (+5V) |
| Pin 2 | Black | GND |
| Pin 3 | Green | D0 (Data 0) |
| Pin 4 | White | D1 (Data 1) |

## Pro Micro Connections

| Pro Micro Pin | RP10 Wire | Description |
|---------------|-----------|-------------|
| VCC | Red | +5V power to reader |
| GND | Black | Common ground |
| Pin 2 (D0, INT0) | Green | Wiegand D0 |
| Pin 3 (D1, INT1) | White | Wiegand D1 |

## Notes
- The Pro Micro and RP10 share a common ground — required for reliable Wiegand signaling.
- 5V is supplied from USB VBUS. The RP10 draws ~75mA standby, ~100mA peak.
- No level shifter is needed; RP10 Wiegand output is 5V-tolerant and matches ATmega32U4 logic levels.
- Keep D0/D1 leads short (<15cm) to preserve Wiegand timing integrity.
- The RP10 must be configured to output Wiegand format for iCLASS SE/SEOS card data.
