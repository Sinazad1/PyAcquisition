# Hub Comeback Ramp Playbook (ICUSB2328I)

Use this playbook when the 8-port hub returns from service.

## 1) Pre-boot checks
- Verify RS232 level compatibility end-to-end (hub DB9 is true RS232).
- Confirm cable type/pinout (straight-through vs null-modem).
- Label physical mapping: HubPort1->SensorSlot1 ... HubPort8->SensorSlot8.

## 2) Windows readiness
- Disable USB selective suspend.
- For each FTDI COM port:
  - 115200, 8N1, Flow control None.
  - Low latency timer (1-2ms).
  - Disable power-management auto-suspend on USB root hubs.

## 3) Troubleshooter readiness (v5)
1. Run `CN0359Troubleshooter_v5.exe`.
2. Menu `9` (ICUSB2328I readiness check).
3. Confirm expected FTDI count and COM stability.

## 4) Ramp test sequence
1. **1 sensor** connected: verify bare `poll` data on known-good COM.
2. **2 sensors**: run multi-port hub check and confirm both respond.
3. **4 sensors**: repeat and monitor for stability for 2-3 minutes.
4. **8 sensors**: run pre-fixture verify and monitor mode.

If failures appear only as count increases, prioritize:
- power quality
- grounding/noise
- cable integrity
- fixture fan-out wiring

## 5) Acquisition validation
- Run CN0359 preflight in app before Play.
- Confirm PASS or expected PARTIAL diagnostics.
- Run 3-minute acquisition and inspect DUT1..DUT8 CSV continuity.

## 6) Exit criteria
- Stable responses at full 8-sensor load.
- No repeated timeout clusters on specific ports.
- Acquisition + analysis + programming path completes without operator workarounds.
