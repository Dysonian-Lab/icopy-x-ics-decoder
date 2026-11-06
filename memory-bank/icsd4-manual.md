# 11/4/2026 Manual created
# iCS D4 — Benchtop Diagnostic Sniffer & iCS Decoder Accessory
## Usage Manual

**Firmware file:** `icsd4.ino`
**Target hardware:** ATmega32U4 (Arduino Leonardo / SparkFun Pro Micro USB-C)
**Wiegand pins:** D0 = pin 2, D1 = pin 3
**Serial baud:** 115200 8N1

---

## 1. Purpose

`icsd4.ino` serves a dual role:

| Role | Description |
|------|-------------|
| **Primary** | iCS Decoder accessory for the iCopy-X. Responds to `Who` → `ISE` and `RD` → `OK` + card block (or `??`), maintaining 100% reverse compatibility with the production `icsdecooderori.ino` handshake. |
| **Secondary** | Benchtop diagnostic sniffer. Captures raw Wiegand frames into an 8-slot ring buffer, streams them to a PC serial monitor in SNIFF mode, and lets an operator analyze non-standard Wiegand payloads that the iCopy-X middleware failed to parse. |

The sketch is compiled and flashed **independently** of production firmware. It does not modify `icsdecooderori.ino` or any other file.

---

## 2. Hardware

| Component | Connection |
|-----------|------------|
| MCU | SparkFun Qwiic Pro Micro USB-C (ATmega32U4) or Arduino Leonardo |
| RFID Reader | HID multiCLASS SE RP10 / RP40 |
| RP10 Red → | Pro Micro VCC (+5V) |
| RP10 Black → | Pro Micro GND |
| RP10 Green → | Pro Micro Pin 2 (Wiegand D0, INT0) |
| RP10 White → | Pro Micro Pin 3 (Wiegand D1, INT1) |
| LED | Pro Micro Pin 13 (onboard LED; blinks once per latched frame) |

Keep D0/D1 leads short (<15 cm) to preserve Wiegand timing integrity. The RP10 draws ~75 mA standby, ~100 mA peak.

---

## 3. Flashing

1. Install **SparkFun AVR Boards** via Arduino IDE Boards Manager:
   `https://raw.githubusercontent.com/sparkfun/Arduino_Boards/main/IDE_Board_Manager/package_sparkfun_index.json`
2. Select **Tools → Board → SparkFun AVR Boards → SparkFun Qwiic Pro Micro (ATmega32U4)** (or Arduino Leonardo).
3. Open `icsd4.ino`.
4. Select the correct COM port under **Tools → Port**.
5. Click **Upload**.

> **One-shot flash warning:** The Pro Micro is difficult to reflash. Verify your configuration before uploading. This sketch has not been compiled in this environment — verify with Arduino IDE before the production flash.

---

## 4. Serial Connection

- **Baud:** 115200
- **Data bits:** 8
- **Parity:** None
- **Stop bits:** 1
- **Line ending:** `\n` (newline); `\r` is accepted and stripped
- **Command buffer:** 32 bytes; lines longer than 31 characters are truncated

Open Serial Monitor at 115200 baud. Set line ending to "Both NL & CR" or "Newline".

---

## 5. Dual Modes

### BRIDGE mode (`sniffMode = false`, default)

Wiegand capture runs continuously. Completed frames are latched into the ring buffer but **not** auto-printed to serial.

- `Who` → `ISE`
- `RD` → production card block (if a valid card was captured) or `??`
- `STATUS` / `DUMP` / `CLEAR` / `BITS` / `TIMEOUT` / `MODE` / `HELP` available
- LED blinks on each latched frame

Use BRIDGE mode when the device is connected to iCopy-X and you want normal card reading with silent background capture.

### SNIFF mode (`sniffMode = true`)

Same capture and command set as BRIDGE, **plus**: every time `wgLatchFrame()` completes a frame, `printFrame()` is invoked immediately to stream the raw frame to serial in real time.

Use SNIFF mode when connected to a PC and you want to watch raw Wiegand frames as cards are presented.

Switch between modes at any time:
```
Host: MODE SNIFF
Dev : MODE SNIFF
Host: MODE BRIDGE
Dev : MODE BRIDGE
```

---

## 6. Command Reference

All commands are uppercase. Arguments are separated by a single space. No command echo. Responses end with `\r\n`.

### `WHO`
Handshake. Responds with `ISE`. Does not touch card state or the ring buffer.

```
Host: WHO
Dev : ISE
```

### `RD`
Production card read. If a captured frame is available and its bit count is in the whitelist (26, 34, 35, 37, 48), respond `OK` followed by the formatted card block. Otherwise respond `??`. Always clears card state after responding.

```
Host: RD
Dev : OK
Dev : $A_CARD_START$
Dev : wiedata#:10011001000011000000111001
Dev : Bit#:26
Dev : FC#:100
Dev : ID#:12345
Dev : Hex#:02643039
Dev : Blk7#:0000000002643039
Dev : Bits#:000000000000000000000010011001000011000000111001
Dev : $A_CARD_STOP$
```

Card payload fields:
| Field | Format | Description |
|-------|--------|-------------|
| `wiedata#:` | ASCII binary | Exact-length binary bitstream |
| `Bit#:` | Base-10 integer | Total captured bits |
| `FC#:` | Base-10 integer | Facility code / Company ID |
| `ID#:` | Base-10 integer | Card number |
| `Hex#:` | Zero-padded hex | Raw bits padded to nearest byte boundary |
| `Blk7#:` | 16-char hex | 64-bit zero-padded hex for Proxmark3 block write |
| `Bits#:` | Zero-padded binary | Zero-padded to the exact bit count (e.g. 26 chars for a 26-bit card) |

### Supported Wiegand formats for RD output:
| Format | Bits | FC field | CN field |
|--------|------|----------|----------|
| H10301 | 26 | bits 1-8 (8-bit) | bits 9-24 (16-bit) |
| Kantech / Corporate 1000 | 34 | bits 1-16 (16-bit) | bits 17-32 (16-bit) |
| Corporate 1000 | 35 | bits 1-13 (13-bit) | bits 14-33 (20-bit) |
| Corporate 1000 | 37 | bits 1-17 (17-bit) | bits 18-35 (18-bit) |
| Corporate 1000 | 48 | bits 3-24 (22-bit) | bits 25-47 (23-bit) |
| Avigilon 56-bit | 56 | bits 2-21 (20-bit) | bits 22-55 (34-bit) |

Formats not listed return `FC#:0 ID#:0` but still return `OK` with the raw `Hex#` data.

### `STATUS`
Print the most recent captured frame from the ring buffer, or `NO FRAMES` if empty.

```
Host: STATUS
Dev : $FRAME_START$
Dev : Index#: 0
Dev : Bit#: 48
...
Dev : $FRAME_STOP$
```

### `DUMP [n]`
Print a specific ring slot (0..7), or the most recent frame if no argument. Index refers to the ring slot, not a logical sequence number. Prints `EMPTY` if the ring is empty or the index is out of range.

```
Host: DUMP
Dev : $FRAME_START$   (most recent frame)
Dev : ...

Host: DUMP 3
Dev : $FRAME_START$   (ring slot 3)
Dev : ...

Host: DUMP 9
Dev : EMPTY
```

### `CLEAR`
Reset the ring buffer and live capture state. Clear production card state. Responds `CLEARED`.

```
Host: CLEAR
Dev : CLEARED
```

### `MODE BRIDGE|SNIFF`
Switch capture mode. `BRIDGE` = capture only (no auto-print). `SNIFF` = auto-print every latched frame.

```
Host: MODE SNIFF
Dev : MODE SNIFF
```

### `TIMEOUT <ms>`
Set the frame gap timeout (idle gap after which a frame is considered complete). Clamped to 5..100 ms. Default 25 ms.

```
Host: TIMEOUT 50
Dev : TIMEOUT#:50
Host: TIMEOUT 2
Dev : TIMEOUT#:5        (clamped to minimum)
Host: TIMEOUT 200
Dev : TIMEOUT#:100      (clamped to maximum)
```

### `BITS`
Report how many bits have accumulated in the live capture frame so far. Useful for checking mid-frame accumulation.

```
Host: BITS
Dev : BITS#:26
```

### `BRUTE`
Brute-force FC/CN field positions on the most recent captured frame. Tries every 8-bit FC position and every 16/20/24-bit CN position, printing decimal values. Scan the output for known card numbers (e.g. inkjet-printed on the card) to identify the correct field layout. Once found, the layout can be hardcoded into `sendCardBlock()` for production `RD` output.

```
Host: BRUTE
Dev : BRUTE - Frame 0 bits=56
Dev : RawHex=001ad0004c1b1b
Dev : BitMap: 00000000 00011010 11010000 ...
Dev : FC8 (start=value):
Dev :   0=0
Dev :   ...
Dev : CN16 (start=value):
Dev :   ...
Dev : BRUTE done
```

### `HELP` / `/?`
List every supported command, one per line. `/?` is an alias for `HELP`.

```
Host: HELP
Dev : WHO               - iCopy-X handshake
Dev : RD                - Read production card block
Dev : STATUS            - Print most recent raw frame
Dev : DUMP [n]          - Print ring slot (0-7)
Dev : CLEAR             - Reset ring buffer & live state
Dev : MODE BRIDGE|SNIFF - Toggle silent capture vs auto-print
Dev : TIMEOUT <ms>      - Set frame gap timeout (5-100ms)
Dev : BITS              - Show live bit accumulation count
Dev : BRUTE             - Brute force FC/CN field positions
Dev : HELP / /?         - Show this menu
```

### Unknown commands
Respond with `??`.

```
Host: FOOBAR
Dev : ??
```

---

## 7. Frame Output Format (`printFrame`)

Used by `STATUS`, `DUMP`, and SNIFF auto-streaming. Every line ends with `\r\n`.

```
$FRAME_START$
Index#: <ring slot, or 255 for ad-hoc calls>
Bit#: <bitCount>
Pulses#: <pulseCount>
FirstUs#: <micros() of first pulse>
LastUs#: <micros() of last pulse>
MinGapUs#: <shortest inter-pulse gap, microseconds>
MaxGapUs#: <longest inter-pulse gap, microseconds>
Overflow#: <0|1>
Bin#: <binary, MSB-first>
Hex#: <hex, lowercase, zero-padded>
Guess#: <26\|34\|35\|37\|48\|56\|64\|OTHER>
$FRAME_STOP$
```

- `Index#` is the ring slot (0..7). For SNIFF auto-streaming, this is the slot just written.
- `Overflow#` = 1 if the frame exceeded 256 bits (truncated) or if the ring buffer displaced an older frame.
- `Bin#` / `Hex#` are emitted from the **full** `bits[]` buffer (up to 256 bits), not the truncated 64-bit `cardRaw`.
- `Guess#` maps known bit counts to format names; anything else is `OTHER`.

---

## 8. Ring Buffer

- Fixed depth: 8 frames (`WgFrame ring[8]`)
- `ringHead` = next write slot; `ringCount` = number of valid frames (0..8)
- When full, the oldest slot is overwritten and `ringCount` stays at 8
- The newly latched frame receives `overflow = true` to signal a previous frame was displaced
- `STATUS` and `DUMP` read from the ring; `CLEAR` resets it

---

## 9. Workflow: Debugging a Strange SE Card

**Scenario:** iCopy-X's regular iCS Decoder cannot read a card. You want to see the raw Wiegand payload.

### Step 1: Flash `icsd4.ino`
Flash the sketch to the Pro Micro. Disconnect from iCopy-X and connect to your PC via USB.

### Step 2: Open Serial Monitor
Baud 115200, line ending "Both NL & CR".

### Step 3: Enable SNIFF mode
```
Host: MODE SNIFF
Dev : MODE SNIFF
```

### Step 4: Present the card
The RP10E reads the card and emits Wiegand pulses. After the gap timeout (default 25 ms), the frame latches and auto-streams:

```
$FRAME_START$
Index#: 0
Bit#: 56
Pulses#: 56
FirstUs#: 1234567
LastUs#: 1234589
MinGapUs#: 100
MaxGapUs#: 150
Overflow#: 0
Bin#: 11001100101010101111000011001100101010101111000011001100
Hex#: ccaaf0ccaaf0cc
Guess#: 56
$FRAME_STOP$
```

### Step 5: Analyze
- **Bit# = 56**: Outside the RD whitelist (26/34/35/37/48), so `RD` would return `??`. This explains why iCopy-X fails.
- **Bin# / Hex#**: Full raw 56-bit payload, MSB-first, nothing truncated.
- **Overflow# = 0**: Frame fit in the 256-bit buffer.
- **MinGapUs / MaxGapUs**: Timing info to spot reader anomalies.

### Step 6: Use diagnostic commands
| Command | What it tells you |
|---------|-------------------|
| `STATUS` | Re-print the most recent frame |
| `DUMP 0` | Re-print ring slot 0 |
| `DUMP 1` | Re-print ring slot 1 (previous card) |
| `CLEAR` | Wipe ring + live state |
| `MODE BRIDGE` | Stop auto-streaming (capture silently) |
| `TIMEOUT 50` | Widen gap timeout for slow readers |
| `BITS` | Check bits accumulated mid-frame |

### Step 7: What to do with the data
1. **Compare bit count** — if not 26/34/35/37/48, you now know why iCopy-X's `RD` rejects it.
2. **Extract FC/ID manually** — use the raw `Bin#`/`Hex#` to compute facility code and card number for non-standard formats.
3. **Identify the format** — `Guess#` tells you if it's 48/56/64-bit or `OTHER`.
4. **Capture multiple cards** — the 8-slot ring holds the last 8 frames; `DUMP` lets you compare them side by side.
5. **Feed to downstream tools** — the raw `Bin#`/`Hex#` output is machine-parseable for future Lua scripts or plugins.

---

## 10. Workflow: Using with iCopy-X (Production Mode)

Connect the Pro Micro to iCopy-X via USB-C. The device enumerates as a USB CDC serial port.

```
iCopy-X → Device: Who\r\n
Device → iCopy-X: ISE\r\n

iCopy-X → Device: RD\r\n
Device → iCopy-X: OK\r\n + $A_CARD_START$...$A_CARD_STOP$   (or ??\r\n)
```

In BRIDGE mode, this behaves exactly like production `icsdecooderori.ino`. Frames are still captured into the ring buffer silently. You can later connect to a PC, switch to SNIFF mode, and use `STATUS`/`DUMP` to review what was captured — no need to re-present the card.

---

## 11. Limitations

| Limitation | Details | Workaround |
|------------|---------|------------|
| **64-bit RD truncation** | `RD` reconstructs only the low 64 bits into `cardRaw`. Frames >64 bits are truncated and fail the whitelist (26/34/35/37/48), so `RD` returns `??`. | Use `STATUS`, `DUMP [n]`, or SNIFF mode to view the full `bits[]` array via `Bin#`/`Hex#`. |
| **32-bit cardId truncation** | Fixed: `cardId` is now `uint64_t` with custom `printUint64Dec()` output. 34-bit CN values up to 17 billion are handled without truncation. | N/A — fixed in firmware. |
| **Ring depth 8** | Only the last 8 frames are retained. Older frames are displaced. | Use `CLEAR` frequently; capture one card at a time for analysis. |
| **256-bit capture limit** | `liveBits` holds 32 bytes = 256 bits max. Frames longer than 256 bits set `liveOverflow = true` and stop accepting bits. | Use `Overflow#` to detect truncation. |
| **One flash** | Pro Micro is difficult to reflash. Verify before uploading. | Test thoroughly with Arduino IDE Serial Monitor before the production flash. |

---

## 12. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| No response to `Who` | Wrong baud, wrong port, device not enumerated | Check Serial Monitor at 115200; verify COM port; press Pro Micro reset |
| `RD` returns `??` for a known card | Card bit count not in whitelist (26/34/35/37/48), or no card captured yet | Present card; check `BITS`; use `STATUS`/`DUMP` to see raw bits |
| Serial garbage / no output | Wrong line ending, wrong baud | Set line ending to "Both NL & CR"; verify 115200 baud |
| `Overflow#: 1` | Frame >256 bits or ring displaced an older frame | Frame truncated; use diagnostic output for partial data |
| LED doesn't blink | `loop()` not latching frames | Verify Wiegand wiring (D0=pin2, D1=pin3); check reader power |

---

## 13. Files

| File | Purpose |
|------|---------|
| `icsd4.ino` | Firmware sketch (this manual's subject) |
| `icsdecooderori.ino` | Production firmware (NOT modified by this sketch) |
| `benchtop-diagnostic-plan.md` | Implementation plan this firmware was built from |

---

**License:** PolyForm Noncommercial License 1.0.0 — see project LICENSE. For pentesting and RFID research only.
