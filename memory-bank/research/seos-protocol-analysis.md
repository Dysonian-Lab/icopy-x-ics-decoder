# SEOS Protocol Analysis — BlackHat Asia 2025

Source: `seosTalk/Asia-25-Iceman-dismantling-the-seos-protocol.pdf`
Transcript: `seosTalk/iceman-seos-talk.txt` (pdftotext output)
Authors: evildaemond & Iceman (RFID hackers, iceman = Proxmark3 fork maintainer)
Date captured: 2026-08-24

## Overview

SEOS is HID Global's successor to iCLASS SE. Built on ISO 7816 APDUs over ISO 14443-A (JCOP card layer). Features AES security, strong authentication, privacy protection. Little public documentation — this talk is the primary public teardown.

## Protocol Structure

- **Transport:** ISO 7816 APDU over ISO 14443-A (the layer iCopy-X sees as "ISO 14443-A, UID/SAK/ATQA")
- **Crypto:** AES-128 CBC encryption + SHA-256 hashing
- **Secure Messaging (SM):** All sensitive data exchanged via SM commands
- **Mutual Authentication:** `RND.ICC` ↔ `RND.IFD` challenge-response with **diversified keys** (per-card unique keys derived from a master)

## Card Data Model

- **ADF** (Application Data File): contains credential data objects (D0=SecurityRocks, D1=SensitiveData, D2=ExtraSensitive)
- **GDF** (Global Data File): shared/global data
- **Keysets:**
  - Privacy Keyset (ENC KEY + MAC KEY) — decrypts the privacy/credential cryptogram
  - Auth Keyset (Auth Key 1, Auth Key 2) — used during authentication exchange
- **Diversifier:** Static value on the ADF

## Recovered Data (from talk demo)

- ADF OID: `1.3.6.1.4.1.29240.1.1.2.1.24.1.1.2` (ASN.1: `2B0601040181E43801010201`)
- External ID (CF [07]): `11223344556677` — the actual card identifier
- APDU command flow observed:
  - `00 A4 0400` — SELECT FILE (ADF)
  - `80 A5 04` — SM Mutual Auth (challenge RND.ICC)
  - `0B 00 3A 84` — SM SEOS GET ADF command
  - `80 02 A5 04` — SM command with encryption (09=AES-128 CBC, 07=SHA-256)

## Key Findings for Our Project

### The "Hard Path" (what the talk demonstrates)
Full RF-layer teardown: sniff 14a traffic, parse APDUs, recover RND.ICC/IFD, decrypt cryptogram with privacy keyset. **Mechanism is proven. Master keys are NOT public** — real deployments use diversified keys derived from an unknown master. No one has published the master key.

### The "Practical Path" (what our project actually does)
The DIY iCS Decoder does NOT break SEOS crypto. The **RP10E's integrated secure element** performs the full SEOS handshake internally and outputs the decoded credential as **Wiegand** (FC/ID). We capture Wiegand — never touching AES, APDUs, or keys.

### The Downgrade Clone
**Primary use case:** Most access control systems have NOT disabled legacy iCLASS Wiegand fallback on SEOS credentials. The SEOS card still emits a legacy Wiegand credential (the "downgrade"). The RP10E reads this and outputs it; the iCopy-X writes it to a legacy iCLASS/Picopass or T5577 blank. This works WITHOUT recovering any SEOS keys.

**Proper SEOS-to-SEOS clone** (writing to another SEOS card) WOULD require the keysets — not yet achievable without the master key.

## Relevance to iCS Decoder
- Our firmware targets the Wiegand output only — SEOS internals are handled by RP10E silicon
- The talk confirms SEOS uses AES-128 CBC + SHA-256 (informational; we don't implement it)
- External ID / FC / ID extraction is the RP10E's job, not ours
- The downgrade method is why the iCS Decoder exists and why our DIY version is viable

## Reference Materials Cited in Talk
- HID SEOS whitepaper: https://www.hidglobal.com/sites/default/files/resource_files/pacs-seos-card-ds-en_0.pdf
- Patent US10826707B2 (Privacy preserving tag)
- Patent EP2831802B1 (Field revisions for personal security device)
- "An analysis of the HID Indala and Seos protocols" — Luud
- "Unlocking doors from half a continent away: A relay attack against HID Seos" — Haskins, Stevado
