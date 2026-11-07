-- icsd4.lua — portable Lua serial bridge for iCS D4 diagnostic sniffer
-- Works in CLI / Phosphor GUI / iCopy-X environments.

-- ---------- Configuration ----------
local function script_dir()
  local src = debug.getinfo(1, "S").source or ""
  if src:sub(1,1) == "@" then src = src:sub(2) end
  return src:match("^(.*[/\\])") or "./"
end

local config = {
  port = nil, baud = 115200, read_timeout_ms = 2000,
  write_timeout_ms = 1000, retry_count = 1, output_format = "text",
  log_file = nil, auto_detect_d4 = true,
}

local function load_config(path)
  path = path or (script_dir() .. "icsd4.lua.cfg")
  local f = loadfile(path)
  if not f then return nil end
  local ok, t = pcall(f)
  if ok and type(t) == "table" then
    for k,v in pairs(t) do config[k] = v end
    return config
  end
  return nil
end

load_config()

M.config = config
M.load_config = load_config
M.script_dir = script_dir
local function try_require(name)
  local ok, mod = pcall(require, name)
  if ok then return mod end
  return nil
end

local luaserial = try_require("luaserial") or try_require("serial")

local function open_port(path)
  if luaserial then
    local ok, h = pcall(luaserial.open, path, config.baud or 115200)
    if not ok or not h then return nil, h or "open failed" end
    if h.settimeout then h:settimeout((config.read_timeout_ms or 2000)/1000) end
    return h, nil
  end
  return nil, "no serial library available"
end

local function close_port(h)
  if h and h.close then h:close() end
  return true
end

local function write_line(h, text)
  if not h then return false, "no handle" end
  local data = text .. "\n"
  if h.write then
    local ok, err = pcall(h.write, h, data)
    if not ok then return false, err end
    return true
  end
  return false, "write unsupported"
end

local function read_line(h, timeout_ms)
  if not h then return nil, "no handle" end
  timeout_ms = timeout_ms or 2000
  if h.read then
    local ok, line = pcall(h.read, h, timeout_ms)
    if not ok then return nil, line end
    if line == nil then return nil, "timeout" end
    line = tostring(line):gsub("\r", "")
    return line, nil
  end
  return nil, "read unsupported"
end

-- ---------- Helpers ----------
local function read_block(h, start_marker, stop_marker)
  local lines = {}
  local timeout = 2000
  local deadline = os.clock() + timeout / 1000
  -- send nothing; caller already sent. Collect until stop marker or timeout.
  while os.clock() < deadline do
    local line, err = read_line(h, 200)
    if not line then break end
    table.insert(lines, line)
    if line:find(stop_marker, 1, true) then break end
    if line == "??" then break end
  end
  return lines
end

local function read_response(h)
  -- collect lines until timeout or stop marker
  local lines = {}
  local deadline = os.clock() + 2
  while os.clock() < deadline do
    local line, err = read_line(h, 200)
    if not line then break end
    table.insert(lines, line)
    if line:find("$", 1, true) and line:find("STOP", 1, true) then break end
    if line == "BRUTE done" then break end
    if line == "CLEARED" or line == "ISE" or line:match("^MODE ") or line:match("^TIMEOUT#") or line:match("^BITS#") then
      -- single-line responses: stop after first meaningful line
      if not line:find("$", 1, true) then break end
    end
    if line == "??" then break end
    if line == "NO FRAMES" or line == "EMPTY" then break end
  end
  return lines
end

local function send_cmd(h, cmd)
  write_line(h, cmd)
  return read_response(h)
end

-- ---------- Parsers ----------
local function parse_frame_lines(lines)
  local f = {}
  local inblock = false
  for _, ln in ipairs(lines) do
    if ln == "$FRAME_START$" then inblock = true
    elseif ln == "$FRAME_STOP$" then break
    elseif inblock then
      local k, v = ln:match("^(.-)#:%s*(.*)$")
      if k and v then
        k = k:gsub("#", "")
        if k == "Index" then f.index = tonumber(v)
        elseif k == "Bit" then f.bit_count = tonumber(v)
        elseif k == "Pulses" then f.pulse_count = tonumber(v)
        elseif k == "FirstUs" then f.first_pulse_us = tonumber(v)
        elseif k == "LastUs" then f.last_pulse_us = tonumber(v)
        elseif k == "MinGapUs" then f.min_gap_us = tonumber(v)
        elseif k == "MaxGapUs" then f.max_gap_us = tonumber(v)
        elseif k == "Overflow" then f.overflow = (tonumber(v) ~= 0)
        elseif k == "Bin" then f.bin = v
        elseif k == "Hex" then f.hex = v
        elseif k == "Guess" then f.guess = v
        elseif k == "CapturedAtMs" then f.captured_at_ms = tonumber(v) end
      end
    end
  end
  if not f.bit_count then return nil end
  return f
end

local function parse_card_lines(lines)
  local card = { available = false }
  local inblock = false
  local raw_lines = lines
  -- check for ??
  for _, ln in ipairs(lines) do
    if ln == "??" then return { available = false } end
    if ln == "OK" then card.available = true end
  end
  for _, ln in ipairs(lines) do
    if ln == "$A_CARD_START$" then inblock = true
    elseif ln == "$A_CARD_STOP$" then break
    elseif inblock then
      -- wiedata#:...
      local key, val = ln:match("^(.-)#:(.*)$")
      if key and val then
        key = key:gsub("#", "")
        if key == "wiedata" then card.wiedata = val
        elseif key == "Bit" then card.bit_count = tonumber(val)
        elseif key == "FC" then card.facility_code = tonumber(val)
        elseif key == "ID" then card.card_id = tonumber(val)
        elseif key == "Hex" then card.hex = val
        elseif key == "Blk7" then card.blk7 = val
        elseif key == "Bits" then card.bits = val end
      end
    end
  end
  if not card.available then return { available = false } end
  return card
end

-- ---------- Public API (handle-based) ----------
function M.open(port_path)
  return open_port(port_path)
end
function M.close(h)
  return close_port(h)
end

function M.who(h)
  local lines = send_cmd(h, "WHO")
  for _, ln in ipairs(lines) do
    if ln == "ISE" then return true, nil end
  end
  return false, "no ISE response"
end

function M.read_card(h)
  local lines = send_cmd(h, "RD")
  local card = parse_card_lines(lines)
  return card, nil
end

function M.get_status(h)
  local lines = send_cmd(h, "STATUS")
  for _, ln in ipairs(lines) do
    if ln == "NO FRAMES" then return nil, nil end
  end
  return parse_frame_lines(lines), nil
end

function M.dump_frame(h, slot)
  if type(slot) ~= "number" or slot < 0 or slot > 7 or slot ~= math.floor(slot) then
    error("slot must be integer 0-7")
  end
  local lines = send_cmd(h, "DUMP " .. tostring(slot))
  for _, ln in ipairs(lines) do
    if ln == "EMPTY" then return nil, nil end
  end
  return parse_frame_lines(lines), nil
end

function M.clear_buffer(h)
  local lines = send_cmd(h, "CLEAR")
  for _, ln in ipairs(lines) do
    if ln == "CLEARED" then return true, nil end
  end
  return false, "not cleared"
end

function M.set_mode(h, mode)
  if mode ~= "BRIDGE" and mode ~= "SNIFF" then
    error("mode must be BRIDGE or SNIFF")
  end
  local lines = send_cmd(h, "MODE " .. mode)
  for _, ln in ipairs(lines) do
    local m = ln:match("^MODE (%w+)$")
    if m then return m, nil end
    if ln == "??" then return nil, "not recognized" end
  end
  return nil, "no response"
end

function M.set_timeout(h, ms)
  if type(ms) ~= "number" then error("ms must be number") end
  if ms < 5 then ms = 5 end
  if ms > 100 then ms = 100 end
  local lines = send_cmd(h, "TIMEOUT " .. tostring(math.floor(ms)))
  for _, ln in ipairs(lines) do
    local n = ln:match("^TIMEOUT#:(%d+)$")
    if n then return tonumber(n), nil end
    if ln == "??" then return nil, "not recognized" end
  end
  return nil, "no response"
end

function M.get_live_bits(h)
  local lines = send_cmd(h, "BITS")
  for _, ln in ipairs(lines) do
    local n = ln:match("^BITS#:(%d+)$")
    if n then return tonumber(n), nil end
  end
  return nil, "no response"
end

function M.brute_force(h)
  local lines = send_cmd(h, "BRUTE")
  for _, ln in ipairs(lines) do
    if ln == "NO FRAMES" then return nil, nil end
  end
  local res = {
    fc8 = {}, fc16 = {}, fc20 = {}, fc22 = {},
    cn16 = {}, cn20 = {}, cn24 = {}, cn32 = {}, cn34 = {}, cn36 = {},
  }
  local section = nil
  for _, ln in ipairs(lines) do
    local m = ln:match("^BRUTE %- Frame (%d+) bits=(%d+)$")
    if m then res.frame_index = tonumber(m); res.bit_count = tonumber(m:match("%d+$") or ln:match("bits=(%d+)")) end
    local rh = ln:match("^RawHex=(.+)$")
    if rh then res.raw_hex = rh end
    local bm = ln:match("^BitMap:%s*(.*)$")
    if bm then res.bit_map = bm end
    -- section headers
    for _, name in ipairs({"FC8","FC16","FC20","FC22","CN16","CN20","CN24","CN32","CN34","CN36"}) do
      if ln:match("^" .. name .. " %(") then section = name:lower() end
    end
    -- candidate lines: "  start=value"
    local s, v = ln:match("^%s*(%d+)=(%d+)$")
    if s and v and section then
      local key = section
      table.insert(res[key], { start = tonumber(s), value = tonumber(v) })
    end
  end
  -- fix bit_count parse
  for _, ln in ipairs(lines) do
    local b = ln:match("bits=(%d+)")
    if b then res.bit_count = tonumber(b) end
  end
  return res, nil
end

function M.get_help(h)
  local lines = send_cmd(h, "HELP")
  return table.concat(lines, "\n"), nil
end

function M.auto_brute_and_match(h, target_cn, target_fc)
  local res = M.brute_force(h)
  if not res then return { match = false } end
  local cn_cand, fc_cand
  for _, list in ipairs({res.cn16,res.cn20,res.cn24,res.cn32,res.cn34,res.cn36}) do
    for _, c in ipairs(list) do
      if c.value == target_cn then cn_cand = c; break end
    end
    if cn_cand then break end
  end
  for _, list in ipairs({res.fc8,res.fc16,res.fc20,res.fc22}) do
    for _, c in ipairs(list) do
      if c.value == target_fc then fc_cand = c; break end
    end
    if fc_cand then break end
  end
  local match = (cn_cand ~= nil and fc_cand ~= nil)
  local suggested
  if match then
    suggested = "FC at start " .. fc_cand.start .. ", CN at start " .. cn_cand.start
  end
  return { match = match, cn_candidate = cn_cand, fc_candidate = fc_cand, suggested_format = suggested }
end

-- ---------- Convenience: open by port string in middleware ----------
M.read_card_by_port = function(port)
  local h, err = M.open(port)
  if not h then return nil, err end
  local card = M.read_card(h)
  M.close(h)
  return card, nil
end

-- ---------- CLI ----------
local function parse_args(argv)
  local opts = { port = nil, json = false, cmd = nil, args = {} }
  local i = 1
  while i <= #argv do
    local a = argv[i]
    if a == "--port" then opts.port = argv[i+1]; i = i + 2
    elseif a == "--json" then opts.json = true; i = i + 1
    else
      if not opts.cmd then opts.cmd = a else table.insert(opts.args, a) end
      i = i + 1
    end
  end
  return opts
end

local function json_encode(v)
  if type(v) == "boolean" then return v and "true" or "false"
  elseif type(v) == "number" then return tostring(v)
  elseif type(v) == "string" then return '"' .. v:gsub('"','\\"') .. '"'
  elseif type(v) == "table" then
    -- array vs object
    local is_arr = (#v > 0)
    if is_arr then
      local parts = {}
      for _, x in ipairs(v) do table.insert(parts, json_encode(x)) end
      return "[" .. table.concat(parts, ",") .. "]"
    else
      local parts = {}
      for k, val in pairs(v) do
        if type(val) ~= "function" then
          table.insert(parts, '"' .. tostring(k) .. '":' .. json_encode(val))
        end
      end
      return "{" .. table.concat(parts, ",") .. "}"
    end
  else return "null" end
end

local function run_cli(argv)
  local opts = parse_args(argv)
  if not opts.port and config.port then opts.port = config.port end
  local port = opts.port
  if not port and config.auto_detect_d4 then
    -- auto detect
    for _, p in ipairs({"/dev/ttyACM0","/dev/ttyUSB0","COM3","COM4"}) do
      local h = M.open(p)
      if h then
        local ok = M.who(h)
        if ok then port = p; M.close(h); break end
        M.close(h)
      end
    end
  end
  if not port then
    print("No port found. Use --port")
    return
  end
  local h, err = M.open(port)
  if not h then print("open failed: " .. tostring(err)); return end
  if opts.json == false and config.output_format == "json" then opts.json = true end
  local res
  if cmd == "who" then
    local ok = M.who(h); res = ok and "ISE" or "??"
    print(res)
  elseif cmd == "read" then
    local card = M.read_card(h)
    if opts.json then print(json_encode(card)) else
      if card.available then
        print("available=true")
        print("bit_count=" .. tostring(card.bit_count))
        print("facility_code=" .. tostring(card.facility_code))
        print("card_id=" .. tostring(card.card_id))
      else print("available=false") end
    end
  elseif cmd == "status" then
    local f = M.get_status(h)
    if not f then print("NO FRAMES") else
      if opts.json then print(json_encode(f)) else
        for k,v in pairs(f) do print(k .. "=" .. tostring(v)) end
      end
    end
  elseif cmd == "dump" then
    local slot = tonumber(opts.args[1] or "0")
    local f = M.dump_frame(h, slot)
    if not f then print("EMPTY") else
      for k,v in pairs(f) do print(k .. "=" .. tostring(v)) end
    end
  elseif cmd == "clear" then
    print(M.clear_buffer(h) and "CLEARED" or "??")
  elseif cmd == "mode" then
    local m = M.set_mode(h, (opts.args[1] or ""):upper())
    print(m or "??")
  elseif cmd == "timeout" then
    local ms = tonumber(opts.args[1] or "25")
    local r = M.set_timeout(h, ms)
    print(r and ("TIMEOUT#:" .. r) or "??")
  elseif cmd == "bits" then
    local b = M.get_live_bits(h)
    print(b and ("BITS#:" .. b) or "??")
  elseif cmd == "brute" then
    local r = M.brute_force(h)
    if not r then print("NO FRAMES")
    else
      print("BRUTE - Frame " .. tostring(r.frame_index) .. " bits=" .. tostring(r.bit_count))
      print("RawHex=" .. tostring(r.raw_hex))
      if opts.json then print(json_encode(r)) end
    end
  elseif cmd == "help" then
    print(M.get_help(h))
  elseif cmd == "interactive" then
    while true do
      io.write("> "); io.flush()
      local line = io.read()
      if not line then break end
      write_line(h, line)
      local resp = read_response(h)
      for _, l in ipairs(resp) do print(l) end
    end
  else
    print("unknown command: " .. cmd)
  end
  M.close(h)
end

-- Detect CLI invocation
if arg and #arg > 0 then
  run_cli(arg)
else
  -- module mode: return M
end

return M
