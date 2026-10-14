"""ics_decoder   ICS Decoder (ATmega32U4) serial bridge.

Bridges the DIY decoder firmware to the existing iCLASS write path.
Protocol:
  Host -> Dev : Who\r\n   -> Dev -> Host : ISE\r\n
  Host -> Dev : RD\r\n    -> Dev -> Host : OK\r\n + $A_CARD_START$...$A_CARD_STOP$
  or                      -> Dev -> Host : ??\r\n  (no card)
"""

import glob
import base64
import re
import os
import sys
import time
import threading

try:
    import serial
    from serial.tools.list_ports import comports as _comports
except ImportError:
    serial = None
    _comports = None

try:
    import iclasswrite
except ImportError:
    try:
        from . import iclasswrite
    except ImportError:
        iclasswrite = None

_BAUD_RATE = 115200
_CMD_WHO = 'Who\r\n'
_CMD_RD = 'RD\r\n'
_READLINE_TIMEOUT = 1.2  # USB CDC ACM needs >=1.0s for reliable WHO response

_LOG_DIR = '/mnt/upan/dump/ics_decoder'
_current_log_file = None
_pm3_lock = threading.Lock()


def _pm3_exec(cmd, timeout_ms=3000, retries=0):
    """Execute a PM3 command via executor with crash recovery.

    On iCopy-X hardware, PM3 commands can trigger rftask restarts
    (FPGA-level crashes). When startPM3Task returns -1 (timeout/crash),
    we retry up to *retries* times with a brief delay to let rftask
    recover.

    Serialises all PM3 hardware access via _pm3_lock so that the
    background poll thread and the UI write thread cannot collide on
    /dev/ttyACM0 simultaneously.

    Args:
        cmd: PM3 command string (e.g. 'hf iclass rdbl --blk 06 -k ...')
        timeout_ms: timeout for startPM3Task (0 = use default)
        retries: number of retries on -1 (crash/timeout)

    Returns:
        (ret, output) tuple on success, None if all retries failed.
    """
    import executor
    with _pm3_lock:
        for attempt in range(retries + 1):
            _log("PM3_CMD: {}".format(cmd))
            ret = executor.startPM3Task(cmd, timeout=timeout_ms)
            output = executor.getPrintContent()
            if not output:
                time.sleep(0.05)
                output = executor.getPrintContent()
            if output:
                output = output.strip()
            _log("PM3_REPLY: ret={} output={}".format(ret, (output[:200] if output else 'None')))
            if ret != -1:
                if not output:
                    _log("PM3_REPLY: WARNING ret={} but output empty after getPrintContent retry".format(ret))
                return (ret, output)
            if attempt < retries:
                _log("PM3_RETRY: attempt {}/{} after crash (ret=-1)".format(attempt + 1, retries + 1))
                time.sleep(0.5)
        _log("PM3_REPLY: all {} retries exhausted for cmd: {}".format(retries + 1, cmd))
    return None


def _get_log_filepath():
    global _current_log_file
    if _current_log_file:
        return _current_log_file
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        existing = [
            f for f in os.listdir(_LOG_DIR)
            if f.endswith('.log') and f[:-4].isdigit()
        ]
        nums = [int(f[:-4]) for f in existing]
        next_num = max(nums) + 1 if nums else 1
        _current_log_file = os.path.join(_LOG_DIR, "{:03d}.log".format(next_num))
        return _current_log_file
    except Exception:
        return None


def _log(msg):
    """Write timestamped log to numbered file in /mnt/upan/dump/ics_decoder/.

    Uses line buffering (buffering=1) in append mode. Never raises.
    """
    try:
        path = _get_log_filepath()
        if not path:
            return
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        with open(path, 'a', encoding='utf-8', buffering=1) as f:
            f.write("[{}] {}\n".format(timestamp, msg))
    except Exception:
        pass


def reset_log_session():
    """Resets the cached log file so the next card operation rolls to the next incremented log file."""
    global _current_log_file
    _current_log_file = None


def _open_serial(port):
    if serial is None:
        return None
    try:
        ser = serial.Serial(port, _BAUD_RATE, timeout=_READLINE_TIMEOUT)
        return ser
    except Exception:
        return None


def detect_decoder():
    """Scan serial ports for the ICS Decoder.

    Returns the serial handle if a device replies with ISE to Who,
    otherwise closes any opened handle and returns None.

    Uses strict timeouts to prevent UI blocking.
    """
    _log('DETECT_DECODER_START')
    _log('CWD={}'.format(os.getcwd()))
    _log('LOG_PATH={}'.format(_get_log_filepath()))

    if serial is None:
        _log('DETECT_DECODER: serial module is None')
        return None

    candidates = []

    if sys.platform.startswith('linux'):
        for g in ('/dev/ttyACM*', '/dev/ttyUSB*'):
            candidates.extend(glob.glob(g))
        seen = set()
        candidates = [c for c in candidates if not (c in seen or seen.add(c))]
        candidates = [p for p in candidates if not p.endswith('ttyACM0')]
    elif sys.platform.startswith('win'):
        if _comports is not None:
            try:
                candidates = [p.device for p in _comports()]
            except Exception:
                candidates = []
        if not candidates:
            for i in range(1, 257):
                candidates.append('COM%d' % i)
    elif sys.platform.startswith('darwin'):
        for g in ('/dev/cu.usbmodem*', '/dev/cu.usbserial*'):
            candidates.extend(glob.glob(g))
        seen = set()
        candidates = [c for c in candidates if not (c in seen or seen.add(c))]

    _log('DETECT_DECODER candidates={}'.format(candidates))

    for port in candidates:
        ser = _open_serial(port)
        if ser is None:
            continue
        try:
            # Small delay for decoder to stabilize after port open
            time.sleep(0.1)
            # Flush any stale data in input buffer
            ser.reset_input_buffer()
            ser.write(_CMD_WHO.encode('utf-8'))
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            _log('DETECT_DECODER port={} response={}'.format(port, line))
            if 'ISE' in line:
                _log('DETECT_DECODER FOUND {}'.format(port))
                return ser  # Return OPEN port - do NOT close
        except Exception as e:
            _log('DETECT_DECODER port={} error={}'.format(port, e))
        # Only close on error/failure, not on success
        try:
            ser.close()
        except Exception:
            pass

    _log('DETECT_DECODER: no decoder found')
    return None


def read_card(ser):
    """Send RD and read a card block from the decoder.

    Returns a parsed dict (see parse_block) or None on no-card. Disconnection raises ConnectionError.
    """
    if ser is None or not ser.is_open:
        raise ConnectionError('Decoder unavailable')

    try:
        ser.write(_CMD_RD.encode('utf-8'))
    except Exception as error:
        raise ConnectionError('Decoder command failed') from error

    response = bytearray()
    frame_started = False
    status_only = True
    serial_timeout = getattr(ser, 'timeout', None)
    if not isinstance(serial_timeout, (int, float)) or serial_timeout <= 0:
        serial_timeout = _READLINE_TIMEOUT
    deadline = time.monotonic() + 4 * serial_timeout
    while time.monotonic() < deadline and len(response) < 65536:
        try:
            raw = ser.readline()
            if not raw:
                break
            response.extend(raw)
            line = raw.decode('utf-8', errors='replace').strip('\x00 \t\r\n')
        except Exception:
            if response:
                result = parse_block(response.decode('utf-8', errors='replace'), bytes(response))
                result['status'] = 'decoder_error'
                return result
            raise ConnectionError('Decoder response failed')

        if not line:
            continue

        if line == '$A_CARD_START$':
            frame_started = True
        if line not in ('OK', '??'):
            status_only = False
        if frame_started and line == '$A_CARD_STOP$':
            break

        # Preserve our SEOS_READ/SEOS_PARSE debug logging for card trace
        if line.startswith('Blk7#') or line.startswith('SIO#') or line.startswith('PACS#'):
            _log('SEOS_READ line={}'.format(line))

    if not response or (not frame_started and status_only):
        _log('SEOS_READ: no card (status_only={})'.format(status_only))
        return None
    result = parse_block(response.decode('utf-8', errors='replace'), bytes(response))

    # Preserve SEOS_PARSE debug line
    _log('SEOS_PARSE fc={} id={} raw={} blk7={}'.format(
        result.get('fc', ''),
        result.get('id', ''),
        result.get('raw', ''),
        result.get('blk7', '')))

    return result


def parse_block(text, raw_bytes=None):
    """Parse a framed response, preserving source bytes and unsupported fields.

    Reconciled from upstream v1.1.7 architecture with our SEOS_READ/SEOS_PARSE
    debug hooks preserved.
    """
    if raw_bytes is None:
        raw_bytes = text.encode('utf-8')
    result = {
        'raw_response_b64': base64.b64encode(raw_bytes).decode('ascii'),
        'raw_response_text': text,
        'raw_fields': {},
        'format': 'Unknown/Unsupported',
        'status': 'unsupported',
    }
    lines = [line.strip('\x00 \t\r\n') for line in text.splitlines()]
    try:
        start = lines.index('$A_CARD_START$')
        stop = lines.index('$A_CARD_STOP$', start + 1)
    except ValueError:
        result['status'] = 'malformed'
        return result
    if '$A_CARD_START$' in lines[start + 1:stop]:
        result['status'] = 'malformed'
        return result
    body = '\n'.join(lines[start + 1:stop])
    names = {
        'blk7': 'raw_blk7', 'wiedata': 'wiedata', 'bit': 'bit',
        'bits': 'bits', 'fc': 'reported_fc', 'id': 'reported_id',
        'hex': 'hex', 'sio': 'sio_pacs', 'pacs': 'sio_pacs',
        'sio_container': 'sio_container', 'container': 'sio_container',
        'technology': 'source_technology',
    }
    for line in body.splitlines():
        if ':' not in line or '#' not in line.split(':', 1)[0]:
            continue
        key, value = line.split(':', 1)
        key = key.strip().rstrip('#').lower()
        value = value.strip()
        result['raw_fields'][key] = value
        field = names.get(key)
        if field and value:
            result[field] = value

    bit_text = result.get('bit')
    if bit_text and bit_text.isdigit():
        result['bit_length'] = int(bit_text)
    elif re.fullmatch(r'[01]+', result.get('bits', '')):
        result['bit_length'] = len(result['bits'])
    result.pop('bit', None)

    raw_blk7 = result.get('raw_blk7', '').replace(' ', '')
    if re.fullmatch(r'[0-9A-Fa-f]{16}', raw_blk7) and int(raw_blk7, 16) != 0:
        result['derived_legacy'] = {'blk7': raw_blk7.upper(), 'source': 'decoder_reported'}
        result['blk7'] = raw_blk7.upper()

    if result.get('bit_length') == 26:
        reported_fc = result.get('reported_fc', '')
        reported_id = result.get('reported_id', '')
        if reported_fc.isdigit() and reported_id.isdigit():
            fc, card_id = int(reported_fc), int(reported_id)
            frame = result.get('wiedata', '')
            if (0 <= fc <= 255 and 0 <= card_id <= 65535 and (fc or card_id) and
                    re.fullmatch(r'[01]{26}', frame) and
                    int(frame, 2) == calculate_wiegand26_parity(fc, card_id)):
                result.update(fc=fc, id=card_id, raw=hex(int(frame, 2)),
                              format='H10301 (26-bit)', status='decoded')
        if result['status'] != 'decoded':
            for field, parser in (('sio_pacs', parse_sio_pacs), ('hex', parse_sio_pacs)):
                parsed = parser(result.get(field), bit_length=26)
                if parsed['valid']:
                    result.update(fc=parsed['fc'], id=parsed['cn'],
                                  raw=parsed['raw_26bit'], format='H10301 (26-bit)', status='decoded')
                    break
    return result


def extract_and_shift_wiegand(payload_bytes: bytes, bit_length=None) -> dict:
    """Strip ASN.1 Tag 85 if present, extract padding byte NN,
    and apply right-shift to construct the Wiegand frame.

    Handles both raw decrypted payloads ([NN] [Payload]) and
    ASN.1 TLV containers with Tag 0x85 (PACS payload container).

    Args:
        payload_bytes: Raw bytes from decoder (with or without ASN.1 wrapper)
        bit_length: Expected bit length (only 26-bit supported)

    Returns:
        Dict with keys: valid, fc, cn, shifted_hex
    """
    if bit_length is not None and bit_length != 26:
        return {"valid": False}
    data = payload_bytes

    if len(data) > 2 and data[0] == 0x85:
        length = data[1]
        if length != len(data) - 2:
            return {"valid": False}
        data = data[2:2 + length]

    if len(data) < 5 or data[0] > 7:
        return {"valid": False, "fc": 0, "cn": 0, "shifted_hex": "0"}

    shift_nn = data[0]
    payload_data = data[1:]

    raw_int = int.from_bytes(payload_data, byteorder="big")
    shifted = raw_int >> shift_nn
    if shifted == 0 or shifted >= (1 << 26):
        return {"valid": False}

    fc = (shifted >> 17) & 0xFF
    cn = (shifted >> 1) & 0xFFFF
    if calculate_wiegand26_parity(fc, cn) != shifted:
        return {"valid": False}

    return {
        "valid": True,
        "fc": fc,
        "cn": cn,
        "shifted_hex": hex(shifted)
    }


def parse_sio_pacs(hex_string, bit_length=None):
    """Parse SEOS SIO PACS payload to extract FC and Card Number.

    SIO PACS Wiegand Format (Black Hat Asia 2025 - Iceman & evildaemond):
        [NN] [Payload Bytes]
        NN = number of trailing zero padding bits

    Extraction:
        1. Read shift count NN = payload[0]
        2. Convert remaining bytes to integer bitstream (big-endian)
        3. Right-shift bitstream by NN bits (>> NN)
        4. Parse 26-bit Wiegand frame from result

    26-bit Wiegand Frame (H10301):
        [P_even (1b)] [FC (8b)] [CN (16b)] [P_odd (1b)]

    Args:
        hex_string: Hex string of SIO PACS payload (e.g., "061B7D0040")
        bit_length: Expected bit length (only 26-bit supported)

    Returns:
        Dict with keys: fc, cn, raw_26bit, valid
    """
    if not hex_string or (bit_length is not None and bit_length != 26):
        return {"fc": 0, "cn": 0, "raw_26bit": "0", "valid": False}

    try:
        hex_string = hex_string.strip().replace(' ', '').replace(':', '')
        if len(hex_string) < 4:
            return {"fc": 0, "cn": 0, "raw_26bit": "0", "valid": False}

        raw_bytes = bytes.fromhex(hex_string)
        result = extract_and_shift_wiegand(raw_bytes, bit_length=bit_length)
        if result['valid']:
            return {
                "fc": result['fc'],
                "cn": result['cn'],
                "raw_26bit": result['shifted_hex'],
                "valid": True
                       }
        return {"fc": 0, "cn": 0, "raw_26bit": "0", "valid": False}
    except Exception:
        return {"fc": 0, "cn": 0, "raw_26bit": "0", "valid": False}


def parse_sio_container(hex_string, bit_length=None):
    """Parse SEOS SIO ASN.1 TLV container to extract PACS payload.

    SEOS SIO Container Format (ASN.1 TLV):
        Tag 85: Encrypted PACS data (cipher bytes + 16-byte MAC)
        Tag Other: Additional data objects

    The ICS Decoder hardware performs:
        1. ISO 7816 ADF selection (00 A4 04 00...)
        2. Challenge-response mutual authentication
        3. EAX/EAX' decryption with diversified KDF key
        4. Output of decrypted PACS payload (with NN padding byte)

    This function handles raw container output from the decoder if it
    outputs the ASN.1 TLV format instead of pre-parsed PACS.

    Args:
        hex_string: Hex string of raw SIO container
        bit_length: Expected bit length (only 26-bit supported)

    Returns:
        Dict with keys: fc, cn, raw_26bit, valid
    """
    if not hex_string or (bit_length is not None and bit_length != 26):
        return {"fc": 0, "cn": 0, "raw_26bit": "0", "valid": False}

    try:
        hex_string = hex_string.strip().replace(' ', '').replace(':', '')
        data = bytes.fromhex(hex_string)
        result = extract_and_shift_wiegand(data, bit_length=bit_length)
        if result['valid']:
            return {
                "fc": result['fc'],
                "cn": result['cn'],
                "raw_26bit": result['shifted_hex'],
                "valid": True
                       }
        return {"fc": 0, "cn": 0, "raw_26bit": "0", "valid": False}
    except Exception:
        return {"fc": 0, "cn": 0, "raw_26bit": "0", "valid": False}


def _extract_tlv_tag(data, target_tag):
    """Extract value from ASN.1 TLV encoded data.

    Simple TLV parser for SEOS SIO containers.
    Format: [Tag] [Length] [Value]

    Args:
        data: Bytes of TLV encoded data
        target_tag: Tag byte to extract (e.g., 0x85 for PACS)

    Returns:
        Bytes of the tag's value, or None if not found
    """
    i = 0
    while i < len(data) - 2:
        tag = data[i]
        length = data[i + 1]
        if length == 0x81:
            length = data[i + 2]
            value_start = i + 3
        elif length == 0x82:
            length = (data[i + 2] << 8) | data[i + 3]
            value_start = i + 4
        else:
            value_start = i + 2

        if tag == target_tag:
            return data[value_start:value_start + length]

        i = value_start + length
    return None


def write_to_card(blk7_hex):
    """Write SE data derived from Blk7 to an iClass tag.

    Uses iclasswrite.make_se_data + writeDataBlocks with ICLASS_LEGACY (17).
    Tries multiple keys to support both virgin Picopass blanks and formatted
    HID iClass cards.

    Returns True on success (ret == 0), False otherwise.
    """
    if iclasswrite is None:
        return False

    # Standard HID iClass keys to try (in order of likelihood)
    ICLASS_KEYS = [
        'AFA785A7DAB33378',  # Standard HID iClass key (formatted cards)
        '2020666666668888',  # Virgin Picopass transport key
    ]

    _log("PM3_WRITE: blk7={}".format(blk7_hex))

    try:
        se_data = iclasswrite.make_se_data(blk7_hex)
    except Exception as e:
        _log("PM3_WRITE: make_se_data error: {}".format(e))
        return False

    _log("PM3_WRITE: se_data={}".format(se_data))

    for key in ICLASS_KEYS:
        try:
            _log("PM3_CMD: iclasswrite.writeDataBlocks(blk=17, key={})".format(key[:8]))
            ret = iclasswrite.writeDataBlocks(17, se_data, key)
            _log("PM3_REPLY: writeDataBlocks ret={}".format(ret))
            if ret == 0:
                _log("WRITE_PM3 iclass SUCCESS with key={}".format(key[:8]))
                return True
        except Exception as e:
            _log("PM3_REPLY: writeDataBlocks key={} error={}".format(key[:8], e))
            continue

    _log("PM3_WRITE: iclass failed all keys")
    return False


def detect_target_card():
    """Detect if a writable iClass card is present on the coil.

    Uses multi-key support to handle both virgin Picopass blanks (transport
    key) and formatted HID iClass cards (standard HID key).

    Returns True if a card is detected, False otherwise.
    """
    try:
        import executor
    except ImportError:
        try:
            from . import executor
        except ImportError:
            return False

    try:
        # Standard HID iClass keys to try (in order of likelihood)
        ICLASS_KEYS = [
            'AFA785A7DAB33378',  # Standard HID iClass key (formatted cards)
            '2020666666668888',  # Virgin Picopass transport key
        ]

        # Try authenticated read with each key on Block 6/7 (application area)
        for key in ICLASS_KEYS:
            cmd = 'hf iclass rdbl --blk 06 -k {}'.format(key)
            ret = _pm3_exec(cmd, timeout_ms=3000, retries=2)
            if ret is None:
                continue
            pm3_ret, output = ret
            if pm3_ret != -1 and output and 'block' in output.lower():
                # Verify we got actual data, not just an error
                for line in output.splitlines():
                    if 'block' in line.lower() and ':' in line:
                        hex_part = line.split(':', 1)[1].strip()
                        # Must have hex bytes like '00 00 80 1E C2 00 0A 7A'
                        if len(hex_part.replace(' ', '')) >= 16:
                            _log("PM3_REPLY: detect_target_card SUCCESS - valid block on blk 06 with key={}".format(key[:8]))
                            return True

        # Fallback: try Block 0 with each key
        for key in ICLASS_KEYS:
            cmd = 'hf iclass rdbl --blk 00 -k {}'.format(key)
            ret = _pm3_exec(cmd, timeout_ms=3000, retries=2)
            if ret is None:
                continue
            pm3_ret, output = ret
            if pm3_ret != -1 and output and 'block' in output.lower():
                for line in output.splitlines():
                    if 'block' in line.lower() and ':' in line:
                        hex_part = line.split(':', 1)[1].strip()
                        if len(hex_part.replace(' ', '')) >= 16:
                            _log("PM3_REPLY: detect_target_card SUCCESS - valid block on blk 00 with key={}".format(key[:8]))
                            return True

        _log("PM3_REPLY: detect_target_card FAILED - no valid block read with any key")
        return False
    except Exception as e:
        _log("PM3_REPLY: detect_target_card ERROR - {}".format(e))
        return False


def detect_t5577():
    """Detect if a T5577 blank is present on the LF coil.

    Uses lf t55xx detect to check for T5577 card presence.
    Returns True if T5577 detected, False otherwise.
    """
    try:
        import executor
    except ImportError:
        try:
            from . import executor
        except ImportError:
            return False

    try:
        cmd = 'lf t55xx detect'
        ret = _pm3_exec(cmd, timeout_ms=5000, retries=1)
        if ret is None:
            _log("PM3_REPLY: detect_t5577 FAILED - all retries exhausted")
            return False
        pm3_ret, output = ret
        if pm3_ret == -1:
            _log("PM3_REPLY: detect_t5577 FAILED - ret=-1")
            return False
        if not output:
            _log("PM3_REPLY: detect_t5577 FAILED - no output")
            return False
        out_lower = output.lower()
        is_t5577 = (
            ("t55x7" in out_lower or "t5577" in out_lower or "t55xx" in out_lower) and
            ("found" in out_lower or "chip type" in out_lower or "detected" in out_lower or "raw:" in out_lower)
        )
        _log("PM3_REPLY: detect_t5577 result={}".format(is_t5577))
        return is_t5577
    except Exception as e:
        _log("PM3_REPLY: detect_t5577 ERROR - {}".format(e))
        return False


def detect_target():
    """Detect what type of blank card is on the coil/antenna (HF only).

    Only detects iClass/Picopass blanks via `detect_target_card()`.
    LF T5577 detection is NOT performed here - it is handled on-demand
    in the write flow to avoid blocking LF commands that can hang PM3
    for 30+ seconds.

    Returns:
        'hf_iclass' if iClass/Picopass blank detected (HF 13.56 MHz)
        None if no HF card detected
    """
    if detect_target_card():
        _log("DETECT_TARGET: result=hf_iclass")
        return 'hf_iclass'
    _log("DETECT_TARGET: result=None (no HF card on coil)")
    return None


def write_to_t5577(fc, card_id):
    """Write HID Prox credential to T5577 blank.

    Uses lf hid clone -w H10301 to let Proxmark3 handle H10301 framing
    natively with correct parity bit calculation.

    STRICT: Only writes verified 26-bit H10301 frames. Returns False for
    non-26-bit formats (fc=0, cn=0) - extended/48-bit SEOS payloads are
    structured for 13.56 MHz HF memory and will produce unreadable 125 kHz
    LF cards if written to T5577.

    Args:
        fc: Facility Code (int, 0-255)
        card_id: Card ID/Number (int, 0-65535)

    Returns:
        True on success, False on failure or non-26-bit format
    """
    try:
        import executor
    except ImportError:
        try:
            from . import executor
        except ImportError:
            return False

    try:
        if int(fc) == 0 and int(card_id) == 0:
            _log('WRITE_PM3 t5577 FAILED - fc=0 and cn=0 (non-26bit data, unsafe for LF)')
            return False
        cmd = 'lf hid clone -w H10301 --fc {} --cn {}'.format(int(fc), int(card_id))
        ret = _pm3_exec(cmd, timeout_ms=5000, retries=1)
        if ret is None:
            _log('WRITE_PM3 t5577 FAILED - all retries exhausted')
            return False
        pm3_ret, output = ret
        write_success = pm3_ret in (0, 1)
        if write_success:
            # Double-check output for error messages
            if output and "error" in output.lower():
                _log('WRITE_PM3 t5577 FAILED - error in output')
                write_success = False
        _log('WRITE_PM3 t5577 result={}'.format(write_success))
        return write_success
    except Exception as e:
        _log('WRITE_PM3 t5577 ERROR - {}'.format(e))
        return False


def is_valid_26bit(fc, cn):
    """Check if extracted FC/CN represent a valid 26-bit Wiegand frame.

    Args:
        fc: Facility Code
        cn: Card Number

    Returns:
        True if valid 26-bit format (fc > 0 or cn > 0)
    """
    try:
        fc, cn = int(fc), int(cn)
        return 0 <= fc <= 255 and 0 <= cn <= 65535 and (fc != 0 or cn != 0)
    except (TypeError, ValueError):
        return False


def calculate_wiegand26_parity(fc: int, cn: int) -> int:
    """
    Reconstructs the 26-bit Wiegand integer from FC (8-bit) and CN (16-bit)
    with standard even (P1) and odd (P2) parities.
    """
    data24 = ((fc & 0xFF) << 16) | (cn & 0xFFFF)

    # Even Parity (P1) covers upper 12 bits of data (bits 23..12)
    upper_12 = (data24 >> 12) & 0xFFF
    p1 = 0
    temp = upper_12
    while temp:
        p1 ^= (temp & 1)
        temp >>= 1

    # Odd Parity (P2) covers lower 12 bits of data (bits 11..0)
    lower_12 = data24 & 0xFFF
    p2 = 1
    temp = lower_12
    while temp:
        p2 ^= (temp & 1)
        temp >>= 1

    wiegand26 = (p1 << 25) | (data24 << 1) | p2
    return wiegand26


def verify_target_card(target_type, source_data):
    """
    Performs hardware readback and reverse verification against original source_data.
    Returns: (success: bool, message: str)
    """
    if not source_data:
        return (False, "No source data")

    expected_fc = int(source_data.get('fc', 0))
    expected_cn = int(source_data.get('id', 0))
    expected_blk7 = source_data.get('raw_block7', source_data.get('blk7', '')).replace(" ", "").lower()
    is_26bit = source_data.get('is_26bit', False) or (expected_fc > 0 and expected_cn > 0)

    _log('VERIFY type={} exp_fc={} exp_cn={} exp_blk7={} 26bit={}'.format(
        target_type, expected_fc, expected_cn, expected_blk7[:16], is_26bit))

    try:
        import executor
    except ImportError:
        try:
            from . import executor
        except ImportError:
            return (False, "No executor")

    # -------------------------------------------------------------
    # 1. HF iClass / Picopass Verification
    # -------------------------------------------------------------
    if target_type == 'hf_iclass':
        read_hex = None
        used_key = None
        for key in ["AFA785A7DAB33378", "2020666666668888"]:
            cmd = 'hf iclass rdbl --blk 7 -k {}'.format(key)
            ret = _pm3_exec(cmd, timeout_ms=3000, retries=1)
            if ret is None:
                continue
            pm3_ret, output = ret
            _log("PM3_REPLY: verify rdbl key={} ret={}".format(key[:8], pm3_ret))
            if pm3_ret != -1 and output:
                for line in output.splitlines():
                    if "block" in line.lower() and ":" in line:
                        raw_bytes = line.split(":", 1)[1].strip()
                        cleaned = raw_bytes.replace(" ", "").replace("\t", "").strip().lower()
                        if len(cleaned) == 16:
                            read_hex = cleaned
                            used_key = key
                            break
            if read_hex:
                break

        if not read_hex:
            return (False, "Auth failed")

        # Normalize both strings for comparison
        clean_read = read_hex.strip().replace(" ", "").lower()
        clean_exp = expected_blk7.strip().replace(" ", "").lower()

        # Direct raw match takes precedence
        if clean_read == clean_exp and len(clean_read) == 16:
            if is_26bit and expected_fc > 0:
                _log("VERIFY_SUCCESS: FC:{} CN:{}".format(expected_fc, expected_cn))
                return (True, "Verified FC:{} CN:{}".format(expected_fc, expected_cn))
            else:
                _log("VERIFY_SUCCESS: Blk7: {}".format(clean_read.upper()))
                return (True, "Blk7: {}".format(clean_read.upper()))

        # Only execute 26-bit bit-shift validation if raw equality fails
        if is_26bit:
            try:
                raw_int = int(clean_read, 16)
                read_fc = (raw_int >> 17) & 0xFF
                read_cn = (raw_int >> 1) & 0xFFFF
                if read_fc == expected_fc and read_cn == expected_cn:
                    _log("VERIFY_SUCCESS: FC:{} CN:{}".format(read_fc, read_cn))
                    return (True, "Verified FC:{} CN:{}".format(read_fc, read_cn))
                else:
                    _log("VERIFY_FAIL: R:FC:{} CN:{} != E:FC:{} CN:{}".format(
                        read_fc, read_cn, expected_fc, expected_cn))
                    return (False, "R:FC:{} CN:{} != E:FC:{} CN:{}".format(
                        read_fc, read_cn, expected_fc, expected_cn))
            except Exception:
                pass

        _log("VERIFY_FAIL: R:{} != E:{}".format(clean_read.upper()[:8], clean_exp.upper()[:8]))
        return (False, "R:{} != E:{}".format(clean_read.upper()[:8], clean_exp.upper()[:8]))

    # -------------------------------------------------------------
    # 2. LF T5577 Verification
    # -------------------------------------------------------------
    elif target_type == 'lf_t5577':
        if not is_26bit:
            _log("VERIFY_FAIL: LF invalid for non-26b")
            return (False, "LF invalid for non-26b")

        cmd = 'lf hid reader'
        ret = _pm3_exec(cmd, timeout_ms=5000, retries=1)
        if ret is None:
            _log("VERIFY_FAIL: LF retries exhausted")
            return (False, "No LF signal")

        pm3_ret, output = ret
        if pm3_ret == -1:
            _log("VERIFY_FAIL: LF no output")
            return (False, "No LF signal")

        read_fc = None
        read_cn = None
        # Specifically target the H10301 line with valid parity
        for line in output.splitlines():
            line_lower = line.lower()
            if "h10301" in line_lower and "fc:" in line_lower and "cn:" in line_lower:
                fc_match = re.search(r'FC:\s*(\d+)', line, re.IGNORECASE)
                cn_match = re.search(r'CN:\s*(\d+)', line, re.IGNORECASE)
                if fc_match and cn_match:
                    read_fc = int(fc_match.group(1))
                    read_cn = int(cn_match.group(1))
                    break  # Found the correct line, stop searching

        if read_fc is None or read_cn is None:
            _log("VERIFY_FAIL: LF parse failed")
            return (False, "Failed to parse LF")

        if read_fc == expected_fc and read_cn == expected_cn:
            _log("VERIFY_SUCCESS: LF FC:{} CN:{}".format(read_fc, read_cn))
            return (True, "FC:{} CN:{}".format(read_fc, read_cn))

        _log("VERIFY_FAIL: LF R:FC:{} CN:{} != E:FC:{} CN:{}".format(
            read_fc, read_cn, expected_fc, expected_cn))
        return (False, "R:FC:{} CN:{} != E:FC:{} CN:{}".format(
            read_fc, read_cn, expected_fc, expected_cn))

    return (False, "Unknown target")
