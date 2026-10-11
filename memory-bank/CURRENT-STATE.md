# ICS DECODER - CURRENT STATE (2026-09-01)

## LATEST BUILD: v1.0-ICS (commit e70b5dd)

---

## NON-26-BIT LF GUARD (commit e70b5dd)

### Problem
Raw `lf hid clone -r` fallback for 48-bit SEOS payloads produces unreadable
125 kHz LF cards because extended SIO is structured for HF memory.

### Fix
- `write_to_t5577()` returns False for non-26-bit formats (no raw fallback)
- `_do_write()` blocks LF writes when fc=0/cn=0 and shows "Non-26b SIO!"
- WAIT_BLANK shows "Incompatible: Requires HF iClass" for LF with non-26b
- Stops polling timers before write to prevent serial port collisions
- Retry in STATE_RESULT uses retained `_source_data` without re-scanning

### Target Handling Rules

| Credential Type | Detected Blank | Action |
|-----------------|----------------|--------|
| Standard 26-bit (fc > 0, cn > 0) | LF T5577 | Execute `lf hid clone -w H10301 --fc {fc} --cn {cn}` |
| Standard 26-bit (fc > 0, cn > 0) | HF iClass | Execute `hf iclass wrbl` (Block 7) |
| Extended/Custom (fc == 0, cn == 0) | LF T5577 | Block write -> Show: "Incompatible: Requires HF iClass" |
| Extended/Custom (fc == 0, cn == 0) | HF iClass | Execute `hf iclass wrbl` (Block 7 raw 8-byte copy) |

## T5577 WRITE BUG FIX (commit 3d228e3)

### Problem
Writing to T5577 produced corrupted cards:
- **Input:** FC: 78, CN: 46574 (from Block 7: 0x029D6BDD)
- **Output:** FC: 4, CN: 2579191 (corrupted!)

### Root Cause
The old code used:
```python
raw = (FC << 16) | CN  # = 0x4EB5EE
cmd = 'lf hid clone -r {}'.format(raw)
```

**`lf hid clone -r` expects the FULL 26-bit frame WITH parity bits pre-calculated** (which is the Block 7 value `0x029D6BDD`), NOT the unshifted payload `0x4EB5EE`.

Passing `0x4EB5EE` to `-r` caused Proxmark3 to interpret it as a corrupted/extended frame, producing wrong FC/CN.

### Fix
Changed to let Proxmark3 handle H10301 framing natively:
```python
cmd = 'lf hid clone -w H10301 --fc {} --cn {}'.format(fc, cn)
```

The `-w H10301` flag tells PM3 to:
1. Calculate even parity (bit 25)
2. Calculate odd parity (bit 0)
3. Frame the 26-bit Wiegand format correctly

### Verification
| Step | Old (Broken) | New (Fixed) |
|------|--------------|-------------|
| Input | FC=78, CN=46574 | FC=78, CN=46574 |
| Command | `lf hid clone -r 4EB5EE` | `lf hid clone -w H10301 --fc 78 --cn 46574` |
| T5577 Result | FC=4, CN=2579191 (WRONG) | FC=78, CN=46574 (CORRECT) |

---

## DEVELOPER QUESTIONS & SHIFT MATH CLARIFICATION

### Questions Asked (from cridential.txt)

**Payload Format:**
> Q3: The padding you apply to Hex#/Bits# (rawbits + 0x2000000000 + (1<<bitnum)) — is that padding required by the iCopy-X parser, or just an artifact of how you assembled the string?

> Q4: Do the fields need to be exactly the widths you send, or will the iCopy-X accept zero-padded values?

**Wiegand Handling:**
> Q5: Did the RP10E ever produce anything other than 26/34-bit frames for iCLASS SE/SEOS?

> Q6: Did parity validation matter for iCopy-X parsing, or was it just for display purposes?

> Q7: Did you encounter bit-length negotiation or format detection issues?

### Developer Responses

- Q3-Q4: "I'm just mimicking the official icsd, i don't know how the official fw is parsing it"
- Q5: "i don't know. i have just a handful of samples, there is zero iclass in EU"
- Q6: "cf 3" (same as Q3 - unknown)
- Q7: "it worked with my fw samples, that's all i know"

### Current Understanding (From Arduino Code in cridential.txt)

The original developer's Wiegand parsing logic:

**26-bit Wiegand:**
```cpp
facilityCode = (capturedBits >> 17) & 0xFF;  // 8-bit FC
cardId = capturedBits & 0xFFFF;               // 16-bit CN (NO shift!)
```

**34-bit Wiegand:**
```cpp
facilityCode = (capturedBits >> 1) & 0x3FFFF;  // 18-bit FC
cardId = capturedBits & 0x1FFFFFF;              // 25-bit CN (NO shift!)
```

**IMPORTANT DISCREPANCY:** The original code does NOT right-shift CN by 1. It uses:
- 26-bit: `CN = capturedBits & 0xFFFF` (lower 16 bits directly)
- 34-bit: `CN = capturedBits & 0x1FFFFFF` (lower 25 bits directly)

This differs from the SIO PACS NN right-shift method where:
- `shifted = bitstream >> NN`
- `CN = (shifted >> 1) & 0xFFFF`

### Two Different Bit Extraction Methods

| Method | Use Case | FC Extraction | CN Extraction |
|--------|----------|---------------|---------------|
| Direct Wiegand | Raw Wiegand from RP10E reader | `(bits >> 17) & 0xFF` | `bits & 0xFFFF` |
| SIO PACS NN Shift | Decrypted SEOS SIO payload | `(shifted >> 17) & 0xFF` | `(shifted >> 1) & 0xFFFF` |

**Key Insight:** The SIO PACS method requires the NN right-shift FIRST because the payload has trailing padding bits. Raw Wiegand does NOT need this because the bits are already aligned.

### Open Questions Still Unanswered

1. **Padding format** - Is `rawbits + 0x2000000000 + (1<<bitnum)` required or just mimicking?
2. **Field widths** - Does iCopy-X require exact widths or accept zero-padded?
3. **Frame types** - Does RP10E produce non-26/34-bit frames for SE/SEOS?
4. **Parity validation** - Required for parsing or just display?
5. **Bit-length negotiation** - Any format detection issues?

---

## SE-TO-LEGACY DOWNGRADE ATTACK

### Purpose
Read Block 7 / PACS data from HID SEOS/SE cards via USB serial decoder, then write to legacy iClass/Picopass (HF) or T5577 (LF) blanks via PM3 coil.

### Attack Flow
```
1. User places SEOS/SE source tag on USB decoder (NOT coil)
2. ICS Decoder hardware performs:
   - ISO 7816 ADF selection (00 A4 04 00...)
   - Challenge-response mutual authentication
   - EAX/EAX' decryption with diversified KDF key
   - Outputs decrypted PACS payload via serial
3. iCopy-X middleware parses SIO payload:
   - Extracts NN padding byte
   - Applies right bit-shift (>> NN)
   - Parses 26-bit Wiegand frame (FC + CN)
4. User removes source, places legacy blank on PM3 coil
5. Firmware auto-detects blank type (HF or LF)
6. Firmware writes credential to blank using appropriate method
7. Blank now clones the PACS credential from the SE source
```

---

## SIO WIEGAND PARSING (Black Hat Asia 2025 - Iceman & evildaemond)

### Architecture: Division of Labor

**ICS Decoder Dongle (Hardware/Firmware):**
- Manages physical RF communication (ISO 14443A / ISO 7816 APDUs)
- Executes mutual authentication challenge-response and session key derivation
- Decrypts the AEAD container using internal SAM/keyset
- Transmits decrypted data block via serial ($A_CARD_START$...$A_CARD_STOP$)

**iCopy-X Middleware (ics_decoder.py):**
- Consumes serial stream from USB bridge
- Checks for raw decrypted SIO payload or ASN.1 TLV structure
- Extracts padding count (NN), applies right bit-shift, unpacks Wiegand frame
- Routes parsed bits to iclasswrite.py (HF) or lfhidwrite.py (LF)

### NN Right-Shift Bit Extraction

**SIO PACS Format:** `[NN] [Payload Bytes]`
- `NN` = number of trailing zero padding bits (byte 0)
- `Payload Bytes` = Wiegand data (bytes 1..N)

**Extraction Algorithm:**
```python
# 1. Read shift count from first byte
shift_nn = payload[0]

# 2. Convert remaining bytes to big-endian integer
bitstream = int.from_bytes(payload[1:], byteorder="big")

# 3. Right-shift out trailing padding bits
shifted_bits = bitstream >> shift_nn

# 4. Parse 26-bit Wiegand frame (H10301)
fc = (shifted_bits >> 17) & 0xFF      # Facility Code (8 bits)
cn = (shifted_bits >> 1) & 0xFFFF     # Card Number (16 bits)
p_even = (shifted_bits >> 25) & 0x01  # Even parity bit
p_odd = shifted_bits & 0x01           # Odd parity bit
```

**26-bit Wiegand Frame (H10301):**
```
[P_even (1b)] [FC (8b)] [CN (16b)] [P_odd (1b)]
   Bit 25      Bits 17-24   Bits 1-16     Bit 0
```

### ASN.1 TLV Container Handling

**Tag 0x85 Container Format:**
```
[0x85] [Length] [Cipher Bytes + 16-byte MAC]
```

**Parsing Logic:**
```python
if data[0] == 0x85:
    length = data[1]
    data = data[2:2 + length]
# Then apply NN right-shift as above
```

### Unified Parsing Function

**`extract_and_shift_wiegand(payload_bytes)`** - Single function handles:
- Raw decrypted payloads: `[NN] [Payload]`
- ASN.1 TLV containers: `[0x85] [Length] [Data]`

Returns: `{"valid": bool, "fc": int, "cn": int, "shifted_hex": str}`

---

## DUAL-FREQUENCY TARGET SUPPORT

### Target Comparison

| Target | Frequency | Card Types | Detection | Write Method |
|--------|-----------|------------|-----------|--------------|
| HF iClass | 13.56 MHz | Picopass 2k/16k, Magic iClass | `hf iclass rdbl --blk 00` | `iclasswrite.writeDataBlocks()` → `hf iclass wrbl` |
| LF T5577 | 125 kHz | T5577 (HID Prox emulation) | `lf t55xx detect` | `lf hid clone -r <raw_hex>` |

### HF Write Details
- **Data:** Block 7 (PACS credential, 16 hex chars)
- **Method:** `iclasswrite.writeDataBlocks()` → `hf iclass wrbl` via PM3 executor
- **Key:** `2020666666668888` (default legacy key)
- **Blocks:** 6, 7, 8, 9 (SE data blocks)

### LF Write Details
- **Data:** FC (8-bit) + Card ID (16-bit) → raw HID Prox 26-bit format
- **Method:** `lf hid clone -w H10301 --fc {fc} --cn {cn}` via PM3 executor
- **Non-26-bit fallback:** `lf hid clone -r <raw_hex>` when fc=0 and cn=0
- **Format:** H10301 (HID ProxCard II)

---

## ICLASSSEACTIVITY STATE MACHINE

### States
```
READING → (card detected) → WAIT_BLANK → (Write pressed) → WRITING → (done) → RESULT
                     ↑                                                    │
                     └──────────────── (Retry) ↝─────────────────────────┘
```

### State Descriptions

| State | Left Button | Right Button | Description |
|-------|-------------|--------------|-------------|
| READING | Back | (none) | Polling USB decoder for source SE tag |
| WAIT_BLANK | Back | Write | Source decoded, detecting target blank |
| WRITING | (none) | (none) | Write operation in progress |
| RESULT | Back | Retry | Show result, can retry or exit |

### Target Detection Display
- **HF iClass:** Shows "Target: iClass Blank"
- **LF T5577:** Shows "Target: T5577 (HID Prox)"
- **None:** Shows "Place blank on coil..."

### Button Actions
- **WAIT_BLANK + Write:** Start write operation (auto-detects HF/LF, re-detects target before writing)
- **RESULT + Retry:** Re-detects target, then re-writes same data without re-reading source
- **RESULT + Back:** Exit to menu

---

## FILES & ARCHITECTURE

### Key Files Modified

> **Note:** This workspace (`D:\kilocode\icsdecoder`) is self-contained. All application code lives in `release/extracted-955/`. The `src/` paths below are conceptual references to the upstream Dysonian-Lab/icopy-x fork repository structure.

| File (workspace) | File (upstream concept) | Purpose |
|------------------|------------------------|---------|
| `release/extracted-955/app.py` | `src/app.py` | Swap logic with validation, rollback, execv |
| `release/extracted-955/lib/actmain.py` | `src/lib/actmain.py` | MENU_ITEMS + _ACTIVITY_REGISTRY |
| `release/extracted-955/lib/activity_main.py` | `src/lib/activity_main.py` | IClassSEActivity state machine |
| `release/extracted-955/lib/ics_decoder.py` | `src/middleware/ics_decoder.py` | SIO parsing + target detection |
| `release/extracted-955/lib/iclasswrite.py` | `src/middleware/iclasswrite.py` | HF write routines |
| `release/extracted-955/lib/lfwrite.py` | `src/middleware/lfwrite.py` | LF HID clone routine |
| `release/extracted-955/lib/executor.py` | `src/middleware/executor.py` | PM3 command execution |

### ACTIVE MODIFIED FILES (2026-10-07)

| File | Changes |
|------|---------|
| `release/extracted-955/lib/ics_decoder.py` | Replaced `_log()` with non-blocking implementation using `_LOG_DIR='/mnt/upan/dump/ics_decoder'`, line buffering (`buffering=1`), no `os.fsync()`, no `os.path.ismount()`. Added `_get_log_filepath()` and `reset_log_session()`. |
| `release/extracted-955/lib/activity_main.py` | `IClassSEActivity`: Added `reset_log_session()` in `onCreate`, `READ:` log in `_poll_decoder`, `WRITE_START:` log in `_do_write`, `VERIFY_RESULT:` logs in `_do_verify_bg`. |

### ics_decoder.py Functions

| Function | Purpose |
|----------|---------|
| `detect_decoder()` | Scan serial ports for ICS Decoder |
| `read_card(ser)` | Send RD command, read card block |
| `parse_block(text)` | Parse $A_CARD_START$...$A_CARD_STOP$ block |
| `extract_and_shift_wiegand(data)` | Unified NN right-shift + Wiegand parsing |
| `parse_sio_pacs(hex_string)` | Parse decrypted PACS payload |
| `parse_sio_container(hex_string)` | Parse ASN.1 TLV container |
| `detect_target_card()` | Detect HF iClass blank |
| `detect_t5577()` | Detect LF T5577 blank |
| `detect_target()` | Auto-detect target type |
| `write_to_card(blk7)` | Write to HF iClass blank |
| `write_to_t5577(fc, cn, raw_bits=None)` | Write to LF T5577 blank (with non-26-bit fallback) |
| `is_valid_26bit(fc, cn)` | Check if FC/CN represent valid 26-bit frame |

### Write Pipeline (Open-Source Firmware)

**No write.so!** Stock firmware uses closed-source blob. Open-source uses:

| Module | Purpose |
|--------|---------|
| `iclasswrite.py` | `writeDataBlock()`, `writeDataBlocks()` |
| `executor.py` | `startPM3Task()` - PM3 command execution |
| `hficlass.py` | `hf iclass rdbl` - card detection |
| `lfwrite.py` | `write_hid()` - LF HID clone |

### Write Flow
1. User presses Write (WAIT_BLANK) or Retry (RESULT)
2. `_do_write()` re-detects target card via `ics_decoder.detect_target()`
3. If no target detected → fail with "No card detected!" message
4. If target detected → write using appropriate method (HF or LF)
5. For LF: uses `lf hid clone -w H10301` for 26-bit, `lf hid clone -r` for non-26-bit

### PM3 Commands Used

| Command | Purpose |
|---------|---------|
| `hf iclass rdbl --blk 00 -k 2020666666668888` | Detect HF iClass blank |
| `hf iclass wrbl --blk {b} -d {data} -k {key}` | Write block to iClass |
| `lf t55xx detect` | Detect LF T5577 blank |
| `lf hid clone -w H10301 --fc {fc} --cn {cn}` | Clone HID Prox to T5577 (26-bit) |
| `lf hid clone -r {raw_hex}` | Clone HID Prox to T5577 (raw, non-26-bit fallback) |

**IMPORTANT:** `hf iclass info` HANGS on iCopy-X hardware (FPGA mismatch) - DO NOT USE

---

## BUILD DETAILS

- **IPK:** `D:\kilocode\icopy-x\icopy-x-ics-decoder-noflash.ipk` (v1.0-ICS, 12.2 MB)
- **Release v0.1.6:** https://github.com/Dysonian-Lab/icopy-x-ics-decoder/releases/tag/v0.1.6
  - `icopy-x-ics-decoder-noflash.ipk` (11.4 MB) — Factory PM3, Lua 5.1
  - `ics-decoder-firmware.hex` (19 KB) — Pro Micro (ATmega32U4)
- **Activity:** IClassSEActivity at `src/lib/activity_main.py:8007`
- **Registry:** `_ACTIVITY_REGISTRY` at `src/lib/actmain.py:77`
- **Menu Entry:** `MENU_ITEMS` at `src/lib/actmain.py:145`
- **Latest commits:** 91477e7 (synced with upstream v4.23346), e70b5dd (non-26-bit LF guard), 301c531 (target detection), 30831f9 (raw fallback removed)

---
---

## TESTER LOG ANALYSIS (2026-09-16)

### Tester Setup
- **Device:** Genuine Nikola iCS Decoder on `/dev/ttyUSB0` (FTDI, responds `ISE` to `Who`)
- `/dev/ttyACM0` present but responds with `"b"` — not a valid decoder, correctly skipped
- **Card:** Regular iClass Legacy card (NOT SEOS/SE)

### Log Findings (logs 013, 014 from `/mnt/upan/dump/ics_decoder/`)

Every RD cycle returns all-zeros:
SEOS_READ blk7=0000000000000000 fc=0 id=0 sio_pacs= hex=0000000 SEOS_PARSE fc=0 id=0 raw= blk7=0000000000000000


The genuine Nikola decoder detects the card (RD doesn't return `??`) but extracts NO data — blk7 is all zeros, fc=0, id=0, no SIO# field. This is a **card compatibility limitation**, not a firmware bug. The Nikola iCS Decoder only supports SE/SEOS cards; legacy iClass cards are not decodable.

### Key Insight
**The genuine reference device has the same limitation.** Our DIY decoder uses the same RP10E reader and would produce identical all-zeros output for this card type. No firmware or middleware fix can resolve a card that the RP10E + decoder firmware cannot decode.

### Suggested UX Fix: All-Zeros Guard

**File:** `src/lib/activity_main.py` (in the Dysonian-Lab/icopy-x fork)

**Problem:** When `blk7=0000000000000000` (all zeros), the current check at line 8208:
```python
if blk7:  # '0000000000000000' is truthy — passes the check!
...incorrectly treats all-zeros as valid card data, showing "Source decoded!" with FC:0, ID:0.

Recommended fix: Add a guard for all-zeros blk7 to show "card unreadable" instead of proceeding to write:

# Line 8206-8214 — add all-zeros guard
if block is not None:
    blk7 = block.get('blk7', '')
    if blk7 and blk7 != '0000000000000000':
        self._source_data = block
        self._state = self.STATE_WAIT_BLANK
        self._render_wait_blank_state()
        self._start_target_poll()
        return
    # Card detected but no data extracted — likely incompatible card type
    # Show error message and continue polling
    self._render_card_unreadable_state()
Suggested new render method:

def _render_card_unreadable_state(self):
    """Render 'Card unreadable' state for all-zeros card data."""
    canvas = self.getCanvas()
    if canvas is None:
        return
    self._clear_canvas()
    self.setLeftButton(resources.get_str('back'))
    self.setRightButton('')
    canvas.create_text(
        120, self._Y_STATUS,
        text='Card unreadable',
        fill='#8B0000',
        font=resources.get_font(14),
        anchor='center',
        tags='_ics_status',
    )
    canvas.create_text(
        120, self._Y_PROMPT,
        text='Try SE/SEOS or 125kHz Prox',
        fill='#333333',
        font=resources.get_font(13),
        anchor='center',
        tags='_ics_prompt',
    )
Also add all-zeros detection in middleware (src/middleware/ics_decoder.py, parse_block()):

# After blk7 extraction (line 208-210), add validation
if 'blk7' not in result:
    return None
if result['blk7'] == '0000000000000000':
    # Genuine decoder detected a card but couldn't decode it (likely
    # legacy iClass or incompatible card type)
    result['decodable'] = False
else:
    result['decodable'] = True
Conclusion
No firmware or middleware changes needed for card reading itself. The all-zeros guard is a UX improvement to avoid misleading "Source decoded!" messages for undecodable cards. 

```
---

## TESTER LOG ANALYSIS — Legacy iClass Card (2026-09-16)

### Card Type: iClass Legacy (NOT SEOS/SE)
- Key set 0 = `AE A6 84 A6 DA B2 32 78` (HID iClass default public key)
- 2 application areas (AA1 limit 18, AA2 limit 31) — standard iClass Legacy
- "failed to communicate with card" — intermittent PM3 read, card positioning issue

### Why the Nikola Decoder Returns All-Zeros
- The iCS Decoder (genuine Nikola and DIY) is designed **ONLY** for SE/SEOS cards
- The RP10E performs SEOS crypto internally and outputs decrypted Wiegand
- **iClass Legacy cards do NOT produce Wiegand output** from the RP10E
- The decoder detects card presence but extracts no data → returns all zeros

### Correct Workflow for Legacy iClass Cards
1. **Do NOT use ICS Decoder** for Legacy iClass cards
2. **Use iCopy-X standard Read → Clone flow** (PM3 coil directly)
3. The iCopy-X natively supports iClass Legacy via `hf iclass dump` with HID default key
4. Write to blank iClass/Picopass via `iclasswrite.writeDataBlocks()`

### Bit Count Conclusion
**Not a bit count mismatch.** The issue is that Legacy iClass cards don't produce Wiegand output from the RP10E. The firmware's filter `(26/34/35/37/48)` would handle 34-bit if it were produced, but the RP10E doesn't output Wiegand for Legacy cards. This is a hardware/architecture limitation, not a firmware bug.

---
## REPOS

| Repo | Purpose |
|------|---------|
| `Dysonian-Lab/icopy-x` | Main fork with ICS Decoder |
| `Dysonian-Lab/icopy-x-ics-decoder` | Firmware, releases |
| `lab-401/icopy-x` | Upstream (read-only) |

## SYNC HISTORY

### 2026-10-03: Fork Synced with Upstream v4.23346

**Initial state:**
- Local `Dysonian-Lab/icopy-x` main at `7049af1` (50 commits behind both origin and upstream)
- `origin/main` (Dysonian-Lab) at `b3809b5` (30 commits ahead of local)
- `upstream/main` (lab-401) at `28e817f` (75 commits ahead of local, contains all origin commits)

**Sync steps performed:**
1. `git stash` — preserved uncommitted changes (iCLASS fixes)
2. `git pull origin main --ff-only` — fast-forwarded local from `7049af1` to `b3809b5`
3. `git merge upstream/main` — merged 45 upstream commits on top, fast-forwarding to `28e817f`
4. `git stash pop` — restored uncommitted changes, resolved conflicts:
   - `ipk_extract/` files: deleted by upstream, discarded stashed changes (obsolete)
   - `plugins/manage_dictionaries/plugin.py`: merged upstream i18n plugin refactor with iCLASS dictionary support
   - `plugins/manage_dictionaries/ui.json`: merged upstream UI refactor with iCLASS input fields
   - `src/middleware/hficlass.py`: no conflict (stashed changes applied cleanly)
   - `src/middleware/iclasswrite.py`: no conflict (stashed changes applied cleanly)
5. Cleaned up `iclass_default_keys.dic` — removed duplicates and placeholder keys
6. `git commit` — commit `91477e7` on local main
7. `git stash drop` — discarded stash (changes fully applied)
8. `git push origin main` — pushed to `Dysonian-Lab/icopy-x`

**Final state:**
- Local main at `91477e7`
- Contains all upstream PRs #14-#30 (i18n, card-notes, chameleon-dump, RTC fixes, MFC recovery)
- Contains all your iCLASS dictionary key discovery fixes

**To keep in sync going forward:**
```bash
cd /d/kilocode/icopy-x
git fetch upstream
git merge upstream/main  # or git rebase upstream/main for cleaner history
git push origin main
```

## TOKEN LOCATION

`D:\kilocode\icsdecoder\cridential.txt` line 60

---

## CRITICAL ISSUE - PM3 Version Shows "?" & Long Boot (2026-10-04)

### Problem
After flashing `icopy-x-ics-decoder-noflash.ipk` (v0.1.6):
- About screen shows: HMI 1.4.1.0, OS v0.1.6, **PM: ?**
- Long boot (2-3 min) with "Processing..." screen hanging
- Device was previously running upstream v1.1.6 full flash IPK with PM3 v4.23346

### Root Cause Analysis

**No-flash IPK uses factory PM3 client** (from commit `372259e`) - this is the **old NIKOLA firmware** (v3.1 from 2022), NOT the RRG/Iceman v4.23346.

The PM3 version detection in `src/middleware/version.py::getPM()` calls `pm3_flash.get_running_version()` which sends `hw version` via executor.

**For NIKOLA firmware**: expects `NIKOLA: v3.1 ...` line in output
**For RRG/Iceman**: expects `os: RRG/Iceman/master/v4.23346...` line

The factory PM3 binary in the no-flash IPK **IS the NIKOLA client** (from commit `372259e`). It should return "NIKOLA: v3.1..." in `hw version` output.

**Why it shows "?":**
1. `executor.startPM3Task('hw version', timeout=5000)` returns -1 (timeout/error)
2. Or PM3 subprocess isn't running properly on device
3. Or TCP connection (port 8888) not established
4. Or `hw version` command hangs on this firmware

**Long "Processing..." boot:**
The `_post_ui_pm3_check()` in `application.py` runs `hw version` with `rework_max=0` (no retries). If PM3 is slow/unresponsive, it blocks the background thread but the Toast stays visible.

### Key Files
- `src/middleware/version.py` - `getPM()` calls `pm3_flash.get_running_version()`
- `src/middleware/pm3_flash.py` - `get_running_version()` sends `hw version` via executor
- `src/middleware/executor.py` - `startPM3Task()` with `rework_max` retries
- `src/main/rftask.py` - RemoteTaskManager manages PM3 subprocess on TCP:8888
- `src/main/main.py` - Boots RTM, calls `executor.connect2PM3()` after 2s sleep

### Why PM3 Binary in No-Flash IS Old NIKOLA
- `build/factory_proxmark3` = NIKOLA client (commit `372259e`)
- No-flash IPK excludes `res/firmware/pm3/fullimage.elf` (the RRG/Iceman firmware image)
- Without the flash manifest, `needs_flash()` returns False, never flashes new firmware
- The PM3 client binary runs against whatever firmware is on the device's SAMD21

### If Device Was on v1.1.6 Full Flash Before
The SAMD21 has RRG/Iceman v4.23346 firmware on it. The no-flash IPK installs the **NIKOLA client binary** which tries to talk to RRG/Iceman firmware via old Nikola protocol - **protocol mismatch**.

### Fix Options
1. **Flash full IPK** (`icopy-x-ics-decoder-flash.ipk`) - includes RRG/Iceman firmware + matching client
2. **Use PM3 client matching device firmware** - but no-flash IPK only ships NIKOLA client
3. **Build no-flash with RRG/Iceman client** - but would need matching Lua 5.4 scripts

### Immediate Action
Flash the **full flash IPK** (includes firmware + matching client) to restore PM3 version detection.

---

## FIXED: No-Flash IPK PM3 Client Mismatch (2026-10-04)

### Problem
No-flash IPK v0.1.6 (released 2026-10-03) shipped **RRG/Iceman 385d892-dirty client** (old, Lua 5.1) instead of **v4.23346 Frosty Lemon client** (Lua 5.4).

Devices with v4.23346 firmware (from full flash v1.1.6) had protocol mismatch:
- `hw version` command failed → PM version showed `"?"`
- Long 2-3 min boot with "Processing..." (PM3 unresponsive to version probe)

### Root Cause
`tools/build_ipk.py` has two client sources for `--no-flash`:
- `build/factory_proxmark3` = checked-in old client (385d892-dirty)
- `build/proxmark3` = Docker build (v4.23346)

Build script defaulted to factory client for no-flash.

### Fix Applied
Replaced checked-in factory binaries with upstream v1.1.6 release binaries:
```bash
cp official_flash_ipk/pm3/proxmark3 build/factory_proxmark3
cp official_flash_ipk/pm3/lua.zip build/factory_lua.zip
python tools/build_ipk.py --no-flash --version v0.1.6
```

### Result
- **PM3 client**: RRG/Iceman **v4.23346 Frosty Lemon** (matches device firmware)
- **Lua scripts**: **5.4** (matches v4.23346)
- **CAPABILITIES_VERSION**: **11** (both client + firmware)
- **version.so / install.so**: identical to upstream v1.1.6
- **IPK size**: 13.1 MB (was 11.4 MB)
- **SHA256**: `6ed487c5dadc2fa364721a3bbf63efd39931af88a65b4cb81f31f9ecdc3d59db`

### Release Updated
https://github.com/Dysonian-Lab/icopy-x-ics-decoder/releases/tag/v0.1.6
- Old asset deleted, new asset uploaded
- PM version now dynamically detected via `hw version` (no hardcoding)

### Verification Pending
Test on device: About screen should show PM `v4.23346` (not `?`), fast boot.

---

## FIXED: iCLASS Dictionary Folder Auto-Creation (2026-10-04)

### Problem
iCLASS dictionary folder `/mnt/upan/keys/iclass/` not created on device. Only `mf1/` and `t55xx/` existed at `H:\keys\`. User had to manually run "Load Dictionaries" from Manage Dictionaries plugin.

### Root Cause
Dictionary folders only created when user manually runs "Load Dictionaries" plugin action. No auto-creation on boot/mount.

### Fix Applied
Added `_ensure_dictionary_dirs()` in `src/middleware/gadget_linux.py` called from `auto_ms_remount()` which runs:
1. On boot (main.py calls `gadget_linux.auto_ms_remount()`)
2. After PC-mode exit (`kill_all_module` calls it with `auto_remount=True`)

```python
def _ensure_dictionary_dirs():
    base = '/mnt/upan/keys'
    for sub in ('mf1', 't55xx', 'iclass'):
        os.makedirs(os.path.join(base, sub), exist_ok=True)
```

### Result
- `H:\keys\iclass\` folder auto-created on boot/mount
- Manage Dictionaries plugin "Load Dictionaries" still works for copying default keys
- iCLASS keys available immediately for `hficlass.py` dictionary fallback

### IPK Updated
- Release v0.1.6 asset replaced (SHA256: `0bd94806...`)
- Device H: updated with new IPK

---

## FIXED: iCLASS Dictionary Auto-Copy (2026-10-04)

### Problem
Dictionary folder created but empty — default `iclass_default_keys.dic` not copied. User still had to manually run "Load Dictionaries".

### Fix Applied
Extended `_ensure_dictionary_dirs()` in `src/middleware/gadget_linux.py` to also copy default dictionary files from plugin bundle if destination doesn't exist:

```python
dicts = {
    'mf1': ('mfc_default_keys.dic', 'mfc_default_keys.dic'),
    't55xx': ('t55xx_default_pwds.dic', 't55xx_default_pwds.dic'),
    'iclass': ('iclass_default_keys.dic', 'iclass_default_keys.dic'),
}

for sub, (src_name, dst_name) in dicts.items():
    # ... create directory ...
    dst_file = os.path.join(path, dst_name)
    if not os.path.isfile(dst_file):
        src_file = os.path.join(plugin_base, sub, src_name)
        if os.path.isfile(src_file):
            shutil.copy(src_file, dst_file)
```

### Result
- On boot/mount: all three dictionary folders created + default keys copied
- `H:\keys\iclass\iclass_default_keys.dic` now populated immediately
- iCLASS dictionary fallback in `hficlass.py` works without manual steps

### IPK Updated
- Release v0.1.6 asset replaced (SHA256: `32ffc30b...`)
- Device H: updated with new IPK

---

## FIXED: iCLASS Dictionary Auto-Copy (2026-10-04)

### Problem
Dictionary folder created but empty — default `iclass_default_keys.dic` not copied. User still had to manually run "Load Dictionaries".

### Fix Applied
Extended `_ensure_dictionary_dirs()` in `src/middleware/gadget_linux.py` to also copy default dictionary files from plugin bundle if destination doesn't exist:

```python
dicts = {
    'mf1': ('mfc_default_keys.dic', 'mfc_default_keys.dic'),
    't55xx': ('t55xx_default_pwds.dic', 't55xx_default_pwds.dic'),
    'iclass': ('iclass_default_keys.dic', 'iclass_default_keys.dic'),
}

for sub, (src_name, dst_name) in dicts.items():
    # ... create directory ...
    dst_file = os.path.join(path, dst_name)
    if not os.path.isfile(dst_file):
        src_file = os.path.join(plugin_base, sub, src_name)
        if os.path.isfile(src_file):
            shutil.copy(src_file, dst_file)
```

### Result
- On boot/mount: all three dictionary folders created + default keys copied
- `H:\keys\iclass\iclass_default_keys.dic` now populated immediately
- iCLASS dictionary fallback in `hficlass.py` works without manual steps

### IPK Updated
- Release v0.1.6 asset replaced (SHA256: `32ffc30b...`)
- Device H: updated with new IPK

## Verified Working (2026-10-04)
- Logging: ICS decoder logs -> /mnt/upan/dump/ics_decoder/ (numbered 001.log, 002.log...), main app logs -> /mnt/upan/logs/ (numbered 001.log, 002.log...). Both visible in PC-Mode.
- SEOS downgrade workflow verified end-to-end:
  - Read SEOS card via ICS decoder: FC#:100 ID#:612 blk7#:0000000002c804c9
  - Write to T5577 blank: success
  - Verify T5577: FC:100 CN:612 parity (ok)
  - Autocopy T5577->T5577: verify passed
- About screen: OS version 0.1.6 reported correctly, PM version no longer shows ?

## Known Issues (need investigation)
- PC mode exit hang observed in app log
- 56-bit card capture from Canadian tester not yet analyzed/implemented

## V0.1.6.2 � LF VERIFY ARCHITECTURE FIX (2026-10-10)

### Problem
After a successful LF T5577 write with inline verification, `_do_verify_bg()` called
HF-only `detect_target()`. On an LF card (T5577), it returns `None`, producing
"No card on coil" and overwriting the successful write result. Boolean flags
(`_lf_verify_done`, `_last_written_target`) failed because the background polling
timer (`_poll_target` ? `_bg_detect`) continuously runs `detect_target()`,
overwriting `self._target_type = None` before `_do_verify_bg()` executes.

### Fix (in `activity_main.py` only, `ics_decoder.py` untouched)

**1. Credential-type-based protocol dispatch in `_do_verify_bg()`**
- Check `is_valid_26bit(fc, cid)` from `self._source_data` FIRST.
- If 26-bit: attempt LF verification directly via
  `verify_target_card(TARGET_LF_T5577, source)`. If success ? report True.
  Only if LF fails ? fall back to HF `detect_target()`.
- If not 26-bit: use existing HF-only `detect_target()`.

**2. Timer pollution prevention**
- `_do_verify()`: sets `_abort_target_poll = True`, calls `_stop_poll()` +
  `_stop_target_poll()` before launching background verify.
- `_do_write()`: sets `_abort_target_poll = True` before stopping timers.
- `_on_target_detected()`: refuses to overwrite `_target_type` when state
  is not `STATE_WAIT_BLANK` (prevents stale timer callbacks from clobbering
  post-write state).

**3. No state flags** � eliminated `_lf_verify_done` and `_last_written_target`.
Protocol dispatch is driven by credential type, not fragile boolean state.

### Verification
- Hardware log `027.log`: `VERIFY_RESULT: success=True msg=FC:100 CN:613`
- Golden snapshot: `release/GOLDEN-v0.1.6.2-verified-lf-clone/` + `CHECKSUMS.sha256`
- Release asset: `icopy-x-ics-decoder-v0.1.6.2-debug.ipk` (SHA256:
  `2db557dadae6de3ca64fc1aed98255abba72db910d3819a656f49bc75646fa12`)

### Operational Rules
- **Rule A**: `ics_decoder.py` is locked � PM3 wrapper logic is verified.
- **Rule B**: Future feature audits use Two-Phase: Phase 1 = audit/logging
  only (zero logic changes); Phase 2 = architectural proposal before
  implementation.
- **Rule C**: If any future change regresses, revert to
  `release/GOLDEN-v0.1.6.2-verified-lf-clone/`.

## Lessons Learned
- Do NOT change working code paths (ics_decoder logging was working � replaced 2026-10-07 per strict constraints: removed ismount/fsync, set log dir to `/mnt/upan/dump/ics_decoder/`)
- Do NOT touch historical docs/CI unless explicitly asked
- Minimal changes only � no broad refactors
- Verify IPK contents before uploading
- Do not add commentary to user statements
