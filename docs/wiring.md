# Wiring Diagram — ICS Decoder

## Components
- **MCU:** Teyleten Robot Type-C Pro Micro ATmega32U4 5V 16MHz
- **RFID Reader:** HD RP10 125kHz (Wiegand output)
- **Power:** USB-C from iCopy-X or host

## RP10 Pinout (standard Wiegand)
| RP10 Wire | Color | Function |
|-----------|-------|----------|
| Pin 1     | Red   | VCC (+5V) |
| Pin 2     | Black | GND |
| Pin 3     | Green | D0 (Data 0) |
| Pin 4     | White | D1 (Data 1) |

## Pro Micro Connections
| Pro Micro Pin | RP10 Wire | Description |
|---------------|-----------|-------------|
| VCC           | Red       | +5V power to reader |
| GND           | Black     | Common ground |
| Pin 2 (INT0)  | Green     | Wiegand D0 |
| Pin 3 (INT1)  | White     | Wiegand D1 |

## ASCII Diagram
```
                 USB-C
                   |
             +-----+-----+
             |  iCopy-X   |
             +-----+-----+
                   | VBUS 5V
                   |
        +----------+----------+
        |                     |
    +---+---+             +---+---+
    | Pro   |             |  HD   |
    | Micro |             | RP10  |
    |       |             |       |
    | VCC o--------------o Red   |
    | GND o--------------o Black |
    | D2  o--------------o Green |  (Wiegand D0)
    | D3  o--------------o White |  (Wiegand D1)
    |       |             |       |
    +---+---+             +---+---+
        |                     |
       GND                  GND
```

## Notes
- The Pro Micro and RP10 share a common ground — required for reliable Wiegand signaling.
- 5V is supplied from USB VBUS. The RP10 draws ~75mA standby, ~100mA peak.
- No level shifter is needed; RP10 Wiegand output is 5V-tolerant and matches ATmega32U4 logic levels.
- Keep D0/D1 leads short (<15cm) to preserve Wiegand timing integrity.
