# Developer Q&A Responses

Date: 2026-08-15
Source: iCopy-X-Community/icopyx-diy-ics-decoder developer

## Context
Developer confirmed he was targeting the original/factory firmware in 2021. The open-source firmware never implemented iCS Decoder support ("non-critical = not important = not implemented"). He never had a genuine iCS Decoder for testing — his implementation is a best-guess mimic based on observed traffic.

## Answers

1. **Baud rate:** "I've no idea of the official ics decoder baudrate."
2. **Second RD behavior:** "no idea and i don't have an official icsd to test"
3. **Payload padding:** "I'm just mimicking the official icsd, i don't know how the official fw is parsing it"
4. **Field widths:** "cf 3" (same as above — just mimicking)
5. **RP10E other formats:** "i don't know. i have just a handful of samples, there is zero iclass in EU"
6. **Parity validation:** "cf 3" (mimicking official, doesn't know if required)
7. **Bit-length negotiation:** "it worked with my fw samples, that's all i know"
8. **USB VID/PID:** Not asked/answered
9. **Serial timeout/line-ending:** Not asked/answered
10. **Init sequence:** Not asked/answered

## Implications
- Competitor's protocol implementation is unverified against genuine hardware
- We must do our own reverse engineering and testing
- Best approach: iterative testing against iCopy-X, adjusting based on observed behavior
- Protocol capture from genuine iCS Decoder would be ideal but may not be available
