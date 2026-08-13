# Build Instructions — ICS Decoder Firmware

## Prerequisites
- Windows 10/11 with PowerShell
- Arduino IDE 2.x installed
- USB-C cable to connect Pro Micro to PC

## 1. Install Board Support
1. Open Arduino IDE
2. Go to **File → Preferences → Additional Boards Manager URLs**
3. Add:
   ```
   https://raw.githubusercontent.com/arduino/ArduinoCore-avr/master/boards.txt
   ```
   *(ATmega32U4 Pro Micro boards are typically included with AVR core. If not, install via Boards Manager: search for "SparkFun Pro Micro" or "AVR by Arduino".)*

4. Go to **Tools → Board → AVR Boards → Arduino Leonardo**
   *(The Pro Micro ATmega32U4 uses the same core as Leonardo.)*

## 2. Connect Hardware
1. Wire the HD RP10 to the Pro Micro per `docs/wiring.md`
2. Plug the Pro Micro into your PC via USB-C
3. Verify the device enumerates as a COM port in Device Manager

## 3. Upload Firmware
1. Open `firmware/wiegand-sniffer/wiegand-sniffer.ino` in Arduino IDE
2. Select the correct COM port under **Tools → Port**
3. Click **Upload**
4. Wait for "Done Uploading"

## 4. Test the Sniffer
1. Open **Tools → Serial Monitor** (or use a terminal like PuTTY)
2. Set baud rate to **115200** and line ending to **Both NL & CR**
3. Present a 125kHz Wiegand card to the RP10 reader
4. You should see output like:
   ```
   Wiegand Sniffer Ready
   Present a 125kHz card to the HD RP10 reader...
   Bits: 26
   Raw:  00000010000000000111100101100110111001000001
   FC#:  203
   ID#:  14112
   Hex#: 2007966e41
   ---
   ```

## 5. Troubleshooting
| Symptom | Cause | Fix |
|---------|-------|-----|
| No serial output | Wrong COM port or baud rate | Check Device Manager, set 115200 |
| Garbled characters | Wrong line ending setting | Set Serial Monitor to "Both NL & CR" |
| Spurious bits | Wiring noise / long leads | Shorten D0/D1 wires, check grounds |
| No card read | Reader not powered | Verify 5V on RP10 Red wire, check USB power |

## 6. Next Steps
Once the sniffer captures valid Wiegand data, proceed to Phase 3:
- Implement the `Who` / `ISE` handshake
- Implement the `RD` command handler with card payload formatting
