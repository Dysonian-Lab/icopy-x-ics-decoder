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

## IMPORTANT: Which IPK to choose

There are **two** IPK variants in the release. They behave very differently:

| Variant | What it does | Menu item appears? |
|---------|--------------|-------------------|
| `icopy-x-ics-decoder-noflash.ipk` | Installs Python middleware + activity on **top of your existing firmware**. Does **not** flash the PM3 ARM firmware. | **NO** — the official firmware's menu does not contain "ICS Decoder". This package only adds the backend code. |
| `icopy-x-ics-decoder-flash.ipk` | Installs Python middleware **AND** flashes the PM3 ARM firmware to the iCopy-X. After flashing, the device runs our fork's firmware which has "ICS Decoder" in the menu. | **YES** — after the firmware flash completes and the device reboots. |

**If you install the no-flash IPK on the official firmware, you will NOT see "ICS Decoder" in the menu.** That is expected. You must use the **flash** variant if you want the menu item.

## Step 1: Install the flash IPK and flash the iCopy-X firmware

1. Copy `icopy-x-ics-decoder-flash.ipk` to the iCopy-X storage.
2. Connect the iCopy-X to your PC and enter **PC-Mode** (mass storage).
3. Install the package:
   ```bash
   opkg install /path/to/icopy-x-ics-decoder-flash.ipk
   ```
4. Reboot the iCopy-X.
5. After reboot, the device will detect that the PM3 firmware needs to be updated. Follow the on-screen prompts to flash:
   - Ensure the device is charged and plugged in.
   - Confirm the flash when prompted.
   - **Do not interrupt power during flashing.**
6. After flashing completes, the device will reboot again.

After the second reboot, the **ICS Decoder** entry will appear in the iCopy-X main menu (between **LUA Script** and **Settings**).

### If you already installed the no-flash IPK and want to switch

1. Install the flash IPK as above.
2. The flash process will overwrite the PM3 firmware.
3. After flashing, the menu item will appear.

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
| No "ICS Decoder" menu item after reboot | You installed the **no-flash** IPK on the official firmware. The official firmware's menu does not include "ICS Decoder". Install the **flash** IPK and complete the PM3 firmware flash. |
| IPK install fails | Confirm iCopy-X is on 1.0.90+ and has free storage |
| Pro Micro not detected by iCopy-X | Try a different USB-C cable; confirm Pro Micro power LED blinks |
| No card data displayed | Verify D0=Pin 2 (Green), D1=Pin 3 (White); check VCC/GND |
| `??` response from reader | Card format unsupported — only 26/34/35/37/48-bit Wiegand is decoded |
| Firmware upload fails | Double-tap Pro Micro reset button to enter bootloader mode |
| Serial port busy | Close other programs using the Pro Micro COM port |
| Reader not powering on | Check VCC (Red) and GND (Black) connections |