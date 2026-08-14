# Build Instructions — ICS Decoder Firmware

## Prerequisites
- Windows 10/11, macOS, or Linux
- Arduino IDE 2.x or PlatformIO
- USB-C cable to connect SparkFun Qwiic Pro Micro to PC

## 1. Install Board Support

1. Open Arduino IDE
2. Go to **File → Preferences → Additional Boards Manager URLs**
3. Add:
   ```
   https://raw.githubusercontent.com/sparkfun/Arduino_Boards/master/IDE_Board_Manager/package_sparkfun_index.json
   ```
4. Go to **Tools → Board → Boards Manager**
5. Search for **SparkFun AVR Boards** and install
6. Go to **Tools → Board → SparkFun AVR Boards → SparkFun Qwiic Pro Micro (ATmega32U4)**

## 2. Connect Hardware

1. Wire the HD RP10 to the SparkFun Qwiic Pro Micro per `docs/wiring.md`
2. Plug the Pro Micro into your PC via USB-C
3. Verify the device enumerates as a COM port in Device Manager

## 3. Upload Firmware

1. Open `firmware/wiegand-sniffer/wiegand-sniffer.ino` in Arduino IDE
2. Select the correct COM port under **Tools → Port**
3. Click **Upload**

## 4. Test the Sniffer

1. Open **Tools → Serial Monitor** (or use a terminal like PuTTY)
2. Set baud rate to **115200** and line ending to **Both NL & CR**
3. Present an iCLASS SE/SEOS card to the RP10 reader
4. You should see output like:
   ```
   Wiegand Sniffer v2
   Present a card to the HD RP10 reader...
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

## 5. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Board not detected | USB driver issue | Install SparkFun drivers or use Device Manager to update |
| Upload fails / timeout | Bootloader window | Press reset just before upload |
| COM port not found | Driver issue | Install SparkFun drivers |
| No serial output | Wrong COM port or baud rate | Check Device Manager, set 115200 |
| Garbled characters | Wrong line ending setting | Set Serial Monitor to "Both NL & CR" |
| Spurious bits | Wiring noise / long leads | Shorten D0/D1 wires, check grounds |
| No card read | Reader not powered | Verify 5V on RP10 Red wire, check USB power |

## 6. Next Steps

Once the sniffer captures valid Wiegand data, flash the production firmware:
- `firmware/ics-decoder/ics-decoder.ino` — Complete Who/ISE/RD protocol implementation
