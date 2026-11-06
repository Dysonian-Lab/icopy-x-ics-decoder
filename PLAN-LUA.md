# Plan: iCS D4 Lua Serial Bridge Script

**Document version:** 1.0  
**Target audience:** Human engineer implementing a portable Lua script  
**Hardware target:** iCS D4 firmware (`icsd4.ino`) on ATmega32U4 (SparkFun Qwiic Pro Micro USB-C or Arduino Leonardo)  
**Communication:** USB CDC serial at 115200 baud, 8N1, `\n`-terminated lines  
**Protocol:** iCS D4 text command set (Who/RD/STATUS/DUMP/CLEAR/MODE/TIMEOUT/BITS/BRUTE/HELP)  

---

## 1. Objective

Create a portable Lua script that provides programmatic access to the iCS D4 diagnostic sniffer serial command set. The script must run identically in three environments:

1. **CLI** — Standard Lua interpreter on Windows/macOS/Linux
2. **Phosphor GUI** — Phosphor application with Lua scripting support
3. **iCopy-X** — Embedded Lua 5.4 interpreter on iCopy-X hardware

The script exposes every command from the iCS D4 `/?` help menu as a Lua-callable function, parses responses into structured Lua tables, and provides optional high-level helpers (auto-brute force, frame export, card clone staging).

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                     Lua Script                          │
│  ┌─────────────┐  ┌─────────────┐  ┌───────────────┐  │
│  │ CLI mode    │  │ Phosphor    │  │ iCopy-X       │  │
│  │ (stdio)     │  │ (GUI events)│  │ (middleware)  │  │
│  └──────┬──────┘  └──────┬──────┘  └──────┬────────┘  │
│         │                │                │             │
│         └────────────────┴────────────────┘             │
│              Serial Port Abstraction Layer              │
│              (luaserial / luposix / socket)             │
│         │                │                │             │
└─────────┼────────────────┼────────────────┼─────────────┘
          │                │                │
   COM3   /dev/ttyACM0   /dev/ttyUSB0     iCopy-X USB CDC
   Windows   Linux/macOS   Linux             (virtual serial)
```

### Layer responsibilities

| Layer | Responsibility |
|-------|---------------|
| **Transport** | Open/close serial port, set baud 115200 8N1, send lines terminated with `\n`, read lines terminated with `\n` |
| **Protocol** | Encode command strings, parse response text into Lua tables, handle `??` errors and timeouts |
| **Domain** | High-level helpers: `who()`, `read_card()`, `brute_force()`, `export_frame()`, etc. |
| **UI Binding** | CLI: print to stdout. Phosphor: render widgets. iCopy-X: call middleware APIs |

---

## 3. Serial Transport Specification

### Port configuration (all environments)

| Parameter | Value |
|-----------|-------|
| Baud rate | 115200 |
| Data bits | 8 |
| Parity | None |
| Stop bits | 1 |
| Flow control | None |
| Line terminator | `\n` (LF) — iCS D4 strips `\r` but expects `\n` |
| Read timeout | 2000 ms (configurable) |
| Write timeout | 1000 ms |

### Transport API (internal)

```lua
-- Conceptual interface; implementation varies by Lua environment
local transport = {
  open = function(port_path) -> serial_handle or nil, error_string,
  close = function(handle) -> boolean, error_string,
  write_line = function(handle, text) -> boolean, error_string,
  read_line = function(handle, timeout_ms) -> string or nil, error_string,
  set_timeout = function(handle, ms) -> boolean,
}
```

**Environment-specific transport notes:**

| Environment | Recommended library | Notes |
|-------------|--------------------|-------|
| CLI (Lua 5.1/5.2/5.3/5.4) | `luaserial` or `luasocket` + `termios` | `luaserial` preferred for cross-platform serial |
| Phosphor GUI | Built-in serial bindings or FFI to system serial API | Check Phosphor Lua API documentation |
| iCopy-X | Built-in `luaserial` or `io.popen` to `screen`/`cu` | iCopy-X runs Lua 5.4; verify serial library availability at build time |

---

## 4. Protocol Layer

### Command envelope

Every command sent to iCS D4 follows this pattern:

```
<COMMAND>[ <ARG>]\n
```

The iCS D4 responds with one or more lines, each terminated with `\r\n`. Some commands (`RD`, `STATUS`, `DUMP`, `BRUTE`) produce multi-line blocks delimited by `$START$` / `$STOP$` markers.

### Response parsing rules

1. Lines ending with `\r\n` are split into individual lines; `\r` is stripped.
2. A line containing exactly `??` means command not recognized or operation failed.
3. Lines starting with `$` are block delimiters (`$FRAME_START$`, `$FRAME_STOP$`, `$A_CARD_START$`, `$A_CARD_STOP$`).
4. Lines containing `:` are key-value pairs (`Key#: value`).
5. Lines without `:` inside a block are raw data (`wiedata#:` is an exception — it has a `:` but the value is binary string).
6. Multi-line blocks must be accumulated between start/stop markers before parsing.

### Command table

| Command | Argument | Response pattern | Lua function name |
|---------|----------|------------------|-------------------|
| `WHO` | none | `ISE` | `who()` |
| `RD` | none | `OK` + `$A_CARD_START$...$A_CARD_STOP$` or `??` | `read_card()` |
| `STATUS` | none | `$FRAME_START$...$FRAME_STOP$` or `NO FRAMES` | `get_status()` |
| `DUMP` | `n` (0-7) | `$FRAME_START$...$FRAME_STOP$` or `EMPTY` | `dump_frame(slot)` |
| `CLEAR` | none | `CLEARED` | `clear_buffer()` |
| `MODE` | `BRIDGE` or `SNIFF` | `MODE BRIDGE` or `MODE SNIFF` or `??` | `set_mode(mode)` |
| `TIMEOUT` | `ms` (5-100) | `TIMEOUT#:N` or `??` | `set_timeout(ms)` |
| `BITS` | none | `BITS#:N` | `get_live_bits()` |
| `BRUTE` | none | `BRUTE - Frame N bits=M` + bit map + FC8/CN16/CN20/CN24/CN32/CN34/CN36 lists + `BRUTE done` | `brute_force()` |
| `HELP` / `/?` | none | Command list with descriptions | `get_help()` |

---

## 5. Data Structures

### Frame table (returned by STATUS/DUMP/BRUTE)

```lua
local frame = {
  index = number,          -- ring slot (0-7) or 255 for ad-hoc
  bit_count = number,      -- total captured bits
  pulse_count = number,    -- total falling edges
  first_pulse_us = number, -- micros() of first pulse
  last_pulse_us = number,  -- micros() of last pulse
  min_gap_us = number,     -- shortest inter-pulse gap
  max_gap_us = number,     -- longest inter-pulse gap
  overflow = boolean,      -- frame truncated (>256 bits) or ring displaced
  bin = string,            -- binary string MSB-first
  hex = string,            -- hex string lowercase
  guess = string,          -- "26", "34", "35", "37", "48", "56", "64", "OTHER"
  captured_at_ms = number, -- millis() at latch time
}
```

### Card block table (returned by RD)

```lua
local card = {
  available = boolean,     -- true if OK response, false if ??
  wiedata = string,        -- exact-length binary bitstream
  bit_count = number,      -- total captured bits
  facility_code = number or nil,
  card_id = number or nil, -- may exceed 32 bits; use Lua number (double) or string
  hex = string,            -- zero-padded lowercase hex
  blk7 = string,           -- 16-char hex for Proxmark3 block write
  bits = string,           -- zero-padded binary string
}
```

### BRUTE result table (returned by brute_force)

```lua
local brute_result = {
  frame_index = number,
  bit_count = number,
  raw_hex = string,
  bit_map = string,        -- spaced binary with positions
  fc8 = { {start=number, value=number}, ... },   -- all 8-bit FC candidates
  cn16 = { {start=number, value=number}, ... },  -- all 16-bit CN candidates
  cn20 = { {start=number, value=number}, ... },  -- all 20-bit CN candidates
  cn24 = { {start=number, value=number}, ... },  -- all 24-bit CN candidates
  cn32 = { {start=number, value=number}, ... },  -- all 32-bit CN candidates
  cn34 = { {start=number, value=number}, ... },  -- all 34-bit CN candidates
  cn36 = { {start=number, value=number}, ... },  -- all 36-bit CN candidates
}
```

The `cn34` list is critical for the 56-bit Avigilon format (34-bit card number).
Without it, card numbers above 16.7 million would be invisible to BRUTE.

---

## 6. Function Specifications

### 6.1 `who()`

Send `WHO\n`, expect `ISE`. Returns `true` if iCS D4 responds correctly, `false` otherwise.

**Purpose:** Handshake / device detection.

### 6.2 `read_card()`

Send `RD\n`. Parse response:

- If `??`: return `{ available = false }`
- If `OK` + card block: parse all fields into card table, return `{ available = true, ...card fields... }`

**Note:** After `RD`, iCS D4 clears `cardAvailable`. A subsequent `RD` without a new card present returns `??`.

### 6.3 `get_status()`

Send `STATUS\n`. If `NO FRAMES`, return `nil`. Otherwise parse `$FRAME_START$...$FRAME_STOP$` block into frame table.

### 6.4 `dump_frame(slot)`

Send `DUMP n\n` where n is 0-7. Returns frame table or `nil` if `EMPTY`.

**Validation:** `slot` must be integer 0-7. Raise error if out of range.

### 6.5 `clear_buffer()`

Send `CLEAR\n`. Expect `CLEARED`. Returns `true` on success.

### 6.6 `set_mode(mode)`

Send `MODE BRIDGE\n` or `MODE SNIFF\n`. Returns the mode string echoed back, or `nil` on `??`.

**Validation:** `mode` must be `"BRIDGE"` or `"SNIFF"`.

### 6.7 `set_timeout(ms)`

Send `TIMEOUT N\n`. Clamp `ms` to 5-100 locally before sending (iCS D4 clamps server-side too). Returns the actual timeout value set, or `nil` on `??`.

**Validation:** `ms` must be number 5-100.

### 6.8 `get_live_bits()`

Send `BITS\n`. Parse `BITS#:N`. Returns integer bit count or `nil` on error.

### 6.9 `brute_force()`

Send `BRUTE\n`. Parse the full multi-line output:

1. `BRUTE - Frame N bits=M` line
2. `RawHex=...` line
3. `BitMap: ...` line
4. `FC8 (start=value):` section — one line per start position
5. `CN16 (start=value):` section
6. `CN20 (start=value):` section
7. `CN24 (start=value):` section
8. `CN32 (start=value):` section
9. `CN34 (start=value):` section
10. `CN36 (start=value):` section
11. `BRUTE done` line

Returns brute_result table or `nil` if `NO FRAMES`.

### 6.10 `get_help()`

Send `HELP\n` (or `/?\n`). Return the raw help text as a single string with line breaks preserved.

### 6.11 `auto_brute_and_match(target_cn, target_fc)`

**High-level helper.** Calls `brute_force()`, then scans all CN candidate lists for `target_cn` and FC candidate lists for `target_fc`. Returns a match object:

```lua
{
  match = boolean,
  cn_candidate = {start=..., value=...} or nil,
  fc_candidate = {start=..., value=...} or nil,
  suggested_format = string or nil,  -- e.g. "FC at start 2, CN at start 24"
}
```

**Purpose:** Reverse-engineer unknown card formats using card markings.

---

## 7. Environment-Specific Implementations

### 7.1 CLI Mode

**Entry point:** `lua icsd4.lua <command> [args]`

**Commands:**
- `who` — handshake
- `read` — read card block
- `status` — print most recent frame
- `dump <n>` — print ring slot
- `clear` — reset buffer
- `mode <BRIDGE|SNIFF>` — set mode
- `timeout <ms>` — set gap timeout
- `bits` — show live bit count
- `brute` — brute-force FC/CN positions
- `help` — show command list
- `interactive` — REPL mode (read commands from stdin, send to iCS D4, print responses)

**Serial port:** Specified via `--port COM3` (Windows) or `--port /dev/ttyACM0` (Linux/macOS). Default: auto-detect first serial port with "USB" or "ACM" in name.

**Output:** Plain text to stdout. JSON output available with `--json` flag for programmatic consumption.

**Example session:**
```
$ lua icsd4.lua --port COM3 who
ISE

$ lua icsd4.lua --port COM3 read --json
{"available":true,"bit_count":56,"facility_code":858,"card_id":2493837,"hex":"001ad0004c1b1b","blk7":"00001ad0004c1b1b"}

$ lua icsd4.lua --port COM3 brute
BRUTE - Frame 0 bits=56
...
```

### 7.2 Phosphor GUI Mode

**Entry point:** Loaded as a Phosphor Lua script module.

**UI components:**

| Widget | Purpose |
|--------|---------|
| Port selector dropdown | List available serial ports, select one |
| Connect/Disconnect buttons | Open/close serial connection |
| Status indicator | Connected/disconnected, last response |
| Command buttons | Who, Read Card, Status, Dump, Clear, Bits, Brute |
| Mode toggle | BRIDGE / SNIFF |
| Timeout spinner | 5-100 ms |
| Output text area | Scrollable log of all serial traffic |
| Frame table view | Parsed frame fields (bit count, hex, guess, etc.) |
| Card block view | Parsed card fields (FC#, ID#, Hex#, Blk7#) |
| Brute results view | Table of FC8/CN16/CN20/CN24/CN32/CN34/CN36 candidates |
| Target match inputs | Text boxes for expected FC and CN values |
| Match button | Run `auto_brute_and_match()` |

**Event flow:**
1. User selects port and clicks Connect → script opens serial, sends `WHO`, verifies `ISE`
2. User clicks Read Card → script sends `RD`, parses response, populates Card block view
3. User clicks Brute → script sends `BRUTE`, populates Brute results view
4. User enters target CN/FC, clicks Match → script runs `auto_brute_and_match()`, highlights matches

**Threading:** Serial I/O must not block the Phosphor UI thread. Use coroutines or async I/O with callbacks.

### 7.3 iCopy-X Mode

**Entry point:** Loaded as a Lua module by iCopy-X middleware (`src/middleware/ics_decoder.lua` or similar).

**Integration points:**

| iCopy-X component | Lua script interaction |
|-------------------|------------------------|
| Serial port detection | Reuse existing iCopy-X serial port discovery for the SparkFun MCU |
| `read_card()` | Call instead of/in addition to existing ICS Decoder read; merge results |
| Card write routing | After successful read, route FC/CN to existing PM3 write functions (`hf iclass wrbl`, `lf hid clone`, etc.) |
| UI | Add "D4 Sniffer" tab or section in ICS Decoder activity |
| Logging | Write to iCopy-X log directory (`/mnt/upan/dump/ics_decoder/`) |

**iCopy-X-specific constraints:**
- Lua 5.4 only
- Serial port may be `/dev/ttyACM0` or similar; detect by scanning `/dev/` for USB serial devices
- File system access limited to `/mnt/upan/` and `/home/pi/`
- No networking assumed
- Must not block the iCopy-X UI thread; use `startBGTask` pattern from existing middleware

**Integration example:**
```lua
-- In iCopy-X middleware, when user clicks "Read Card" on an unknown SEOS card:
local d4 = require("icsd4_lua")
local port = detect_d4_port()  -- scan /dev/tty* for SparkFun MCU
if port then
  local h = d4.open(port)
  local card = d4.read_card(h)
  if card and card.available then
    -- Stage card data for iCopy-X clone workflow
    stage_for_clone(card.facility_code, card.card_id)
  end
  d4.close(h)
end
```

---

## 8. Error Handling

| Error condition | Detection | Response |
|-----------------|-----------|----------|
| Serial port not found | `open()` returns nil | Return error message; suggest `--port` or port selection |
| Serial port busy | `open()` returns error | Return error; suggest closing other serial monitors |
| No response (timeout) | `read_line()` returns nil after timeout | Retry once (configurable), then return error |
| `??` response | Exact line match | Return `nil` with error message "Command not recognized" |
| Malformed block | Missing `$STOP$` marker | Return partial data with warning; log malformed response |
| Invalid argument | Out of range slot, bad mode | Raise Lua error with descriptive message before sending |
| Card not present | `RD` returns `??` | Return `{ available = false }` — not an error, expected behavior |
| Frame buffer empty | `STATUS` returns `NO FRAMES` | Return `nil` |

All functions return `(result, error_message)` where `error_message` is `nil` on success.

---

## 9. Configuration

Configuration file `icsd4.lua.cfg` (JSON or Lua table), located next to script:

```lua
return {
  port = nil,              -- nil = auto-detect
  baud = 115200,
  read_timeout_ms = 2000,
  write_timeout_ms = 1000,
  retry_count = 1,
  output_format = "text",  -- "text" or "json"
  log_file = nil,          -- nil = no logging; or path to log file
  auto_detect_d4 = true,   -- automatically scan for iCS D4 on startup
}
```

**Auto-detection heuristic:** Scan all available serial ports. On each, open at 115200, send `WHO`, wait 500ms for `ISE`. First port responding with `ISE` is the iCS D4.

---

## 10. Build & Usage Instructions

### Prerequisites

| Environment | Required |
|-------------|----------|
| CLI | Lua 5.1+, `luaserial` (or `luasocket`) |
| Phosphor | Phosphor application with Lua scripting enabled |
| iCopy-X | iCopy-X firmware with Lua 5.4 support; serial port access |

### Installation

1. Copy `icsd4.lua` to desired location
2. Install `luaserial` (CLI only): `luaruby install luaserial` or platform package manager
3. For iCopy-X: place `icsd4.lua` in middleware directory and `require` it from `ics_decoder.lua`

### Usage examples

**CLI — Read a card:**
```bash
lua icsd4.lua --port COM3 read
```

**CLI — Brute force unknown format:**
```bash
lua icsd4.lua --port /dev/ttyACM0 brute --json
```

**CLI — Interactive REPL:**
```bash
lua icsd4.lua --port COM3 interactive
> who
ISE
> status
$FRAME_START$
...
```

**iCopy-X middleware:**
```lua
local d4 = require("icsd4_lua")
local card = d4.read_card("/dev/ttyACM0")
if card and card.available then
  -- Proceed with clone workflow
end
```

---

## 11. Testing Checklist

Before handoff is considered complete, verify:

- [ ] `who()` returns `true` when iCS D4 is connected and in any mode
- [ ] `read_card()` returns `available = false` when no card has been presented
- [ ] `read_card()` returns `available = true` with correct FC/ID after presenting a known card (26-bit, 48-bit Corporate 1000, 56-bit Avigilon)
- [ ] `get_status()` returns `nil` when ring buffer is empty
- [ ] `get_status()` returns a frame table after a card capture
- [ ] `dump_frame(0)` through `dump_frame(7)` work without errors
- [ ] `clear_buffer()` returns `true` and subsequent `get_status()` returns `nil`
- [ ] `set_mode("SNIFF")` and `set_mode("BRIDGE")` both work
- [ ] `set_timeout(50)` returns `50`; `set_timeout(200)` clamps to `100`; `set_timeout(2)` clamps to `5`
- [ ] `get_live_bits()` returns integer >= 0
- [ ] `brute_force()` returns table with all four candidate lists populated
- [ ] `auto_brute_and_match(2493837, 858)` returns `match = true` for the SE 2k card
- [ ] `auto_brute_and_match(1341, 7874)` returns `match = true` for the Corporate 1000 card
- [ ] CLI mode prints readable text output
- [ ] CLI mode with `--json` produces valid JSON
- [ ] All functions handle `??` responses without crashing
- [ ] Serial port close works cleanly; reopen works
- [ ] Script does not block UI thread in Phosphor or iCopy-X environments

---

## 12. Known Limitations (Documented for Engineer)

1. **RD clears card state:** After a successful `read_card()`, the iCS D4 clears `cardAvailable`. The card must be re-presented for the next `read_card()` call.
2. **56-bit truncation in Blk7:** `Blk7#` is always 16 hex chars (64 bits). For 56-bit cards, `Blk7#` contains only the low 64 bits. Use `Hex#` for full 56-bit data.
3. **Brute-force candidate lists grow with bit count:** For 256-bit frames, `FC8` has 249 entries, `CN36` has 221 entries. Output may be long; consider pagination in GUI.
4. **No automatic format detection:** The script does not guess which FC/CN candidate is correct. The engineer must use `auto_brute_and_match()` with known card markings or manually inspect `BRUTE` output.
5. **Serial port exclusivity:** Only one process can hold the serial port at a time. Close Arduino Serial Monitor before running the script.

---

## 13. File Deliverables

| File | Purpose |
|------|---------|
| `icsd4.lua` | Main Lua script (all environments) |
| `icsd4.lua.cfg` | Example configuration file |
| `PLAN-LUA.md` | This plan document |
| `TESTING.md` | Step-by-step test procedures (derived from section 11) |

---

**End of plan.** This document is sufficient for a human engineer to implement the Lua script without further clarification. All command formats, response patterns, data structures, and environment-specific considerations are specified.