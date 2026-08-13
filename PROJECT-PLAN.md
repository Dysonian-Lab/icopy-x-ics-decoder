# ICS Decoder Project Plan

## Current Status
- Project folder created at D:\kilocode\icsdecoder
- Memory-bank structure established
- Hardware selected: Teyleten Robot Type-C Pro Micro ATmega32U4 5V 16MHz
- Protocol identified but unverified

## Phase 1: Hardware Acquisition & Test Setup (Week 1)
- [ ] Purchase Teyleten Robot Type-C Pro Micro 3pcs (B0B6HYLC44)
- [ ] Purchase HD RP10 125kHz RFID reader
- [ ] Gather USB-C cables, Dupont wires, breadboard
- [ ] Wire RP10 to Pro Micro:
  - RP10 Red → VCC
  - RP10 Black → GND
  - RP10 Green → Pin 2 (D0, INT0)
  - RP10 White → Pin 3 (D1, INT1)

## Phase 2: Wiegand Sniffer (Week 1-2)
- [ ] Write Arduino sketch to capture Wiegand bits via interrupts
- [ ] Test with 26-bit Wiegand card
- [ ] Verify bit timing (25ms timeout)
- [ ] Validate FC/ID extraction from raw bits
- [ ] Document Wiegand format supported by RP10

## Phase 3: Protocol Implementation (Week 2-3)
- [ ] Implement "Who" → "ISE" handshake
- [ ] Implement "RD" command handler
- [ ] Implement card payload formatting ($A_CARD_START$ block)
- [ ] Handle "no card" case with "??\r\n"
- [ ] Test with Serial Monitor / terminal emulator

## Phase 4: iCopy-X Integration (Week 3-4)
- [ ] Connect Pro Micro to iCopy-X via USB-C
- [ ] Verify enumeration as CDC serial device
- [ ] Test handshake with iCopy-X
- [ ] Test card read flow end-to-end
- [ ] Troubleshoot timing, line endings, buffer issues

## Phase 5: Protocol Capture & Validation (Ongoing)
- [ ] Acquire genuine iCS Decoder
- [ ] Capture USB traffic with iCopy-X (usbmon / logic analyzer)
- [ ] Compare captured protocol with reverse-engineered spec
- [ ] Update firmware to match exact protocol
- [ ] Test edge cases: multiple cards, error conditions, timeout behavior

## Risk Register
| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Protocol spec is wrong | High | High | Capture real traffic before finalizing firmware |
| Clone board quality issues | Medium | Medium | Buy from reputable seller, test USB enumeration early |
| RP10 Wiegand format differs | Low | Medium | Sniffer phase will reveal actual format |
| iCopy-X USB host compatibility | Low | High | Test enumeration first; may need different USB descriptor |
| 5V logic conflicts | Low | Low | ATmega32U4 is 5V native — already resolved |

## Milestones
1. Hardware received and wired — Week 1
2. Wiegand sniffer working — Week 2
3. Protocol layer implemented — Week 3
4. First successful iCopy-X handshake — Week 4
5. Protocol validated against real iCS Decoder — Week 5-6
