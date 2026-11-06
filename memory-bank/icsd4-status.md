# Memory Bank — iCS D4 / iCopy-X iCS Decoder Diagnostic Sniffer

## Project Context
- **Goal**: Dual-purpose ATmega32U4 firmware — primary: iCS Decoder accessory for iCopy-X (reverse-compatible Who/RD handshake); secondary: benchtop Wiegand diagnostic sniffer.
- **Repo**: Dysonian-Lab/icopy-x-ics-decoder (GitHub)
- **Local path**: D:\kilocode\icsd4\
- **Target hardware**: ATmega32U4 (SparkFun Qwiic Pro Micro USB-C / Arduino Leonardo)
- **Wiegand pins**: D0 = pin 2, D1 = pin 3 (falling-edge interrupts)
- **Serial**: 115200 8N1, USB CDC

## Files in Working Directory
| File | Status | Purpose |
|------|--------|---------|
| `icsd4.ino` | Complete, reviewed | Firmware sketch (908 lines) |
| `icsd4-manual.md` | Complete, reviewed | Usage manual |
| `icsdecooderori.ino` | Unmodified | Production firmware reference |
| `ics_decoderrecover.ino` | Unmodified | Production recovery firmware reference |
| `benchtop-diagnostic-plan.md` | Unmodified | Implementation plan source |
| `memory-bank/icsd4-status.md` | This file | Project status and decisions |

## Firmware — `icsd4.ino` — Current State

### Verified against `icsdecooderori.ino` and GitHub README
- `Who` → `ISE\r\n` — exact match
- `RD` → `OK\r\n` + `$A_CARD_START$…$A_CARD_STOP$` or `??\r\n` — exact match
- RD whitelist: 26/34/35/37/48/56 bits — **56 added**
- `Blk7#` always 16 hex chars; `Hex#` byte-padded lowercase; `Bits#` exact bit count (no 48-char pad)
- Same pins, baud, LED, command buffer, line-ending handling

### Diagnostic features implemented
- 8-slot ring buffer (`WgFrame ring[8]`) with overflow flag on displaced frames
- SNIFF mode: auto-streams every latched frame via `printFrame()`
- BRIDGE mode: silent capture, RD still works for whitelisted cards
- Commands: WHO/RD/STATUS/DUMP/CLEAR/MODE/TIMEOUT/BITS/BRUTE/HELP + `/?` alias
- Gap-timeout frame latching (default 25 ms, clamp 5..100 ms)
- `wgReconstruct64()` rebuilds uint64_t from bits[] matching production ISR packing
- `extract_field()` extracts arbitrary bit ranges from reconstructed values
- `cmdBrute()` brute-forces FC/CN field positions on captured frames
- `printUint64Dec()` custom 64-bit decimal printer for AVR (Serial.println doesn't support uint64_t decimal)

### 56-bit Avigilon legacy payload (SE 2k via SAM)
Decoded from card capture + confirmed by field testing:
```
Bit 0   = even parity
Bits 1-20 = Facility Code (20 bits) -> 858
Bits 21-54 = Card Number (34 bits) -> 2,493,837
Bit 55   = odd parity
```
Implemented in `sendCardBlock()` lines 844-851. RD now returns `OK` + `FC#:858` + `ID#:2493837` for this card.

### Bugs fixed during review
1. `printBinBuf`: Was reverse `int16_t` loop printing LSB-first. Changed to forward `uint16_t` loop printing MSB-first correctly.
2. Manual contradiction: 48-bit example claimed outside whitelist (48 IS whitelisted). Changed to 56-bit example.
3. **32-bit cardId truncation** (critical): `cardId` was `uint32_t`, truncating 34-bit CN values > 4.29 billion. Fixed: changed to `uint64_t` + added `printUint64Dec()` for AVR decimal output. Fixed in `cmdBrute()` too (was casting to `unsigned long`).

### Remaining documentation-only issues
- GitHub README claims `Bits#` is "48-char binary, left-padded to 48" — actual firmware prints exactly `bits` characters, no padding. README needs updating separately (different repo).

## Compilation Status
- NOT compiled locally (no Arduino CLI / avr-g++ available)
- Must verify with Arduino IDE before one-shot flash: Board = Arduino Leonardo or SparkFun Qwiic Pro Micro (ATmega32U4), Port = target COM
- One-shot flash warning: Pro Micro difficult to reflash — verify thoroughly before uploading

## Key Design Decisions
- `wgLatchFrame()` sets `cardAvailable = true` + `cardRaw`/`cardBits` from `wgReconstruct64()` so RD returns captured frames to iCopy-X
- Ring overflow: newly latched frame gets `overflow = true`; ringCount stays 8; oldest slot overwritten
- All volatile reads outside ISRs wrapped in `noInterrupts()`/`interrupts()`
- ISRs never call Serial, delay, or noInterrupts
- 56-bit FC/ID layout hardcoded based on field-tested card capture; unknown formats return FC=0, ID=0
- **48-bit Corporate 1000 layout hardcoded**: FC=extract_field(raw,48,2,22), CN=extract_field(raw,48,24,23). Confirmed working on SEOS card (FC#:1970 ID#:1341).

## Next Phase — Open Items
1. **DONE**: Test `Who`/`RD` handshake with iCopy-x on 56-bit SE 2k card — returns OK + FC=858 + ID=2493837
2. **DONE**: Test `RD` on 48-bit SEOS Corporate 1000 card — returns OK + FC=7874 + ID=1341
3. **DONE**: Test `RD` on 26-bit card — regression OK (FC=100 ID=613)
4. Test `BRUTE` command on additional SE 2k / SEOS cards to identify more format layouts
5. Capture more cards with `icsd4.ino` in SNIFF mode; compare `Bin#`/`Hex#` for format reverse-engineering
6. End-to-end test: plug SparkFun MCU into iCopy-x (USB-C) and verify iCopy-x can clone SE 2k card to legacy blank
7. **NEW**: Implement Lua serial bridge script per `PLAN-LUA.md` — portable CLI / Phosphor / iCopy-X
8. Consider Lua script / plugin for downstream use of diagnostic features (user-planned, device TBD)
9. Update GitHub README `Bits#` claim (separate repo task)
10. Consider flashing production firmware back after diagnostics if needed

## Contact / Coordination
- Shared board with main agent and task children — use for peer coordination
- No pending questions or blockers