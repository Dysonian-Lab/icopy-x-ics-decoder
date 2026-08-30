# ICS Decoder Project Plan

## Goal
Build a DIY iCS Decoder for the iCopy-X using a SparkFun Pro Micro USB-C and HID RP10E reader, then integrate support for both the genuine Lab401 iCS Decoder and our DIY version into the open-source iCopy-X firmware (Dysonian-Lab/icopy-x fork).

## Current Status
- RP10E reader received and ready
- SparkFun Qwiic Pro Micro USB-C (ATmega32U4) ordered, awaiting delivery
- Open firmware analyzed: dormant `IClassSEActivity` stub found, needs registration + implementation
- Protocol reverse-engineering incomplete — competitor's implementation is best-guess mimic, not verified against genuine hardware
- Developer answers received: mostly "I don't know" — no genuine iCS Decoder was available for testing

## What We Know About the Protocol

### Confirmed
- **Host → Device:** `Who\r\n` and `RD\r\n` commands
- **Device → Host:** `ISE\r\n` response to `Who`
- **Device → Host:** `OK\r\n` followed by `$A_CARD_START$...$A_CARD_STOP$` block, OR `??\r\n` if no card
- **Payload fields:** `wiedata#`, `Bit#`, `FC#`, `ID#`, `Hex#`, `Blk7#`, `Bits#`
- **Line endings:** `\r\n` confirmed from trace
- **Wiegand formats observed:** 26-bit and 34-bit (competitor's samples)
- **RP10E iCLASS SE/SEOS capability:** Confirmed — RP10E has integrated secure element that handles iCLASS SE/SEOS crypto internally and outputs decoded credentials as Wiegand pulses. No external SAM required.

### Unconfirmed / Needs Verification
- **Baud rate:** Competitor uses 9600 on hardware UART; our USB CDC will negotiate with host
- **Payload padding:** Competitor uses `rawbits + 0x2000000000 + (1<<bitnum)` for `Hex#` and `Bits#` — may be parser quirk vs artifact
- **Field widths:** Exact widths vs zero-padded tolerance unknown
- **Second `RD` behavior:** Repeat last card or `??`?
- **Parity validation:** Required for parsing or display-only?
- **USB VID/PID:** Any CDC ACM accepted, or specific device IDs required?
- **Serial timeout:** How long does iCopy-X wait for response?

### What We Don't Know Yet
- Genuine iCS Decoder's exact payload format for iCLASS SE/SEOS cards
- Exact Wiegand bit formats produced by RP10E for iCLASS SE/SEOS (26-bit, 34-bit, etc.)
- Whether the open firmware can detect our CDC ACM device without custom code

## Hardware Plan

### Our DIY Decoder
- **MCU:** SparkFun Qwiic Pro Micro - USB-C (ATmega32U4) 5V/16MHz
- **Reader:** HID multiCLASS SE RP10E
- **Connection:** USB-C to iCopy-X USB-C host port
- **Power:** USB VBUS 5V, RP10E draws ~75mA standby, ~100mA peak
- **Wiring:**
  - RP10E Red → Pro Micro VCC
  - RP10E Black → Pro Micro GND
  - RP10E Green → Pro Micro Pin 2 (D0, INT0)
  - RP10E White → Pro Micro Pin 3 (D1, INT1)
- **Form factor:** No display — matches original iCS Decoder aesthetic

### Test Equipment Needed
- Logic analyzer or USB sniffer to capture genuine iCS Decoder traffic (if available)
- USB-C cables, Dupont wires, breadboard
- Y OTG cable for iCopy-X testing

## Firmware Plan

### Pro Micro Firmware (`firmware/ics-decoder/ics-decoder.ino`)
**Status: Compiles, needs hardware validation**

Current features:
- Wiegand ISR capture on pins 2/3 with 25ms timeout
- Supports 26/34/35/37-bit Wiegand formats
- LED blink on card capture (pin 13)
- USB CDC serial at 115200 baud
- `Who` → `ISE` handshake
- `RD` → `OK` + card block OR `??`
- Graceful fallback for unsupported bit counts

**When board arrives, test in this order:**
1. Upload `wiegand-sniffer/wiegand-sniffer.ino` — verify RP10E captures Wiegand bits
2. Present known 26-bit Wiegand card — verify LED blinks and Serial Monitor shows FC/ID
3. Upload `ics-decoder/ics-decoder.ino` — verify `Who`/`RD` protocol over USB CDC
4. Connect to iCopy-X — test end-to-end

**Potential firmware changes after testing:**
- Adjust `BIT_TIMEOUT_MS` if RP10E timing differs
- Add parity validation if iCopy-X requires it
- Add payload padding if parser requires it
- Adjust supported bit formats based on RP10E output
- Tweak baud rate if needed

### Open Firmware Integration (Dysonian-Lab/icopy-x)

#### Phase 1: Middleware (`src/middleware/ics_decoder.py`)
Create new middleware module with:
- `detect_decoder()` — scan `/dev/ttyUSB0` and `/dev/ttyACM*` for iCS Decoder devices
- `open_decoder(port)` — open serial connection
- `handshake()` — send `Who\r\n`, expect `ISE\r\n`
- `read_card()` — send `RD\r\n`, parse response
- `parse_card_block(text)` — extract `$A_CARD_START$...$A_CARD_STOP$` into structured data
- `close_decoder()` — cleanup

#### Phase 2: Activity Registration
- **File:** `src/lib/actmain.py`
- Register `IClassSEActivity` in `_ACTIVITY_REGISTRY`
- Add to main menu

#### Phase 3: Activity Implementation
- **File:** `src/lib/activity_main.py` (extend existing stub at line ~7997)
- Implement device detection on activity start
- Show "Detecting..." / "Not found" states
- Poll decoder for cards on user action
- Display card data (CSN, FC, ID, bit format)
- Handle device hotplug

#### Phase 4: Menu Entry
- **File:** `src/screens/main_menu.json`
- Add "iCS Decoder" or "SE Decoder" menu item

## Testing Strategy

### Stage 1: Wiegand Validation (No iCopy-X needed)
1. Wire RP10E to Pro Micro
2. Upload `wiegand-sniffer.ino`
3. Present cards and verify:
   - LED blinks on each read
   - Serial Monitor shows correct bit count
   - FC# and ID# decode correctly
   - 26-bit format works
   - 34-bit format works (if you have such cards)
4. Document which Wiegand formats the RP10E actually outputs for iCLASS SE/SEOS

### Stage 2: Protocol Validation (No iCopy-X needed)
1. Upload `ics-decoder.ino`
2. Open Serial Monitor at 115200 baud
3. Type `Who` — verify `ISE` response
4. Present card — verify LED blinks
5. Type `RD` — verify `OK` + card block OR `??`
6. Compare output format with competitor's trace

### Stage 3: iCopy-X Integration
1. Connect Pro Micro to iCopy-X via USB-C
2. Power iCopy-X and Pro Micro
3. Check if iCopy-X detects the device
4. If not detected, check `/dev/ttyACM*` and `/dev/ttyUSB0` on iCopy-X
5. Test `Who`/`RD` handshake from iCopy-X side
6. Verify card data displays correctly on iCopy-X screen

### Stage 4: Open Firmware Integration
1. Implement middleware and activity in fork
2. Deploy to iCopy-X running open firmware
3. Test device detection
4. Test end-to-end card read flow
5. Compare with genuine iCS Decoder if available

## Protocol Capture Plan

We know the RP10E handles iCLASS SE/SEOS crypto internally and outputs Wiegand. What we still need to verify is the protocol between our Pro Micro and the iCopy-X:

### Option A: Borrow Genuine iCS Decoder
- Contact Lab401 or community members
- Capture USB traffic with Wireshark/usbmon
- Compare payload formats with our implementation

### Option B: Test Against Factory Firmware
- If you have factory firmware on a spare iCopy-X or can borrow one
- Test our Pro Micro with symlink workaround
- Capture what the factory firmware expects

### Option C: Iterative Testing
- Start with our best-guess implementation
- Test against iCopy-X, observe behavior
- Adjust protocol based on results
- This is the most likely path forward

## Open Questions to Answer Through Testing

1. **What Wiegand bit formats does RP10E produce for iCLASS SE/SEOS?** 26-bit, 34-bit, or other lengths?
2. **Does open firmware enumerate our CDC ACM device?** Or only FTDI `/dev/ttyUSB0`?
3. **What does iCopy-X send to the decoder?** Just `Who`/`RD`, or more?
4. **How does iCopy-X parse the payload?** Does padding matter? Field widths?
5. **What happens on repeated `RD`?** Same card or `??`?
6. **What baud rate does genuine device use?** 9600? 115200? Other?

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Open firmware rejects CDC ACM devices | Medium | High | Test enumeration first; may need FTDI adapter or custom descriptors |
| Protocol mismatch with iCopy-X | High | Medium | Iterative testing; capture traffic if possible |
| iCopy-X USB-C power insufficient | Low | Medium | Test with powered USB-C hub if needed |
| Genuine device uses different protocol entirely | Low | High | Need protocol capture from real hardware |

## Next Actions (In Order)

1. **Wait for Pro Micro delivery**
2. **Upload `wiegand-sniffer.ino`** — verify RP10E Wiegand output
3. **Document RP10E behavior** — what formats, what cards work
4. **Upload `ics-decoder.ino`** — verify USB CDC and protocol
5. **Test with iCopy-X** — does it detect the device?
6. **Implement open firmware integration** — middleware + activity + menu
7. **Capture protocol traffic** if genuine device becomes available
8. **Iterate based on test results**

## Milestones
1. Pro Micro arrives and is wired — ready for firmware testing
2. Wiegand sniffer validates RP10E output format
3. Protocol layer validated over USB CDC
4. First successful iCopy-X detection and handshake
5. Open firmware integration complete and tested
6. PR submitted to Dysonian-Lab/icopy-x

## Cost
- SparkFun Pro Micro USB-C: ~$24
- HID RP10E reader: ~$20
- Wiring/breadboard: ~$5
- **Total: ~$49** (vs $475 genuine)
