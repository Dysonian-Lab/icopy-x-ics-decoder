# Build Instructions — ICS Decoder Firmware

## Prerequisites
- Windows 10/11 with PowerShell
- Arduino IDE 2.x installed
- USB-C cable to connect Pro Micro to PC
- **5.1kΩ resistors** for USB-C power modification (required for iCopy-X compatibility)

## 1. Hardware Modification — USB-C Power Fix

**CRITICAL:** These Pro Micro clones do not properly signal as a USB-C sink. The iCopy-X will not supply 5V unless the board has 5.1kΩ pull-down resistors on both CC pins.

Before soldering the RP10, modify the Pro Micro:

1. Locate the USB-C connector's CC1 and CC2 pins
2. Solder a 5.1kΩ resistor from CC1 to GND
3. Solder a 5.1kΩ resistor from CC2 to GND
4. Do NOT short CC1 and CC2 together

Without this modification, the board will not power when connected to the iCopy-X.

## 2. Install Board Support

1. Open Arduino IDE
2. Go to **File → Preferences → Additional Boards Manager URLs**
3. Add:
   ```
   https://raw.githubusercontent.com/sparkfun/Arduino_Boards/master/IDE_Board_Manager/package_sparkfun_index.json
   ```
4. Go to **Tools → Board → Boards Manager**
5. Search for **SparkFun Pro Micro** and install
6. Go to **Tools → Board → SparkFun AVR Boards → SparkFun Pro Micro (5V 16MHz)**

**Note:** These boards are SparkFun Pro Micro clones, not genuine Arduino. The SparkFun board package is required for proper USB enumeration.

## 3. Connect Hardware

1. Wire the HD RP10 to the Pro Micro per `docs/wiring.md`
2. Verify the USB-C modification is complete
3. Plug the Pro Micro into your PC via USB-C
4. Verify the device enumerates as a COM port in Device Manager

## 4. Upload Firmware

1. Open `firmware/wiegand-sniffer/wiegand-sniffer.ino` in Arduino IDE
2. Select the correct COM port under **Tools → Port**
3. Click **Upload**

**Note:** Some clones have a 2-second upload window after reset. If upload fails, try:
- Press reset on the board just before clicking Upload
- Select the correct processor: **Tools → Processor → ATmega32U4 (5V 16MHz)**

## 5. Test the Sniffer

1. Open **Tools → Serial Monitor** (or use a terminal like PuTTY)
2. Set baud rate to **115200** and line ending to **Both NL & CR**
3. Present a 125kHz Wiegand card to the RP10 reader
4. You should see output like:
   ```
   Wiegand Sniffer v2
   Present a 125kHz card to the HD RP10 reader...
   ---
   Bits: 26
   Raw:  00000010000000000111100101100110111001000001
   FC#:  203
   ID#:  14112
   Hex#: 2007966e41
   Blk7#: 0000000007966e41
   Bits#: 00000010000000000111100101100110111001000001
   ---
   ```

## 6. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Board not detected | USB-C CC pins not modified | Add 5.1kΩ resistors on CC1 and CC2 |
| Board shows as CH340 | Wrong/fake USB chip | This board is not a true ATmega32U4; replace with genuine SparkFun Pro Micro |
| Upload fails / timeout | 2-second bootloader window | Press reset just before upload, or use AVR programmer |
| COM port not found | Driver issue | Install SparkFun drivers or use Device Manager to update |
| No serial output | Wrong COM port or baud rate | Check Device Manager, set 115200 |
| Garbled characters | Wrong line ending setting | Set Serial Monitor to "Both NL & CR" |
| Spurious bits | Wiring noise / long leads | Shorten D0/D1 wires, check grounds |
| No card read | Reader not powered | Verify 5V on RP10 Red wire, check USB power |

## 7. Next Steps

Once the sniffer captures valid Wiegand data, flash the production firmware:
- `firmware/ics-decoder/ics-decoder.ino` — Complete Who/ISE/RD protocol implementation
