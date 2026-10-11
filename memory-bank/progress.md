# Progress Tracker

## Completed
- [x] Stable IPK build reproduction from commit ea222d4 verified (0 CRC mismatches, 0 size mismatches, 305 files)
- [x] Fresh IPK built and uploaded to GitHub release v0.1.6 (13,055,068 bytes, SHA256 `0baa39bbc7ac307ff0de1c7bd1523d93e1ce56f14760a3719cf0218fed93263e`)
- [x] Identified git line ending issue (Windows CRLF-LF conversion despite autocrlf=false)
- [x] Documented workaround: copy file contents from stable IPK to correct src/ paths
- [x] Identified build artifact locations (proxmarkmark3, lua.zip, version.so, install.so)
- [x] Arduino firmware commit e198f1f identified with printBinary64 call at line 170
- [x] iCopy-X code baseline commit 846d49c identified
- [x] App logging paths documented: main logs at `/mnt/upan/logs/`, ICS decoder logs at `/mnt/upan/dump/ics_decoder/`
- [x] Implemented targeted ICS Decoder logging (2026-10-07):
  - Active modified files: `release/extracted-955/lib/ics_decoder.py` and `release/extracted-955/lib/activity_main.py`
  - Authoritative app source path: `release/extracted-955/` (self-contained workspace, no `src/` directory)
  - Logging destination: `/mnt/upan/dump/ics_decoder/` with incrementing `001.log`, `002.log` via `_get_log_filepath()` + `reset_log_session()`
  - Added `reset_log_session()` call in `IClassSEActivity.onCreate()` (line ~8251)
  - Added `READ:` log on card parse in `_poll_decoder()` (line ~8403)
  - Added `WRITE_START:` log in `_do_write()` (line ~8460)
  - Added `VERIFY_RESULT:` logs in `_do_verify_bg()` (lines ~8868, ~8885)
- [x] **v0.1.6.2 Golden Snapshot established** (2026-10-10):
  - HID 26-bit cloning end-to-end verified on hardware (027.log: `VERIFY_RESULT: success=True`)
  - Golden baseline: `release/GOLDEN-v0.1.6.2-verified-lf-clone/` with `CHECKSUMS.sha256`
  - Release asset: `icopy-x-ics-decoder-v0.1.6.2-debug.ipk` (SHA256: `2db557dadae6de3ca64fc1aed98255abba72db910d3819a656f49bc75646fa12`)
- [x] **v0.1.6.3 Proxmark3 v4.23346 Compatibility Audit** (2026-10-11):
  - 47 PM3 CLI dispatch points audited (all via direct `executor.startPM3Task`; 0 via pm3_compat)
  - 32 unique command templates verified against PM3 v4.23346 source tree (git fc024c803)
  - 32/32 commands FULL MATCH — 0 mismatches, 0 deprecated flags, 0 missing parameters
  - Audit script: `scripts/audit_pm3_cli.py` (AST-based static analysis)
  - Compliance matrix: `docs/PM3_V4.23346_COMPLIANCE_MATRIX.md`
  - GitHub Release published: https://github.com/Dysonian-Lab/icopy-x-ics-decoder/releases/tag/v0.1.6.3
  - Tag v0.1.6.3 (annotated) committed at `2536dd2` and pushed to main
  - User flag directives applied: `lf sea`/`hf sea` = valid aliases; `-k` = `--key` (not `--keep`)

## In Progress
- [ ] Arduino firmware fix: `printBinary64(raw, 48)` → `printBinary64(raw, bits)` at line 170 of `D:\kilocode\icopy-x-ics-decoder\firmware\ics-decoder\ics-decoder.ino`
  - Context: Inside `sendCardBlock()` function — secondary "Bits#:" output after primary `wiedata#` (line 133, already correct with dynamic `bits`)
  - Note: User reference of "line 186" is approximate; actual line is 170
- [ ] Implement safe multi-bit support with isolated exception handling so write UI never crashes

## Blocked / Needs Investigation
- [ ] Device PM3 communication failure: `detect_target()` and `hw version` return `ret=-1`; logs show `rftask: no response`
  - Device "Processing..." hang and OS/PM version showing `?`
  - May be device-side state corruption vs code issue
- [ ] Multi-bit SEOS card support (downgrade path blocked at PACS extraction due to "New silicon" variant)
- [ ] App logging: implement functional app logging for PM3 commands, read/write results, autocopy flow in `/mnt/upan/logs/`
- [ ] Firmware Wiegand whitelist (NEW - 2026-10-11):
  - Location: `firmware/ics-decoder/ics-decoder.ino:119`
  - Current: `if (cardAvailable && (cardBits == 26 || cardBits == 34 || cardBits == 35 || cardBits == 37 || cardBits == 48))`
  - Blocks valid real-world credentials (56-bit PIV, 32-bit CSN, custom enterprise formats)
  - Proposed: `if (cardAvailable && cardBits >= 4 && cardBits <= 64)` for noise-floor passthrough
  - Status: Deferred — DO NOT touch firmware on main. Requires dedicated bench test hardware (secondary SparkFun board + RP10 reader). All work in `feature/arbitrary-wiegand-bits` branch with logic analyzer verification.

## Packaging Audit (Analysis Only)
- **No IPK build script in this workspace.** The `release/extracted-955/` directory is the extracted application contents.
- **IPK build script location:** `D:\kilocode\icopy-x\tools\build_ipk.py` (in the separate icopy-x repo, not in this workspace).
- **Packaging approach:** The `build_ipk.py` script packages the `release/extracted-955/` directory contents (plus PM3 binaries, Lua scripts, and compiled `.so` modules) into a ZIP-format `.ipk` file.
- **No IPK repackaging script exists in `D:\kilocode\icsdecoder`.** The scripts here (`verify_ipk.py`, `check_menu.py`, `check_bytes.py`, `full_verify.py`) only inspect existing `.ipk` files for correctness, not create them.
- **Upload scripts:** `upload_*.bat`, `upload_*.sh`, `create_and_upload_release.ps1` upload pre-built `.ipk` files to GitHub releases — they do not create IPKs.

