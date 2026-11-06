// 11/5/2026 desktop device constructed and connected to an RP40
// 11/5/2026 added 56bit to the whitelist
// 11/5/2026 added a BRUTE command
// iCS D4 — Benchtop Diagnostic Sniffer (ATmega32U4)
// Captures raw Wiegand frames into a ring buffer; serial command interface for bench analysis.
// Compiled and flashed independently. Production firmware (icsdecooderori.ino) is NOT modified.
// Target: ATmega32U4 (Arduino Leonardo). Wiegand D0 = pin 2, D1 = pin 3. Serial = 115200 8N1.
#include <Arduino.h>
#include <stdint.h>
#include <string.h>
#include <ctype.h>
#include <stdlib.h>

// --- Hardware pin mapping ---------------------------------------------------
#define WIEGAND_D0 2          // Wiegand D0 (data 0) — falling-edge interrupt on pin 2
#define WIEGAND_D1 3          // Wiegand D1 (data 1) — falling-edge interrupt on pin 3
#define CMD_BUF_SIZE 32       // Max serial command line length (incl. null terminator)
#define RING_SIZE 8           // Depth of the captured-frame ring buffer
#define LED_PIN 13            // Onboard LED: blinks once per latched frame

// --- Frame data structure ---------------------------------------------------
// A single captured Wiegand frame. bits[] holds up to 256 bits, MSB-first:
//   bit N is stored at byte N/8, bit position 7 - (N % 8). Unused high bits
//   in the final byte are zero.
struct WgFrame {
    uint8_t bits[32];          // Raw captured bits (up to 256 bits = 32 bytes)
    uint16_t bitCount;         // Number of valid bits captured in this frame
    uint32_t firstPulseUs;     // micros() timestamp of the first falling edge
    uint32_t lastPulseUs;      // micros() timestamp of the last falling edge
    uint32_t minGapUs;         // Shortest inter-pulse gap (microseconds)
    uint32_t maxGapUs;         // Longest inter-pulse gap (microseconds)
    uint16_t pulseCount;       // Total falling edges seen (equals bitCount unless overflow)
    bool overflow;             // True if >256 bits arrived (frame truncated)
    uint32_t capturedAtMs;     // millis() at the moment the frame was latched
};

// --- Ring buffer ------------------------------------------------------------
// Fixed-depth circular buffer of the most recent frames. ringHead is the next
// write slot; ringCount is the number of valid frames (0..RING_SIZE). When full,
// the oldest slot is overwritten and ringCount stays at RING_SIZE.
WgFrame ring[RING_SIZE];
uint8_t ringHead = 0;          // Next ring slot to write into
uint8_t ringCount = 0;         // Number of valid frames currently in the ring

// --- Live capture state (shared ISR <-> loop, volatile) ---------------------
// These variables are written inside interrupt context and read in loop(), so
// they are volatile and all loop() reads are wrapped in noInterrupts().
volatile uint8_t liveBits[32];      // Bit accumulator for the frame currently being captured
volatile uint16_t liveBitCount = 0; // Number of bits accumulated so far (0..256)
volatile uint16_t livePulseCount = 0; // Total falling edges seen in the live frame
volatile uint32_t liveFirstPulseUs = 0;   // micros() of the first pulse of the live frame
volatile uint32_t liveLastPulseUs = 0;    // micros() of the most recent pulse
volatile uint32_t liveFirstPulseMs = 0;   // millis() of the first pulse
volatile uint32_t liveLastPulseMs = 0;    // millis() of the most recent pulse (gap timeout reference)
volatile uint32_t liveMinGapUs = UINT32_MAX;  // Shortest gap seen in the live frame
volatile uint32_t liveMaxGapUs = 0;   // Longest gap seen in the live frame
volatile bool liveOverflow = false;   // Set if liveBitCount hits 256 (no more bits accepted)
volatile uint16_t gapTimeoutMs = 25;  // Idle gap (ms) after which a frame is considered complete (clamped 5..100)

// --- Mode / card / serial state ---------------------------------------------
bool sniffMode = false;           // false = BRIDGE (capture only), true = SNIFF (auto-print frames)

// Production-compatible card state (set by capture, consumed by the RD command).
bool cardAvailable = false;       // True when a complete card frame is waiting to be reported
uint64_t cardRaw = 0;             // Raw card bit pattern (packed MSB-first into 64 bits)
uint16_t cardBits = 0;            // Number of valid bits in cardRaw

char cmdBuf[CMD_BUF_SIZE];        // Serial command line accumulator
uint8_t cmdLen = 0;               // Current length of cmdBuf

// Index of the most recently printed frame (ring slot, or 255 for ad-hoc calls).
uint8_t wgFrameIndex = 255;

// --- Forward declarations ---------------------------------------------------
void setupWiegand();
void ISR_D0();
void ISR_D1();
void wgAppendBit(bool isOne);
void wgLatchFrame();
bool wgFrameComplete();
void serialHandleCommand(const char* cmd);
void cmdWho();
void cmdRd();
void cmdStatus();
void cmdDump(const char* arg);
void cmdClear();
void cmdMode(const char* arg);
void cmdTimeout(const char* arg);
void cmdBits();
void cmdHelp();
void printFrame(const WgFrame* f);
void printHexBuf(const uint8_t* buf, uint16_t bits);
void printBinBuf(const uint8_t* buf, uint16_t bits);
const char* guessFormat(uint16_t bits);
// Reconstruct a uint64_t from a packed bits[] buffer, MSB-first, matching the
// production ISR accumulation order (first received bit = MSB of the value).
uint64_t wgReconstruct64(const uint8_t* bits, uint16_t bitCount);
// Extract stream bits [start .. start+len-1] from a left-justified value.
uint64_t extract_field(uint64_t value, uint16_t total_bits, int start, int len);
void sendCardBlock(uint64_t raw, uint16_t bits);
void printHex64(uint64_t value, unsigned int minNibbles);
void printBinary64(uint64_t value, unsigned int bits);

// ============================================================================
// SETUP / LOOP
// ============================================================================

void setup() {
    Serial.begin(115200);
    while (!Serial) {}            // Wait for USB serial enumeration (Leonardo native USB)

    memset(cmdBuf, 0, sizeof(cmdBuf));
    cmdLen = 0;
    cardAvailable = false;
    pinMode(LED_PIN, OUTPUT);
    digitalWrite(LED_PIN, LOW);

    setupWiegand();               // Configure Wiegand pins and attach interrupts
}

void loop() {
    // Poll for a completed frame: if a gap longer than gapTimeoutMs has elapsed
    // since the last pulse, latch the live frame into the ring buffer.
    if (wgFrameComplete()) {
        digitalWrite(LED_PIN, HIGH);
        delay(50);
        digitalWrite(LED_PIN, LOW);
    }

    // Drain the serial port line by line. Lines are terminated by '\n'; '\r'
    // is accepted but stripped before dispatch.
    while (Serial.available() > 0) {
        char c = Serial.read();

        if (c == '\n') {
            if (cmdLen > 0 && cmdBuf[cmdLen - 1] == '\r') {
                cmdLen--;         // Strip trailing carriage return
            }
            cmdBuf[cmdLen] = '\0';
            serialHandleCommand(cmdBuf);
            cmdLen = 0;
            memset(cmdBuf, 0, sizeof(cmdBuf));
        } else if (c != '\r' && isPrintable(c)) {
            if (cmdLen < CMD_BUF_SIZE - 1) {
                cmdBuf[cmdLen++] = c;   // Buffer printable chars (truncate if full)
            }
        }
    }
}

// ============================================================================
// WIEGAND CAPTURE
// ============================================================================

// Configure the Wiegand input pins and attach falling-edge interrupts. Also
// zero-initialize all live capture state and default the gap timeout to 25 ms.
// The device starts in BRIDGE mode (sniffMode = false).
void setupWiegand() {
    pinMode(WIEGAND_D0, INPUT_PULLUP);
    pinMode(WIEGAND_D1, INPUT_PULLUP);

    attachInterrupt(digitalPinToInterrupt(WIEGAND_D0), ISR_D0, FALLING);
    attachInterrupt(digitalPinToInterrupt(WIEGAND_D1), ISR_D1, FALLING);

    memset(liveBits, 0, sizeof(liveBits));
    liveBitCount = 0;
    livePulseCount = 0;
    liveFirstPulseUs = 0;
    liveLastPulseUs = 0;
    liveFirstPulseMs = 0;
    liveLastPulseMs = 0;
    liveMinGapUs = UINT32_MAX;
    liveMaxGapUs = 0;
    liveOverflow = false;
    gapTimeoutMs = 25;
    sniffMode = false;
}

// ISR_D0 — fired on every falling edge of the Wiegand D0 line.
// D0 represents a binary 0 bit. Delegates to wgAppendBit(false).
// ISR body is intentionally short: only byte/bit math, micros()/millis(), and
// counter updates. No Serial, no delay, no noInterrupts.
void ISR_D0() {
    wgAppendBit(false);
}

// ISR_D1 — fired on every falling edge of the Wiegand D1 line.
// D1 represents a binary 1 bit. Delegates to wgAppendBit(true).
// ISR body is intentionally short: only byte/bit math, micros()/millis(), and
// counter updates. No Serial, no delay, no noInterrupts.
void ISR_D1() {
    wgAppendBit(true);
}

// wgAppendBit — ISR helper called by both ISR_D0 and ISR_D1.
// Appends a single bit (isOne == true for D1, false for D0) to the live frame
// bit buffer, MSB-first. Updates pulse/timing bookkeeping.
// Bit packing math:
//   byteIdx = liveBitCount / 8      -> which byte in liveBits[] holds bit N
//   bitPos  = 7 - (liveBitCount % 8)-> which bit position within that byte
//   (MSB-first means bit 0 of the stream goes to bit 7 of byte 0, etc.)
// Overflow guard: if liveBitCount >= 256, set liveOverflow and stop accepting
// further bits until the live state is reset by wgLatchFrame().
void wgAppendBit(bool isOne) {
    if (liveOverflow) {
        return;                   // Frame already overflowed; ignore further bits
    }
    if (liveBitCount >= 256) {
        liveOverflow = true;      // Buffer exhausted; mark overflow and stop
        return;
    }

    uint8_t byteIdx = liveBitCount / 8;
    uint8_t bitPos = 7 - (liveBitCount % 8);
    if (isOne) {
        liveBits[byteIdx] |= (1 << bitPos);   // Set bit N to 1 (0 bits stay cleared since bytes are pre-zeroed)
    }

    liveBitCount++;
    livePulseCount++;

    uint32_t nowUs = micros();
    uint32_t nowMs = millis();

    if (liveBitCount == 1) {
        // First pulse of this frame: record its timestamp as the reference.
        liveFirstPulseUs = nowUs;
        liveFirstPulseMs = nowMs;
    } else {
        // Subsequent pulse: compute the gap from the previous pulse and update
        // the running min/max gap statistics.
        uint32_t gapUs = nowUs - liveLastPulseUs;
        if (gapUs < liveMinGapUs) {
            liveMinGapUs = gapUs;
        }
        if (gapUs > liveMaxGapUs) {
            liveMaxGapUs = gapUs;
        }
    }

    liveLastPulseUs = nowUs;      // Advance the "last pulse" watermark
    liveLastPulseMs = nowMs;
}

// wgLatchFrame — Snapshot the live capture state into a WgFrame and push it
// into the ring buffer, then reset the live state for the next capture.
//
// Atomicity: the snapshot of volatile live state is taken under noInterrupts()
// so an ISR cannot tear a multi-byte read. The ring push and optional print
// happen outside the atomic section (ring push is a single struct copy; print
// is slow and must never run inside a critical section).
//
// Ring buffer behavior:
//   ring[ringHead] = frame;            // write into next slot
//   ringHead = (ringHead + 1) % 8;     // advance write cursor
//   if ringCount < 8: ringCount++      // buffer not yet full
//   else: ringCount stays 8 (oldest slot overwritten) and the NEW frame gets
//         overflow = true to signal that a previous frame was displaced.
//
// In SNIFF mode, printFrame() is called immediately after the push so the raw
// frame streams to serial in real time. cardAvailable is SET to true so the
// production RD command can return this captured frame to iCopy-X exactly like
// a real iCS Decoder would. This is the key divergence from the original plan:
//
//   Original plan: cardAvailable = false;  (RD returns ?? after capture)
//   This build:    cardAvailable = true;   (RD returns OK + card block)
//
// Both modes remain fully functional: BRIDGE captures silently, SNIFF auto-prints.
void wgLatchFrame() {
    WgFrame frame;

    // --- Atomic snapshot of volatile live state -----------------------------
    noInterrupts();
    memcpy(frame.bits, liveBits, 32);
    frame.bitCount = liveBitCount;
    frame.pulseCount = livePulseCount;
    frame.firstPulseUs = liveFirstPulseUs;
    frame.lastPulseUs = liveLastPulseUs;
    frame.minGapUs = liveMinGapUs;
    frame.maxGapUs = liveMaxGapUs;
    frame.overflow = liveOverflow;
    frame.capturedAtMs = millis();

    // Reset live state so the next card capture starts clean.
    memset(liveBits, 0, sizeof(liveBits));
    liveBitCount = 0;
    livePulseCount = 0;
    liveFirstPulseUs = 0;
    liveLastPulseUs = 0;
    liveFirstPulseMs = 0;
    liveLastPulseMs = 0;
    liveMinGapUs = UINT32_MAX;
    liveMaxGapUs = 0;
    liveOverflow = false;
    interrupts();

    // --- Ring buffer push ---------------------------------------------------
    uint8_t slot = ringHead;          // Slot we are about to (over)write
    ring[ringHead] = frame;
    ringHead = (ringHead + 1) % RING_SIZE;

    if (ringCount < RING_SIZE) {
        ringCount++;                  // Buffer still filling
    } else {
        // Buffer full: the oldest slot (ring[slot]) is overwritten by the new
        // frame. Mark the newly latched frame's ring entry with overflow=true
        // so consumers know a previous frame was displaced. ringCount stays 8.
        ring[slot].overflow = true;
    }

    // --- Optional streaming in SNIFF mode ----------------------------------
    if (sniffMode) {
        wgFrameIndex = slot;
        printFrame(&ring[slot]);
    }

    // Expose the captured frame to the production RD command so iCopy-X can
    // read it exactly like a real iCS Decoder. This replaces the previous
    // cardAvailable = false; capture now arms RD with the most recent frame.
    cardAvailable = true;
    cardRaw = wgReconstruct64(frame.bits, frame.bitCount);
    cardBits = frame.bitCount;
}

// wgFrameComplete — Called once per loop() iteration, before serial processing.
// Returns true (and latches the frame) if bits are pending and the idle gap
// since the last pulse exceeds gapTimeoutMs. All volatile reads are guarded by
// noInterrupts() to avoid torn reads of multi-byte values.
bool wgFrameComplete() {
    noInterrupts();
    uint16_t bits = liveBitCount;
    uint32_t lastPulse = liveLastPulseMs;
    uint16_t timeout = gapTimeoutMs;
    interrupts();

    if (bits == 0) {
        return false;                 // Nothing being captured right now
    }

    if ((millis() - lastPulse) > (uint32_t)timeout) {
        wgLatchFrame();               // Idle gap expired: frame is complete
        return true;
    }

    return false;                     // Still waiting for more pulses
}

// ============================================================================
// SERIAL COMMAND HANDLING
// ============================================================================

// Parse a null-terminated command line (trailing '\r' already stripped by the
// caller). Split on the first space into an uppercased command token and an
// optional argument, then dispatch to the matching handler. Unknown commands
// print "??".
void serialHandleCommand(const char* cmd) {
    char commandToken[32];
    memset(commandToken, 0, sizeof(commandToken));
    const char* arg = NULL;

    const char* sp = strchr(cmd, ' ');
    if (sp != NULL) {
        size_t tokLen = (size_t)(sp - cmd);
        if (tokLen >= sizeof(commandToken)) {
            tokLen = sizeof(commandToken) - 1;
        }
        memcpy(commandToken, cmd, tokLen);
        commandToken[tokLen] = '\0';
        arg = sp + 1;                 // Everything after the first space
    } else {
        size_t len = strlen(cmd);
        if (len >= sizeof(commandToken)) {
            len = sizeof(commandToken) - 1;
        }
        memcpy(commandToken, cmd, len);
        commandToken[len] = '\0';
    }

    // Uppercase the token so commands are case-insensitive.
    for (size_t i = 0; commandToken[i] != '\0'; i++) {
        commandToken[i] = (char)toupper((unsigned char)commandToken[i]);
    }

    // --- /? alias ----------------------------------------------------------
    // '/' is not a valid command token character, so "/?" arrives as a single
    // token "/?" with no space. Treat it exactly like HELP.
    if (strcmp(commandToken, "/?") == 0) {
        cmdHelp();
        return;
    }

    // --- Dispatch table (case-sensitive after uppercasing) -----------------
    if (strcmp(commandToken, "WHO") == 0) {
        cmdWho();
    } else if (strcmp(commandToken, "RD") == 0) {
        cmdRd();
    } else if (strcmp(commandToken, "STATUS") == 0) {
        cmdStatus();
    } else if (strcmp(commandToken, "DUMP") == 0) {
        cmdDump(arg);                 // arg may be NULL (dump most recent frame)
    } else if (strcmp(commandToken, "CLEAR") == 0) {
        cmdClear();
    } else if (strcmp(commandToken, "MODE") == 0) {
        cmdMode(arg);                 // arg required: BRIDGE or SNIFF
    } else if (strcmp(commandToken, "TIMEOUT") == 0) {
        cmdTimeout(arg);              // arg required: gap timeout in ms (5..100)
    } else if (strcmp(commandToken, "BITS") == 0) {
        cmdBits();
    } else if (strcmp(commandToken, "HELP") == 0) {
        cmdHelp();
    } else if (strcmp(commandToken, "BRUTE") == 0) {
        cmdBrute();
    } else {
        Serial.print(F("??\r\n"));    // Unrecognised command
    }
}

// WHO — handshake. Responds with "ISE". Does not touch card state or the ring.
void cmdWho() {
    Serial.print(F("ISE\r\n"));
}

// RD — production card read. If a valid card frame is available (bit count in
// the whitelist 26/34/35/37/48), respond "OK" then send the formatted card
// block; otherwise respond "??". Always clear cardAvailable after responding.
void cmdRd() {
    if (cardAvailable && (cardBits == 26 || cardBits == 34 || cardBits == 35 || cardBits == 37 || cardBits == 48 || cardBits == 56)) {
        Serial.print(F("OK\r\n"));
        sendCardBlock(cardRaw, cardBits);
    } else {
        Serial.print(F("??\r\n"));
    }
    cardAvailable = false;
}

// STATUS — print the most recent captured frame (ring slot ringHead-1), or
// "NO FRAMES" if the ring is empty.
void cmdStatus() {
    if (ringCount == 0) {
        Serial.print(F("NO FRAMES\r\n"));
        return;
    }
    uint8_t recent = (ringHead - 1 + RING_SIZE) % RING_SIZE;
    wgFrameIndex = recent;
    printFrame(&ring[recent]);
}

// DUMP — print a specific ring slot, or the most recent frame if no argument.
// Index refers to the ring slot (0..7), not a logical sequence number. Prints
// "EMPTY" if the ring is empty or the index is out of range.
void cmdDump(const char* arg) {
    uint8_t index;
    if (arg == NULL || *arg == '\0') {
        if (ringCount == 0) {
            Serial.print(F("EMPTY\r\n"));
            return;
        }
        index = (ringHead - 1 + RING_SIZE) % RING_SIZE;   // Most recent frame
    } else {
        index = (uint8_t)atoi(arg);                       // Parse decimal slot index
        if (ringCount == 0 || index >= ringCount) {
            Serial.print(F("EMPTY\r\n"));
            return;
        }
    }
    wgFrameIndex = index;
    printFrame(&ring[index]);
}

// CLEAR — reset the ring buffer and live capture state under noInterrupts(),
// clear production card state, and respond "CLEARED".
void cmdClear() {
    noInterrupts();
    ringCount = 0;
    ringHead = 0;
    memset(liveBits, 0, sizeof(liveBits));
    liveBitCount = 0;
    livePulseCount = 0;
    liveFirstPulseUs = 0;
    liveLastPulseUs = 0;
    liveFirstPulseMs = 0;
    liveLastPulseMs = 0;
    liveMinGapUs = UINT32_MAX;
    liveMaxGapUs = 0;
    liveOverflow = false;
    interrupts();

    cardAvailable = false;
    Serial.print(F("CLEARED\r\n"));
}

// MODE — switch between BRIDGE (capture only, no auto-print) and SNIFF
// (auto-print every latched frame). Responds "MODE BRIDGE"/"MODE SNIFF" or
// "??" for an invalid argument.
void cmdMode(const char* arg) {
    if (arg == NULL) {
        Serial.print(F("??\r\n"));
        return;
    }
    if (strcmp(arg, "BRIDGE") == 0) {
        sniffMode = false;
        Serial.print(F("MODE BRIDGE\r\n"));
    } else if (strcmp(arg, "SNIFF") == 0) {
        sniffMode = true;
        Serial.print(F("MODE SNIFF\r\n"));
    } else {
        Serial.print(F("??\r\n"));
    }
}

// TIMEOUT — set the frame gap timeout. Parse arg as an unsigned integer, clamp
// to 5..100 ms, store it, and echo "TIMEOUT#:<ms>".
void cmdTimeout(const char* arg) {
    if (arg == NULL) {
        Serial.print(F("??\r\n"));
        return;
    }
    unsigned long ms = strtoul(arg, NULL, 10);
    if (ms < 5) {
        ms = 5;
    }
    if (ms > 100) {
        ms = 100;
    }
    gapTimeoutMs = (uint16_t)ms;
    Serial.print(F("TIMEOUT#:"));
    Serial.println(gapTimeoutMs);
}

// BITS — read liveBitCount under noInterrupts() and report "BITS#:<count>".
// Lets a bench operator check how many bits have accumulated so far.
void cmdBits() {
    noInterrupts();
    uint16_t bits = liveBitCount;
    interrupts();
    Serial.print(F("BITS#:"));
    Serial.println(bits);
}

// HELP — list every supported command with brief aligned descriptions.
void cmdHelp() {
    Serial.print(F("WHO               - iCopy-X handshake\r\n"));
    Serial.print(F("RD                - Read production card block\r\n"));
    Serial.print(F("STATUS            - Print most recent raw frame\r\n"));
    Serial.print(F("DUMP [n]          - Print ring slot (0-7)\r\n"));
    Serial.print(F("CLEAR             - Reset ring buffer & live state\r\n"));
    Serial.print(F("MODE BRIDGE|SNIFF - Toggle silent capture vs auto-print\r\n"));
    Serial.print(F("TIMEOUT <ms>      - Set frame gap timeout (5-100ms)\r\n"));
    Serial.print(F("BITS              - Show live bit accumulation count\r\n"));
    Serial.print(F("BRUTE             - Brute force FC/CN field positions\r\n"));
    Serial.print(F("HELP / /?         - Show this menu\r\n"));
}

// ============================================================================
// FRAME OUTPUT
// ============================================================================

// printFrame — Emit a single WgFrame in the exact diagnostic text format
// (every line ends with \r\n):
//
//   $FRAME_START$
//   Index#: <slot or 255 for ad-hoc>
//   Bit#: <bitCount>
//   Pulses#: <pulseCount>
//   FirstUs#: <firstPulseUs>
//   LastUs#: <lastPulseUs>
//   MinGapUs#: <minGapUs>
//   MaxGapUs#: <maxGapUs>
//   Overflow#: <0|1>
//   Bin#: <binary, MSB-first>
//   Hex#: <hex, lowercase, zero-padded>
//   Guess#: <format guess: 26/34/35/37/48/56/64/OTHER>
//   $FRAME_STOP$
//
// Index# reports wgFrameIndex (set by STATUS/DUMP/SNIFF; 255 for ad-hoc calls).
void printFrame(const WgFrame* f) {
    Serial.print(F("$FRAME_START$\r\n"));
    Serial.print(F("Index#: "));
    Serial.println(wgFrameIndex);
    Serial.print(F("Bit#: "));
    Serial.println(f->bitCount);
    Serial.print(F("Pulses#: "));
    Serial.println(f->pulseCount);
    Serial.print(F("FirstUs#: "));
    Serial.println(f->firstPulseUs);
    Serial.print(F("LastUs#: "));
    Serial.println(f->lastPulseUs);
    Serial.print(F("MinGapUs#: "));
    Serial.println(f->minGapUs);
    Serial.print(F("MaxGapUs#: "));
    Serial.println(f->maxGapUs);
    Serial.print(F("Overflow#: "));
    Serial.println(f->overflow ? 1 : 0);
    Serial.print(F("Bin#: "));
    printBinBuf(f->bits, f->bitCount);
    Serial.print(F("Hex#: "));
    printHexBuf(f->bits, f->bitCount);
    Serial.print(F("Guess#: "));
    Serial.println(guessFormat(f->bitCount));
    Serial.print(F("$FRAME_STOP$\r\n"));
}

// printHexBuf — Print raw frame bytes as lowercase hex, MSB-first across bytes,
// high nibble then low nibble within each byte. Zero-padded to the full nibble
// count ((bits + 7) / 8) * 2. No "0x" prefix. Terminates with a newline.
void printHexBuf(const uint8_t* buf, uint16_t bits) {
    uint16_t nibbles = ((bits + 7) / 8) * 2;
    for (uint16_t i = 0; i < nibbles; i++) {
        uint16_t byteIdx = i / 2;                       // Which byte this nibble comes from
        uint8_t nibble = (i % 2 == 0)                   // Even index = high nibble, odd = low nibble
            ? ((buf[byteIdx] >> 4) & 0x0F)
            : (buf[byteIdx] & 0x0F);
        Serial.print((char)("0123456789abcdef"[nibble]));
    }
    Serial.println();
}

// printBinBuf — Print raw frame bits as 0/1 characters, MSB-first: bit
// (bits-1) down to bit 0 of the stream. Uses a forward loop over stream bit
// positions (0 to bits-1), mapping each to byteIdx = i/8 and bitPos = 7-(i%8)
// to reproduce the MSB-first packing used in wgAppendBit. No spaces, no
// prefix. Terminates with a newline. Safely handles bits == 0 (no output).
void printBinBuf(const uint8_t* buf, uint16_t bits) {
    for (uint16_t i = 0; i < bits; i++) {
        uint16_t byteIdx = i / 8;              // Which byte holds stream bit i
        uint8_t bitPos = 7 - (i % 8);          // MSB-first within that byte
        Serial.print((unsigned int)((buf[byteIdx] >> bitPos) & 1));
    }
    Serial.println();
}

// guessFormat — Map a bit count to a human-readable Wiegand format guess.
// Known formats: 26, 34, 35, 37, 48, 56, 64. Anything else -> "OTHER".
// Returns a pointer to a static string literal.
const char* guessFormat(uint16_t bits) {
    switch (bits) {
        case 26: return "26";
        case 34: return "34";
        case 35: return "35";
        case 37: return "37";
        case 48: return "48";
        case 56: return "56";
        case 64: return "64";
        default: return "OTHER";
    }
}

// ============================================================================
// PRODUCTION COMPATIBILITY (RD command output)
// ============================================================================

// wgReconstruct64 — Rebuild a uint64_t from the packed bits[] buffer so it
// matches the production ISR accumulation order exactly.
//
// Production ISR math:
//   wiegandBits = (wiegandBits << 1) | bit;   // first bit received = MSB
//
// So bit 0 of the stream ends up at position (bitCount - 1) of the value, and
// the last bit received ends up at position 0. This function reads the
// bits[] buffer MSB-first and shifts left each iteration to reproduce that
// layout. Values with fewer than 64 bits are left-justified (unused high bits
// are zero).
//
// *** 64-BIT TRUNCATION WARNING ***
// Wiegand frames can carry up to 256 bits (liveBits holds 32 bytes). This
// function only reconstructs the low 64 bits into a uint64_t. Any frame with
// bitCount > 64 will be TRUNCATED when exposed via the RD command — cardRaw
// will contain only the first 64 bits and cardBits will report the full count
// (which will fail the RD whitelist check of 26/34/35/37/48, causing RD to
// return "??").
//
// Operators who need to inspect oversized frames (>64 bits) must use the
// diagnostic commands instead of RD:
//   STATUS        — print the most recent frame's full raw bits[] array
//   DUMP [n]      — print a specific ring slot's full raw bits[] array
//   SNIFF mode    — auto-streams every latched frame's full raw data
// These commands output Bin# and Hex# from the complete bits[] buffer, not
// the truncated 64-bit cardRaw value.
uint64_t wgReconstruct64(const uint8_t* bits, uint16_t bitCount) {
    uint64_t value = 0;
    for (uint16_t i = 0; i < bitCount; i++) {
        uint8_t byteIdx = i / 8;                       // Which byte holds bit i
        uint8_t bitPos = 7 - (i % 8);                  // MSB-first within byte
        bool bitVal = (bits[byteIdx] >> bitPos) & 1;   // Extract bit i
        value = (value << 1) | (bitVal ? 1ULL : 0ULL); // Shift left, append bit
    }
    return value;
}

// extract_field — Pull a contiguous bit field from a left-justified Wiegand
// value. Stream bit 0 is the MSB of the value. Use this to test FC/CN layouts
// on non-standard formats (e.g. 56-bit SE 2k).
//
//   value   = reconstructed 64-bit value from wgReconstruct64()
//   total_bits = actual bit count of the frame (e.g. 56)
//   start   = first stream bit to extract (0 = first bit received)
//   len     = number of bits to extract
//
// Example 26-bit H10301: extract_field(raw, 26, 1, 8)  -> FC
//                  extract_field(raw, 26, 9, 16) -> CN
uint64_t extract_field(uint64_t value, uint16_t total_bits, int start, int len) {
    int shift = total_bits - start - len;
    uint64_t mask = (1ULL << len) - 1;
    return (value >> shift) & mask;
}

// cmdBrute — Brute-force FC/CN field positions on the most recent captured
// frame. Tries FC8/FC16/FC20/FC22 and CN16/CN20/CN24/CN32/CN34/CN36 fields,
// printing decoded decimal values. Look for known values (e.g. card number
// 2493837 from card markings) in the output to identify the correct layout.
// Useful for reverse-engineering proprietary high-bit-count formats where
// FC/CN values exceed 8-bit or 24-bit ranges.
void cmdBrute() {
    if (ringCount == 0) {
        Serial.print(F("NO FRAMES\r\n"));
        return;
    }

    uint8_t recent = (ringHead - 1 + RING_SIZE) % RING_SIZE;
    uint64_t raw = wgReconstruct64(ring[recent].bits, ring[recent].bitCount);
    uint16_t bits = ring[recent].bitCount;

    Serial.print(F("BRUTE - Frame "));
    Serial.print(recent);
    Serial.print(F(" bits="));
    Serial.println(bits);
    Serial.print(F("RawHex="));
    printHex64(raw, ((bits + 7) / 8) * 2);

    // --- Bit map: print each stream bit with position ----------------------
    Serial.print(F("BitMap:"));
    for (uint16_t i = 0; i < bits; i++) {
        if (i % 8 == 0) {
            Serial.print(F(" "));
        }
        uint64_t b = extract_field(raw, bits, i, 1);
        Serial.print((unsigned int)b);
    }
    Serial.println();

    // --- FC candidates: 8-bit fields at every start position ---------------
    Serial.println(F("FC8 (start=value):"));
    for (int s = 0; s + 8 <= (int)bits; s++) {
        uint64_t v = extract_field(raw, bits, s, 8);
        Serial.print(F("  "));
        Serial.print(s);
        Serial.print(F("="));
        printUint64Dec(v);
    }

    // --- FC candidates: 16-bit fields --------------------------------------
    Serial.println(F("FC16 (start=value):"));
    for (int s = 0; s + 16 <= (int)bits; s++) {
        uint64_t v = extract_field(raw, bits, s, 16);
        Serial.print(F("  "));
        Serial.print(s);
        Serial.print(F("="));
        printUint64Dec(v);
    }

    // --- FC candidates: 20-bit fields --------------------------------------
    Serial.println(F("FC20 (start=value):"));
    for (int s = 0; s + 20 <= (int)bits; s++) {
        uint64_t v = extract_field(raw, bits, s, 20);
        Serial.print(F("  "));
        Serial.print(s);
        Serial.print(F("="));
        printUint64Dec(v);
    }

    // --- FC candidates: 22-bit fields --------------------------------------
    Serial.println(F("FC22 (start=value):"));
    for (int s = 0; s + 22 <= (int)bits; s++) {
        uint64_t v = extract_field(raw, bits, s, 22);
        Serial.print(F("  "));
        Serial.print(s);
        Serial.print(F("="));
        printUint64Dec(v);
    }

    // --- CN candidates: 16-bit fields at every start position --------------
    Serial.println(F("CN16 (start=value):"));
    for (int s = 0; s + 16 <= (int)bits; s++) {
        uint64_t v = extract_field(raw, bits, s, 16);
        Serial.print(F("  "));
        Serial.print(s);
        Serial.print(F("="));
        printUint64Dec(v);
    }

    // --- CN candidates: 20-bit fields --------------------------------------
    Serial.println(F("CN20 (start=value):"));
    for (int s = 0; s + 20 <= (int)bits; s++) {
        uint64_t v = extract_field(raw, bits, s, 20);
        Serial.print(F("  "));
        Serial.print(s);
        Serial.print(F("="));
        printUint64Dec(v);
    }

    // --- CN candidates: 24-bit fields --------------------------------------
    Serial.println(F("CN24 (start=value):"));
    for (int s = 0; s + 24 <= (int)bits; s++) {
        uint64_t v = extract_field(raw, bits, s, 24);
        Serial.print(F("  "));
        Serial.print(s);
        Serial.print(F("="));
        printUint64Dec(v);
    }

    // --- CN candidates: 32-bit fields --------------------------------------
    Serial.println(F("CN32 (start=value):"));
    for (int s = 0; s + 32 <= (int)bits; s++) {
        uint64_t v = extract_field(raw, bits, s, 32);
        Serial.print(F("  "));
        Serial.print(s);
        Serial.print(F("="));
        printUint64Dec(v);
    }

    // --- CN candidates: 34-bit fields --------------------------------------
    Serial.println(F("CN34 (start=value):"));
    for (int s = 0; s + 34 <= (int)bits; s++) {
        uint64_t v = extract_field(raw, bits, s, 34);
        Serial.print(F("  "));
        Serial.print(s);
        Serial.print(F("="));
        printUint64Dec(v);
    }

    // --- CN candidates: 36-bit fields --------------------------------------
    Serial.println(F("CN36 (start=value):"));
    for (int s = 0; s + 36 <= (int)bits; s++) {
        uint64_t v = extract_field(raw, bits, s, 36);
        Serial.print(F("  "));
        Serial.print(s);
        Serial.print(F("="));
        printUint64Dec(v);
    }

    Serial.print(F("BRUTE done\r\n"));
}

// printUint64Dec — Print a 64-bit unsigned integer in base-10 decimal on AVR,
// where Serial.println() does not natively support uint64_t decimal output.
// Terminates with a newline.
void printUint64Dec(uint64_t value) {
    if (value == 0) {
        Serial.print('0');
        Serial.println();
        return;
    }
    char buf[21];
    uint8_t len = 0;
    uint64_t v = value;
    while (v > 0) {
        buf[20 - len] = '0' + (v % 10);
        v /= 10;
        len++;
    }
    for (uint8_t i = 21 - len; i < 21; i++) {
        Serial.print(buf[i]);
    }
    Serial.println();
}

// sendCardBlock — Emit the production-formatted card block for an RD response.
//
// Bit-extraction math per format (all MSB-first, bit 0 = first pulse sent):
//   26-bit:  FC = bits[8..25]  -> (raw >> 17) & 0xFF
//            ID = bits[1..24]  -> (raw >> 1)  & 0xFFFF
//   34-bit:  FC = bits[8..25]  -> (raw >> 17) & 0xFFFF
//            ID = bits[1..32]  -> (raw >> 1)  & 0xFFFF
//   35-bit:  FC = bits[8..28]  -> (raw >> 21) & 0x1FFF
//            ID = bits[1..20]  -> (raw >> 1)  & 0xFFFFF
//   37-bit:  FC = bits[8..28]  -> (raw >> 19) & 0x1FFFF
//            ID = bits[1..18]  -> (raw >> 1)  & 0x3FFFF
//   48-bit:  no FC/ID breakdown (both zero)
void sendCardBlock(uint64_t raw, uint16_t bits) {
    Serial.println(F("$A_CARD_START$"));

    Serial.print(F("wiedata#:"));
    printBinary64(raw, bits);                       // Raw bits as binary string
    Serial.print(F("Bit#:"));
    Serial.println(bits);

    uint32_t facilityCode = 0;
    uint64_t cardId = 0;

    if (bits == 26) {
        facilityCode = (uint32_t)((raw >> 17) & 0xFF);     // Skip parity bit 0, take 8 FC bits
        cardId = (uint32_t)((raw >> 1)  & 0xFFFF);         // Skip parity bit 0, take 16 ID bits
    } else if (bits == 34) {
        facilityCode = (uint32_t)((raw >> 17) & 0xFFFF);   // Skip parity bit 0, take 16 FC bits
        cardId = (uint32_t)((raw >> 1)  & 0xFFFF);         // Skip parity bit 0, take 16 ID bits
    } else if (bits == 35) {
        facilityCode = (uint32_t)((raw >> 21) & 0x1FFF);   // Skip parity bit 0, take 13 FC bits
        cardId = (uint32_t)((raw >> 1)  & 0xFFFFF);        // Skip parity bit 0, take 20 ID bits
    } else if (bits == 37) {
        facilityCode = (uint32_t)((raw >> 19) & 0x1FFFF);  // Skip parity bit 0, take 17 FC bits
        cardId = (uint32_t)((raw >> 1)  & 0x3FFFF);        // Skip parity bit 0, take 18 ID bits
    } else if (bits == 48) {
        // HID Corporate 1000 (48-bit) — SE/SEOS via SAM:
        //   Bit 0   = odd parity
        //   Bit 1   = even parity
        //   Bits 2-23 = Facility Code / Company ID (22 bits)
        //   Bits 24-46 = Card Number (23 bits)
        //   Bit 47   = odd parity
        facilityCode = (uint32_t)extract_field(raw, 48, 2, 22);   // FC (22 bits)
        cardId = extract_field(raw, 48, 24, 23);                  // CN (23 bits)
    } else if (bits == 56) {
        // Avigilon 56-bit legacy payload (SE 2k via SAM):
        //   Bit 0   = even parity
        //   Bits 1-20 = Facility Code (20 bits)
        //   Bits 21-54 = Card Number (34 bits)
        //   Bit 55   = odd parity
        facilityCode = (uint32_t)extract_field(raw, 56, 1, 20);   // FC (20 bits, fits in uint32_t)
        cardId = extract_field(raw, 56, 21, 34);                  // CN (34 bits, needs uint64_t)
    }

    Serial.print(F("FC#:"));
    Serial.println(facilityCode);
    Serial.print(F("ID#:"));
    printUint64Dec(cardId);

    uint16_t hexNibbles = ((bits + 7) / 8) * 2;            // Full-nibble count for hex output
    Serial.print(F("Hex#:"));
    printHex64(raw, hexNibbles);

    Serial.print(F("Blk7#:"));
    printHex64(raw, 16);                                   // Always 16 hex chars (Blk7 invariant)

    Serial.print(F("Bits#:"));
    printBinary64(raw, bits);

    Serial.println(F("$A_CARD_STOP$"));
}

// printHex64 — Print a 64-bit value as lowercase hex, zero-padded to at least
// minNibbles nibbles, no "0x" prefix, terminated with a newline. Handles the
// zero value specially (prints at least one digit).
void printHex64(uint64_t value, unsigned int minNibbles) {
    char buf[17];
    unsigned int len = 0;
    uint64_t v = value;

    if (v == 0) {
        len = 1;
    } else {
        while (v > 0 && len < 16) {
            buf[15 - len] = "0123456789abcdef"[v % 16];   // Fill buf from the end (LSB first)
            v /= 16;
            len++;
        }
    }

    unsigned int pad = minNibbles > len ? minNibbles - len : 0;
    for (unsigned int i = 0; i < pad; i++) {
        Serial.print('0');                                 // Leading zero padding
    }

    for (unsigned int i = 16 - len; i < 16; i++) {         // Print the significant digits
        Serial.print(buf[i]);
    }
    Serial.println();
}

// printBinary64 — Print a 64-bit value as binary, MSB-first, printing exactly
// `bits` characters (bit `bits-1` down to bit 0). Terminates with a newline.
void printBinary64(uint64_t value, unsigned int bits) {
    for (int i = (int)bits - 1; i >= 0; i--) {
        Serial.print((unsigned int)((value >> i) & 1ULL)); // Extract bit i
    }
    Serial.println();
}
