# CURRENT STATE - 2026-08-31

## WORKING BUILD - TESTED ON DEVICE

### What Works
- **ICS Decoder appears in main menu** (between LUA Script and Settings)
- **No black screen / no brick** - safe swap mechanism
- **HMI 1.4.1.0** shows in About
- **PM v4.21611** proxmark3 client working

### Final Fix (What Made It Work)
1. **Swap logic in app.py** - the entry point boot calls. Validates, swaps, and uses os.execv() for clean restart
2. **Pre-swap validation** - checks required files exist and non-zero before touching anything
3. **Try/except with automatic rollback** - if swap fails, restores backup automatically
4. **ICS Decoder in MENU_ITEMS** (actmain.py line 145) and _ACTIVITY_REGISTRY (line 77)
5. **All files py_compile checked** - zero syntax errors

### Critical Safeguards Implemented
- Pre-swap validation: checks app.py, main/main.py, lib/actmain.py exist and non-zero
- Try/except wrapper: ANY failure during swap triggers automatic rollback
- os.execv() for clean process restart after swap (no self-modification)
- Cleanup on success only: ipk_app_old preserved until new version runs

### Build Details
- **IPK**: `D:\kilocode\icopy-x\icopy-x-ics-decoder-noflash.ipk` (build 260831-23.18-Int)
- **Swap mechanism**: In app.py (not separate script)
- **Menu integration**: Core MENU_ITEMS (not plugin)
- **Activity**: IClassSEActivity at src/lib/activity_main.py:7997
- **Registry**: _ACTIVITY_REGISTRY at src/lib/actmain.py:77
- **Menu entry**: MENU_ITEMS at src/lib/actmain.py:145

### Key Files Modified
- `src/app.py` - added swap logic with validation, rollback, execv
- `src/lib/actmain.py` - added ICS Decoder to MENU_ITEMS and _ACTIVITY_REGISTRY
- `src/lib/activity_main.py` - IClassSEActivity implementation (line 7997)
- `src/middleware/ics_decoder.py` - serial bridge middleware
- `src/main/install.py` - install path /home/pi/ (correct)
- `tools/build_ipk.py` - includes ipk_starter.py in build

### Repos
- **Dysonian-Lab/icopy-x** - main fork with ICS Decoder integration
- **Dysonian-Lab/icopy-x-ics-decoder** - ICS Decoder specific repo (firmware, releases)
- **lab-401/icopy-x** - upstream (read-only reference)

### Token Location
- `D:\kilocode\icsdecoder\cridential.txt` line 60
