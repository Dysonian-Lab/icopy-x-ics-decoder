#include <Arduino.h>
#include <stdint.h>
#include <string.h>
#include <ctype.h>

#define WIEGAND_D0 2
#define WIEGAND_D1 3

#define BIT_TIMEOUT_MS 25

volatile uint64_t wiegandBits = 0;
volatile uint16_t bitCount = 0;
volatile uint32_t lastPulseMicros = 0;
volatile bool frameReady = false;

void ISR_D0();
void ISR_D1();
void processFrame();
void printHex64(uint64_t value, unsigned int minNibbles);
void printBinary64(uint64_t value, unsigned int bits);

void setup() {
    Serial.begin(115200);
    while (!Serial) {}

    pinMode(WIEGAND_D0, INPUT_PULLUP);
    pinMode(WIEGAND_D1, INPUT_PULLUP);

    attachInterrupt(digitalPinToInterrupt(WIEGAND_D0), ISR_D0, FALLING);
    attachInterrupt(digitalPinToInterrupt(WIEGAND_D1), ISR_D1, FALLING);

    Serial.println(F("Wiegand Sniffer v2"));
    Serial.println(F("Present a 125kHz card to the HD RP10 reader..."));
    Serial.println(F("---"));
}

void loop() {
    if (frameReady) {
        noInterrupts();
        uint64_t captured = wiegandBits;
        uint16_t count = bitCount;
        wiegandBits = 0;
        bitCount = 0;
        frameReady = false;
        interrupts();

        processFrame(captured, count);
    }
}

void ISR_D0() {
    wiegandBits = (wiegandBits << 1);
    bitCount++;
    lastPulseMicros = micros();
}

void ISR_D1() {
    wiegandBits = (wiegandBits << 1) | 1ULL;
    bitCount++;
    lastPulseMicros = micros();
}

void processFrame(uint64_t raw, uint16_t bits) {
    Serial.print(F("Bits: "));
    Serial.println(bits);

    Serial.print(F("Raw:  "));
    printBinary64(raw, bits);

    uint32_t facilityCode = 0;
    uint32_t cardId = 0;
    bool supported = true;

    if (bits == 26) {
        facilityCode = (raw >> 17) & 0xFF;
        cardId = (raw >> 1) & 0xFFFF;
    } else if (bits == 34) {
        facilityCode = (raw >> 17) & 0xFFFF;
        cardId = (raw >> 1) & 0xFFFF;
    } else if (bits == 35) {
        facilityCode = (raw >> 21) & 0x1FFF;
        cardId = (raw >> 1) & 0xFFFFF;
    } else if (bits == 37) {
        facilityCode = (raw >> 19) & 0x1FFFF;
        cardId = (raw >> 1) & 0x3FFFF;
    } else {
        supported = false;
    }

    if (supported) {
        Serial.print(F("FC#:   "));
        Serial.println(facilityCode);
        Serial.print(F("ID#:   "));
        Serial.println(cardId);
        Serial.print(F("Hex#:  "));
        printHex64(raw, 10);
        Serial.print(F("Blk7#: "));
        printHex64(raw, 16);
        Serial.print(F("Bits#: "));
        printBinary64(raw, 48);
    } else {
        Serial.println(F("Unsupported Wiegand format"));
    }

    Serial.println(F("---"));
}

void printHex64(uint64_t value, unsigned int minNibbles) {
    char buf[17];
    unsigned int len = 0;
    uint64_t v = value;

    if (v == 0) {
        len = 1;
    } else {
        while (v > 0 && len < 16) {
            buf[15 - len] = "0123456789abcdef"[v % 16];
            v /= 16;
            len++;
        }
    }

    unsigned int pad = minNibbles > len ? minNibbles - len : 0;
    for (unsigned int i = 0; i < pad; i++) {
        Serial.print('0');
    }

    for (unsigned int i = 16 - len; i < 16; i++) {
        Serial.print(buf[i]);
    }
    Serial.println();
}

void printBinary64(uint64_t value, unsigned int bits) {
    for (int i = bits - 1; i >= 0; i--) {
        Serial.print((unsigned int)((value >> i) & 1ULL));
    }
    Serial.println();
}
