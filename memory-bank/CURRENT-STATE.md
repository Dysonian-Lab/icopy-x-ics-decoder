# CURRENT STATE � 2026-08-17

## Where We Are
- RP10E reader received and ready
- SparkFun Pro Micro USB-C ordered, awaiting delivery
- Both firmware files compile cleanly
- Protocol spec confirmed from genuine iCS Decoder documentation
- Developer Q&A done � mostly "I don't know" but spec is now confirmed from other sources
- Final plan: build in Dysonian-Lab/icopy-x fork, PR upstream when working

## Confirmed Architecture
- RP10 and RP40 are BOTH HID multiCLASS SE readers. They output the SAME Wiegand for a given card; RP10 is just a smaller footprint. There is NO special secure-element SEOS path in the RP10E that the RP40 lacks.
- The earlier "RP10E integrated secure element outputs decoded SEOS credentials" claim (PROJECT-PLAN L22 / prior CURRENT-STATE) is CONTRADICTED by architecture research AND by hardware testing. Disregard it.
- Architecture research (2026-08-13): "No security/decryption on the bridge � iCopy-X host handles all processing." The reader emits the card's PACS credential on Wiegand; iCopy-X does the cloning.
- Pro Micro captures Wiegand and bridges to iCopy-X via USB CDC serial � it is a pure Wiegand?USB bridge.
- Protocol: `Who`/`ISE` handshake, `RD`/`OK`+card block or `??`
- Payload format confirmed with exact field specifications

## What To Do When Pro Micro Arrives

### Step 1: Wire It
- RP10E Red ? Pro Micro VCC
- RP10E Black ? Pro Micro GND
- RP10E Green ? Pro Micro Pin 2 (D0, INT0)
- RP10E White ? Pro Micro Pin 3 (D1, INT1)
- USB-C cable from Pro Micro to PC

### Step 2: Test Wiegand Sniffer
- Open `firmware/wiegand-sniffer/wiegand-sniffer.ino` in Arduino IDE
- Upload to Pro Micro
- Open Serial Monitor at 115200 baud
- Present a known Wiegand card
- **Verify:** LED blinks, bit count shown, FC# and ID# decode
- **Critical:** Document which bit formats the RP10E outputs for iCLASS SE/SEOS cards

### Step 3: Test Protocol
- Open `firmware/ics-decoder/ics-decoder.ino`
- Upload to Pro Micro
- Open Serial Monitor at 115200 baud
- Type `Who` ? should see `ISE`
- Present card ? LED should blink
- Type `RD` ? should see `OK` + `$A_CARD_START$...$A_CARD_STOP$` block, OR `??`
- Verify output matches confirmed spec (byte-boundary Hex#, 64-bit Blk7#, 48-bit Bits#)

### Step 4: Test With iCopy-X
- Connect Pro Micro to iCopy-X USB-C host port
- Check if iCopy-X detects it
- If not: check `/dev/ttyACM*` and `/dev/ttyUSB0` on iCopy-X
- Test full card read flow

### Step 5: Open Firmware Integration
- Implement `src/middleware/ics_decoder.py` in Dysonian-Lab/icopy-x fork
- Register `IClassSEActivity` in `src/lib/actmain.py`
- Extend activity with device detection and serial I/O
- Add menu entry in `src/screens/main_menu.json`
- Test on iCopy-X running open firmware

## Key Files
- `PROJECT-PLAN.md` � full project plan
- `README.md` � project README with confirmed protocol spec
- `firmware/ics-decoder/ics-decoder.ino` � production decoder firmware
- `firmware/wiegand-sniffer/wiegand-sniffer.ino` � debug sniffer
- `memory-bank/research/protocol-specification.md` � confirmed protocol spec
- `memory-bank/research/competitor-analysis.md` � competitor code analysis
- `memory-bank/research/open-firmware-integration.md` � iCopy-X integration points
- `memory-bank/research/developer-qa.md` � developer Q&A responses

## Debugging Notes (2026-08-26)

### Wiegand Sniffer � WORKING
- RP40 (multiCLASS SE, 5�16V) confirmed as a functioning reader. Beeps + red?green LED = successful card read; it emits standard 26-bit Wiegand on Green(D0)/White(D1).
- Pro Micro taps Green?pin2 (D0), White?pin3 (D1), Black?GND, Red?VCC. Board is 5V-tolerant; RP40 powered at 5V from Micro VCC works.
- Sniffer captures 26-bit frames correctly: FC (8-bit) + ID (16-bit). Example reads: FC 78/ID 46574, FC 210/ID 57892.

### CRITICAL: Flash with the reader DISCONNECTED
- **Do NOT flash the Pro Micro while the RP40 (or any reader) is soldered/connected.** Uploads fail with `avrdude: butterfly_recv(): programmer is not responding` and can leave the board in a stuck, non-enumerating state that *looks* like a brick (COM port vanishes).
- Recovery: desolder/disconnect the reader, flash, then reconnect. The board is NOT damaged � it was a flash-time conflict, not hardware.
- Never blame the USB cable first; a known-good setup still fails if the reader is attached during upload.

### Reader behavior � CORRECTED (2026-08-26)
- RP10 and RP40 are equivalent multiCLASS SE readers: same Wiegand output for a given card, RP10 just smaller. No special SEOS path in either.
- For an iCLASS SE/SEOS card, the reader emits the card's legacy Wiegand "downgrade" credential (e.g. 48-bit) � THAT is what the iCS Decoder forwards to iCopy-X. This is a DOWNGRADE COPY, not a true clone: iCopy-X writes it to a legacy iCLASS/Picopass or T5577 blank. A real SEOS-to-SEOS clone would need the keysets (not achievable). So the RP40 reads SEOS cards fine; it is NOT legacy-only. (Ref: memory-bank/research/seos-protocol-analysis.md L46-49)
- The Micro is a pure Wiegand?USB-CDC bridge (README "How It Works"); it forwards whatever the reader places on D0/D1.
- ics-decoder.ino payload format matches README confirmed spec: simple zero-padding, NO `+0x2000000000 + (1<<bitnum)` flags (README L76-81 explicit). Verified against 26-bit example.
- RESOLVED: the RP40/RP10 emit a **48-bit** Wiegand frame for an iCLASS SE/SEOS card (captured via sniffer: `Bits: 48`, raw `100000000001111011000010000000000000101001111010`). Added 48-bit to the accepted format set in both ics-decoder.ino and wiegand-sniffer.ino. FC#/ID# left 0 (no confirmed 48-bit FC/ID layout); the full 48 bits pass through Hex# (12 hex, byte-boundary) / Blk7# (16 hex, 64-bit) / Bits# (48) / wiedata# � that is what iCopy-X clones.
- VERIFIED (2026-08-26): ics-decoder.ino `RD` returns a clean 48-bit block for the SEOS card � `Hex#:801ec2000a7a`, `Blk7#:0000801ec2000a7a` (matches raw 48 bits). Next: end-to-end DOWNGRADE test on iCopy-X writing `Blk7#` to a legacy iCLASS/Picopass or T5577 blank (NOT a SEOS card).

## Firmware Integration Scope (2026-08-26) � THE ACTUAL DELIVERABLE

The Arduino bridge is DONE. The project's real work is two firmware integrations:

### 1. iceman Proxmark3 client/device FW v4.21611 (LOCAL: `D:\kilocode\Phosphor-debug\proxmark3-4.21611`)
- This is the "client FW". It has all downgrade-write primitives but NO `icsdecoder` command.
- Primitives available (confirmed in code/CHANGELOG):
  - `hf iclass encode --bin <raw PACS binary> --ki 0` ? writes credential to Picopass (iCLASS legacy) card (`cmdhficlass.c`)
  - `wiegand decode --bin <raw>` + `lf hid clone -w c1k48s --fc .. --cn ..` ? T5577 (`cmdlft55xx.c`, `cmdwiegand.c`)
  - `armsrc/wiegand.c:244` supports up to 48-bit
- `doc/hid_downgrade.md` is the authoritative downgrade method; the "weaponized HID reader" section is exactly our DIY decoder case.
- TODO: add an `icsdecoder` glue command (or rely on iCopy-X driving existing `hf iclass encode`).

### 2. iCopy-X open firmware (NOT CLONED LOCALLY)
- Repos (from cridential.txt): `uaih3k9x/icopy-x-nightly` (user's fork), `lab-401/icopy-x`, `Dysonian-Lab/icopy-x-ics-decoder`
- Needs: implement `IclassSEActivity` (stub at `src/lib/activity_main.py:7997`) + `src/middleware/ics_decoder.py`
  - detect Pro Micro decoder (CDC ACM `/dev/ttyACM*`), send Who/RD, parse `wiedata#`/`Bits#`, drive pm3 `hf iclass encode --bin <bits> --ki 0`
- NOT on disk � must clone before editing.

### Real data flow
`RP40 ? Pro Micro (ics-decoder.ino, DONE) ? [Who/RD] ? $A_CARD_START$ Bits#:<48-bit> ? iCopy-X IclassSEActivity parses wiedata# ? pm3 hf iclass encode --bin <48-bit> --ki 0 ? Picopass/T5577 blank ? reader opens (downgrade, not a true SEOS clone).`

### IMPLEMENTED & PUSHED (2026-08-27)
- `src/middleware/ics_decoder.py` CREATED � detect_decoder() (scans /dev/ttyACM*/ttyUSB* + COM1-256 fallback), read_card() (Who/RD protocol), parse_block(), write_to_card() -> iclasswrite.make_se_data(blk7) + writeDataBlocks(ICLASS_LEGACY, key 2020666666668888).
- `src/lib/activity_main.py` � IclassSEActivity stub REPLACED with working impl (detect on create, 500ms poll via actstack root.after, background write via startBGTask, UI draw + onKeyEvent M1/PWR finish, M2/OK clear).
- `src/lib/actmain.py` � added `'iclass_se': ('activity_main','IclassSEActivity')` to _ACTIVITY_REGISTRY.
- `src/screens/main_menu.json` � added "ICS Decoder" menu entry (`"icon": null`, matched actual format).
- `icopy-x-ics-decoder` repo � ics-decoder.ino + wiegand-sniffer.ino synced with 48-bit SEOS support + header comments.
- Pushed: icopy-x `372259e..ad1f0c7 main`, icopy-x-ics-decoder `8c6d8a7..e198f1f main`. Token stripped from .git/config.

### Assumptions made by implementer (verify on device)
- Serial port scan: consolidated Linux to /dev/ttyACM*+/dev/ttyUSB*; macOS to /dev/cu.usbmodem*+/dev/cu.usbserial*; Windows COM1-256 fallback.
- main_menu.json entry used `"icon": null` (actual file format), not "script".
- IClassSEActivity UI y-coords (60/90/110/170) inferred from 240x240 screen + _constants.py (CONTENT_Y0=40, BTN_BAR_Y0=200), matching PCModeActivity/SniffActivity pattern.
- These are the spots most likely to need a tweak when tested on real hardware.

### Outdated research note
- `memory-bank/research/icopy-x-repo-analysis.md` claims "a 125 kHz Wiegand bridge is NOT an iCLASS SE/SEOS decoder." This is CONTRADICTED by the actual code: the icopy-x-ics-decoder repo self-describes as reading iCLASS SE/SEOS via RP10 over Wiegand USB-CDC, and iclasswrite.make_se_data(blk7) consumes our Wiegand-derived Blk7#. SEOS cards emit a legacy Wiegand downgrade credential (seos-protocol-analysis.md / hid_downgrade.md); the Wiegand bridge captures exactly that. The approach is valid.

## How To Resume
  1. Open this folder: `D:\kilocode\icsdecoder`
2. Read `README.md` for the confirmed protocol spec
3. Read `PROJECT-PLAN.md` and `memory-bank/CURRENT-STATE.md`
4. Check `firmware/` for the two Arduino sketches
5. Continue from Step 1 above depending on what hardware is available
## Release Preparation Status (2026-08-29)

### Completed
- Built no-flash IPK from Dysonian-Lab/icopy-x repo: icopy-x-ics-decoder-noflash.ipk (11.5 MB)
- Created ICS-Decoder-specific install documentation: docs/INSTALL.md
- Updated README.md with confirmed protocol spec and field specifications
- Synced firmware files with 48-bit SEOS support

### Remaining
- Build Arduino firmware hex for Pro Micro
- Upload IPK and hex to GitHub releases


## Release v0.1.0 (2026-08-29)

- Built no-flash IPK: icopy-x-ics-decoder-noflash.ipk
- Built Pro Micro firmware hex: release/ics-decoder-firmware.hex (sparkfun:avr:promicro)
- Created install guide: docs/INSTALL.md
- Uploaded to GitHub releases: https://github.com/Dysonian-Lab/icopy-x-ics-decoder/releases/tag/v0.1.0
- Assets: icopy-x-ics-decoder-noflash.ipk (11.5 MB) + ics-decoder-firmware.hex (19 KB)
## Session Recovery Notes (2026-08-29)

### Available Tools (VERIFIED WORKING)
- gcc 8.1.0 (x86_64-posix-seh-rev0, MinGW-W64)
- g++ 8.1.0 (x86_64-posix-seh-rev0, MinGW-W64)
- mingw32-make 4.2.1 (GNU Make)
- Python 3.11.6
- git 2.55.0.windows.5
- bash 5.3.9 (GNU bash, MSYS2/MinGW)
- WSL 2 available
- arduino-cli installed in WSL at /home/owner/bin/arduino-cli
- PlatformIO NOT installed
- Docker NOT installed
- GitHub CLI (gh) NOT installed

### Completed Work (DO NOT REDO)
- No-flash IPK built: D:\kilocode\icopy-x\icopy-x-ics-decoder-noflash.ipk
- Arduino hex built: D:\kilocode\icsdecoder\release\ics-decoder-firmware.hex
- Install doc: D:\kilocode\icsdecoder\docs\INSTALL.md
- GitHub release v0.1.0 uploaded to Dysonian-Lab/icopy-x-ics-decoder
- Release URL: https://github.com/Dysonian-Lab/icopy-x-ics-decoder/releases/tag/v0.1.0

### Next Steps (if any work remains)
- Test the IPK on actual iCopy-X hardware
- Verify Pro Micro firmware works with RP10/RP40
- Tweak IClassSEActivity UI coordinates if needed on real device

## Docker Build Complete (2026-08-30)

- Built matching PM3 client + firmware inside ubuntu:16.04 Docker container
- ARM Linux client: D:\kilocode\icopy-x\build\proxmark3 (4.2 MB, PM3ICOPYX platform)
- ARM firmware: D:\kilocode\icopy-x\res\firmware\pm3\fullimage.elf (336 KB)
- Lua scripts: D:\kilocode\icopy-x\build\lua.zip (iceman Lua 5.4, 300 KB)
- Flash IPK built: D:\kilocode\icopy-x\icopy-x-ics-decoder-flash.ipk (12.7 MB)
- Uploaded to GitHub releases alongside no-flash IPK and Pro Micro artifacts
