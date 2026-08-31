# iCopy-X Open Firmware Analysis for iCS Decoder Integration

Date: 2026-08-14
Source: https://github.com/lab-401/icopy-x

## Key Finding: Stub Already Exists

The open firmware contains a **complete stub** for iCS Decoder support that was never implemented:

**`src/lib/activity_main.py:7997-8017`**
```python
class IClassSEActivity(BaseActivity):
    # STUB — only displays "Please place iClass SE tag on USB decoder"
    # No actual decoder communication code
```

**Status:**
- Activity class exists but is **NOT registered** in `_ACTIVITY_REGISTRY`
- Unreachable from the main menu
- No serial communication code
- No device detection code

## What the Open Firmware Does NOT Have
- No iCS Decoder device detection
- No USB serial port scanning for external accessories
- No `Who`/`RD` protocol implementation
- No `$A_CARD_START$` payload parsing
- No udev rules or hotplug for accessories
- No generic serial-port abstraction for plugins

## Integration Points

### Activity Registry
- **File:** `src/lib/actmain.py`
- Add `IClassSEActivity` to `_ACTIVITY_REGISTRY`

### Middleware
- **New file needed:** `src/middleware/ics_decoder.py`
- Handle serial communication with iCS Decoder
- Implement `Who`/`RD` protocol
- Parse card payload

### Activity Implementation
- **File:** `src/lib/activity_main.py` (extend existing stub)
- Add device detection
- Add serial communication
- Add card data display

### Menu Entry
- **File:** `src/screens/main_menu.json`
- Add iCS Decoder menu item

## Plugin System Limitations
- Plugins have `pm3_command` and `shell_command` permissions
- No dedicated serial-port API for external accessories
- A plugin could use `shell_command` to spawn Python serial code, but this is awkward
- Better approach: implement as first-class activity + middleware

## Device Enumeration Strategy
- Genuine iCS Decoder: `/dev/ttyUSB0` (FTDI)
- Our DIY Pro Micro: `/dev/ttyACM*` (CDC ACM)
- Competitor's Teensy: `/dev/ttyACM*` (CDC ACM, needs symlink hack)
- Detection: try `/dev/ttyUSB0` first, then scan `/dev/ttyACM*`

## How to Add Menu Items (from user-provided documentation)

### Method 1: Plugin System (RECOMMENDED)
- Create `plugins/<your_plugin_name>/` with JSON manifest
- JSON defines: title, icon, actions (pm3_command, screen_transition, shell_command/binary)
- Plugin auto-appears under top-level "Plugins" menu
- No core code modification needed

### Method 2: Core Menu (src/ & data/)
- Modify `src/lib/actmain.py` MENU_ITEMS list
- Modify `src/screens/main_menu.json`
- Register in `_ACTIVITY_REGISTRY`
- Implement activity handler in `src/lib/activity_main.py`
- Requires: title, icon (from res/), target_state/callback

### Key Files
- `src/lib/actmain.py` — MENU_ITEMS list + _ACTIVITY_REGISTRY
- `src/screens/main_menu.json` — JSON screen definitions
- `src/lib/activity_main.py` — activity implementations
- `src/middleware/ics_decoder.py` — serial bridge middleware
- `plugins/` — plugin directory (RECOMMENDED approach)
- `tools/screen_mirror/mirror_client.py` — test UI without device

### Critical Notes
- Non-blocking PM3 calls required (use startBGTask or middleware queue)
- Test via screen mirroring before device testing
- Plugin system is data-driven, no state machine rewrite needed
