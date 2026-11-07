# iCS D4 Lua Serial Bridge — Tactical Field Manual

## 1. Files
- `icsd4.lua` — main script (all environments)
- `icsd4.lua.cfg` — configuration (optional, next to script)
- `PLAN-LUA.md` — full spec

## 2. iCopy-X Deployment Anchor
On iCopy-X, place files under the scripts directory:
```
/mnt/upan/scripts/icsd4.lua
/mnt/upan/scripts/icsd4.lua.cfg
```
Config is auto-loaded from the script's own directory via `debug.getinfo`, not `./`.

## 3. Configuration
```lua
return {
  port = "/dev/ttyACM0",   -- or nil for auto-detect
  baud = 115200,
  read_timeout_ms = 2000,
  write_timeout_ms = 1000,
  retry_count = 1,
  output_format = "text",   -- "text" or "json"
  log_file = "/mnt/upan/dump/ics_decoder/d4.log",
  auto_detect_d4 = true,
}
```

## 4. CLI Usage
```
lua icsd4.lua --port COM3 who
lua icsd4.lua --port /dev/ttyACM0 read --json
lua icsd4.lua --port /dev/ttyACM0 brute
lua icsd4.lua --port /dev/ttyACM0 interactive
```
If `--port` omitted and `auto_detect_d4=true`, script scans ports and sends `WHO`, picks first responding `ISE`.

## 5. Module API
```lua
local d4 = require("icsd4")  -- or require("icsd4_lua")
local h, err = d4.open("/dev/ttyACM0")
local ok = d4.who(h)
local card = d4.read_card(h)   -- {available, wiedata, bit_count, facility_code, card_id, hex, blk7, bits}
local frame = d4.get_status(h) -- or nil if NO FRAMES
local f = d4.dump_frame(h, 3)  -- slot 0-7
d4.clear_buffer(h)
d4.set_mode(h, "SNIFF")        -- or "BRIDGE"
local ms = d4.set_timeout(h, 50) -- clamped 5-100
local bits = d4.get_live_bits(h)
local res = d4.brute_force(h)
local txt = d4.get_help(h)
local match = d4.auto_brute_and_match(h, 2493837, 858)
d4.close(h)
```

## 6. auto_brute_and_match (The Kill Shot)
Reverse-engineer an unknown card using the inkjet-printed markings:
```lua
local m = d4.auto_brute_and_match(h, target_cn, target_fc)
-- target_cn = card number printed on badge (e.g. 2493837)
-- target_fc = facility code printed on badge (e.g. 858)
if m.match then
  print(m.suggested_format)  -- "FC at start 2, CN at start 24"
  print(m.fc_candidate.start, m.fc_candidate.value)
  print(m.cn_candidate.start, m.cn_candidate.value)
end
```
Examples:
- SE 2k card: `auto_brute_and_match(h, 2493837, 858)` → match true
- Corporate 1000: `auto_brute_and_match(h, 1341, 7874)` → match true

## 7. AVALANCHE WARNING
`brute_force()` on a 256-bit frame emits ~249 FC8, ~235 FC22, ~221 CN36 entries. Terminal output will be huge. In GUIs, paginate or collapse candidate lists. Do not run in tight loops.

## 8. Testing Checklist (Section 11)
- who() true when connected
- read_card() available=false when no card
- read_card() available=true with correct FC/ID for 26/48/56-bit cards
- get_status() nil when empty
- dump_frame(0..7) no errors
- clear_buffer() true then get_status() nil
- set_mode both work
- set_timeout(50)=50, (200)=100, (2)=5
- get_live_bits() integer >=0
- brute_force() all candidate lists populated
- auto_brute_and_match(2493837,858) match=true
- auto_brute_and_match(1341,7874) match=true
- CLI text + --json valid
- All functions handle ?? without crash
- Port close/reopen works
- No UI thread blocking in Phosphor/iCopy-X