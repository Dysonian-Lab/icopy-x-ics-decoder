# ICS DECODER - CURRENT STATE (2026-09-01)

## LATEST BUILD: v1.0-ICS (commit 301c531)

---

## TARGET DETECTION BEFORE WRITE (commit 301c531)

### Problem
Write attempted even when no target card present, causing immediate failure with no user feedback about card presence.

### Fix
- `_do_write()` now re-detects target card before attempting write
- If no target detected, fails immediately with 'No card detected!' message
- Result state shows 'No card detected!' when target_type is None
- Retry button re-detects target before retrying write

---

## NON-26-BIT GUARD (commit 30831f9)

### Problem
48-bit SEOS payload (0x801EC2000A7A) wrote FC:0 CN:0 to T5577 because parser returned fc=0 cn=0 for non-26-bit formats.

### Fix
- `write_to_t5577()` now accepts `raw_bits` parameter for fallback
- If fc=0 and cn=0 but raw_bits available, uses `lf hid clone -r <raw>`
- Prevents writing blank cards for non-26-bit formats
- Added `is_valid_26bit(fc, cn)` helper function

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
                     └──────────────── (Retry) ←─────────────────────────┘
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

| File | Purpose |
|------|---------|
| `src/app.py` | Swap logic with validation, rollback, execv |
| `src/lib/actmain.py` | MENU_ITEMS + _ACTIVITY_REGISTRY |
| `src/lib/activity_main.py` | IClassSEActivity state machine |
| `src/middleware/ics_decoder.py` | SIO parsing + target detection |
| `src/middleware/iclasswrite.py` | HF write routines |
| `src/middleware/lfwrite.py` | LF HID clone routine |
| `src/middleware/executor.py` | PM3 command execution |
| `tools/build_ipk.py` | Build configuration |

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
- **Activity:** IClassSEActivity at `src/lib/activity_main.py:8007`
- **Registry:** `_ACTIVITY_REGISTRY` at `src/lib/actmain.py:77`
- **Menu Entry:** `MENU_ITEMS` at `src/lib/actmain.py:145`
- **Latest commits:** 30831f9 (non-26-bit guard), 301c531 (target detection)

---

## REPOS

| Repo | Purpose |
|------|---------|
| `Dysonian-Lab/icopy-x` | Main fork with ICS Decoder (commit 301c531) |
| `Dysonian-Lab/icopy-x-ics-decoder` | Firmware, releases |
| `lab-401/icopy-x` | Upstream (read-only) |

---

## TOKEN LOCATION

`D:\kilocode\icsdecoder\cridential.txt` line 60
