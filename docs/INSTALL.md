# iCopy-X ICS Decoder — Install Guide

## What this provides

The ICS Decoder package adds card-reading capabilities to your iCopy-X open firmware setup:

- **ICS Decoder menu item** — new entry in the iCopy-X main menu
- **Serial bridge middleware** — translates between iCopy-X UI and Pro Micro firmware
- **Pro Micro firmware** — Wiegand decoder running on the ATmega32U4

## Prerequisites

- iCopy-X updated to firmware **1.0.90** or later
- **SparkFun Qwiic Pro Micro USB-C** (ATmega32U4, 5V/16MHz)
- **HID RP10** or **RP40** multiCLASS SE reader
- USB-C cable (Pro Micro ? iCopy-X host port)

## Wiring

Connect the RP10/RP40 reader to the Pro Micro using the 4-wire Wiegand cable:

| Wire | Color | Pro Micro Pin | Function |
|------|-------|---------------|----------|
| VCC  | Red   | VCC           | Power    |
| GND  | Black | GND           | Ground   |
| D0   | Green | Pin 2 (INT0)  | Wiegand Data 0 |
| D1   | White | Pin 3 (INT1)  | Wiegand Data 1 |

## Step 1: Install the IPK on iCopy-X (no-flash variant)

1. Copy `icopy-x-ics-decoder-noflash.ipk` to the iCopy-X storage.
2. Connect the iCopy-X to your PC and enter **PC-Mode** (mass storage).
3. Install the package via the iCopy-X package manager or SSH:
   ```bash
   opkg install /path/to/icopy-x-ics-decoder-noflash.ipk
   ```
4. Reboot the iCopy-X if prompted.

After reboot, a new **ICS Decoder** entry appears in the iCopy-X menu.

## Step 2: Flash the Pro Micro with the provided .hex

> **CRITICAL: Disconnect the RP10/RP40 reader from the Pro Micro BEFORE flashing.** Leaving the reader connected can cause flashing failures or damage.

### Option A — Arduino IDE

1. Install **SparkFun AVR Boards** via Board Manager.
2. Select **Board:** SparkFun Qwiic Pro Micro USB-C.
3. Set **Processor:** ATmega32U4 (5V, 16MHz).
4. Open the provided sketch in Arduino IDE.
5. Connect the Pro Micro to your PC via USB-C.
6. Select the correct COM port.
7. Click **Upload**.

### Option B — avrdude (command line)

```bash
avrdude -patmega32u4 -cavr109 -PCOM3 -b57600 -D -Uflash:w:ics-decoder-firmware.hex:i
```

Replace `COM3` with your Pro Micro's serial port.

## Step 3: Connect and use the ICS Decoder

1. **Reconnect** the RP10/RP40 reader to the Pro Micro (wiring from the table above).
2. Plug the Pro Micro into the **iCopy-X USB host port** via USB-C.
3. On the iCopy-X, navigate to **Menu > ICS Decoder**.
4. Present a card to the reader — decoded data appears on screen.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| IPK install fails | Confirm iCopy-X is on 1.0.90+ and has free storage |
| Pro Micro not detected by iCopy-X | Try a different USB-C cable; confirm Pro Micro power LED blinks |
| No card data displayed | Verify D0=Pin 2 (Green), D1=Pin 3 (White); check VCC/GND |
| `??` response from reader | Card format unsupported — only 26/34/35/37/48-bit Wiegand is decoded |
| Firmware upload fails | Double-tap Pro Micro reset button to enter bootloader mode |
| Serial port busy | Close other programs using the Pro Micro COM port |
| Reader not powering on | Check VCC (Red) and GND (Black) connections |