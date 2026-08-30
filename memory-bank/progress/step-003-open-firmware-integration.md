# Step 003: Direction Change — Open Firmware Integration

Date: 2026-08-14

## Completed
- Confirmed open firmware has dormant `IClassSEActivity` stub (unregistered, unimplemented)
- Verified open firmware has zero iCS Decoder device detection or serial code
- Confirmed competitor's video uses factory firmware with symlink workaround
- Changed project direction: target open firmware integration, not factory firmware
- Updated PROJECT-PLAN.md with open firmware integration strategy
- Added memory-bank entries for fork and GUI references

## Key Decision
Building for the open-source iCopy-X firmware (Dysonian-Lab/icopy-x fork), not the factory firmware. This requires:
1. Implementing `src/middleware/ics_decoder.py`
2. Registering `IClassSEActivity` in activity registry
3. Extending activity with device detection and serial communication
4. Supporting both genuine iCS Decoder (`/dev/ttyUSB0`) and DIY Pro Micro (`/dev/ttyACM*`)

## Reference Repos
- iCopy-X fork: https://github.com/Dysonian-Lab/icopy-x
- Phosphor GUI 2.0: https://github.com/Dysonian-Lab/Phosphor-2.0-GUI
- Competitor: https://github.com/iCopy-X-Community/icopyx-diy-ics-decoder

## Pending
- Awaiting developer answers to protocol questions
- Hardware procurement (Pro Micro + RP10)
- Implementation of open firmware integration
