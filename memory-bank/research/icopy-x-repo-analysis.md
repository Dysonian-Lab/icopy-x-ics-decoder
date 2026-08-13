# iCopy-X Firmware Analysis Findings

Date: 2026-08-12

Source: https://github.com/lab-401/icopy-x

## Critical Finding: iCS Decoder Is NOT Implemented in Open Firmware

The open-source iCopy-X firmware explicitly excludes iCS Decoder support:
> "Same functions as the original one (besides support for the external ICS decoder)"

The iCS Decoder is a closed-source USB-C accessory for the iCopy-X. Its protocol is proprietary and not documented in the open firmware.

## iCS Decoder Actual Purpose

Per Lab401 product documentation:
- Target: iCLASS SE / iCLASS SEOS (13.56 MHz HF cards)
- NOT a 125 kHz Wiegand device
- Plugs into iCopy-X via USB-C
- iCopy-X detects it within 5 seconds
- Displays CSN, Facility Code, Card Number

## HD RP10 Capabilities

The HID multiCLASS SE RP10 supports BOTH:
- 13.56 MHz: iCLASS SE, iCLASS SEOS, MIFARE, DESFire
- 125 kHz: HID Prox, Indala, AWID, EM4102

The Wiegand D0/D1 interface is for 125 kHz cards ONLY.
iCLASS SE/SEOS requires the reader's 13.56 MHz interface, not Wiegand.

## Protocol Conflict

Our current project uses:
- Wiegand D0/D1 (125 kHz interface)
- Protocol format with FC#/ID# (Wiegand concepts)
- 26/34/35/37 bit Wiegand formats

This is a 125 kHz Wiegand bridge, NOT an iCLASS SE/SEOS decoder.
The "$A_CARD_START$" payload format with Wiegand data does not match
the real iCS Decoder's iCLASS SE/SEOS protocol.

## Implications

1. If the goal is to clone iCLASS SE/SEOS cards, the hardware approach
   must use 13.56 MHz, not Wiegand D0/D1.
2. If the goal is a 125 kHz Wiegand bridge, the project is valid but
   should not be called an "iCS Decoder" clone.
3. The real iCS Decoder protocol remains reverse-engineering work.
