# Offline Functional Test Walkthrough (Hub Down)

This walkthrough validates Acquisition, Analysis, and Programming without requiring the physical 8-port hub.

## A) Generate baseline data with emulator
1. Launch latest acquisition EXE.
2. In serial selector, set Sensor1..Sensor8 to `EMULATOR1..EMULATOR8`.
3. Run `CN0359 Preflight`.
4. Start acquisition for 2-3 minutes, then stop.
5. Confirm files exist:
   - `measurements_*.csv`
   - `events_*.csv`
   - `serial_log_*.txt`

## B) Validate analysis path
1. Open Analysis mode.
2. Select latest `measurements_*.csv`.
3. Confirm matching `events_*.csv` is detected.
4. Click `8-Sensor Checklist`.
5. Run Analysis.
6. Confirm artifacts:
   - `*_analysis.pdf`
   - `*_coefficients.txt`
   - `analysis_log_*.txt`

## C) Validate programming path
1. Open Programming mode.
2. Connect DUT COM port.
3. Confirm DUT identity probe result appears in log.
4. Load latest `*_coefficients.txt`.
5. Program one accepted sensor, then all accepted sensors.
6. Confirm `programming_log_*.txt` is generated.

## D) Failure-path checks
- Rename `events_*.csv` and verify Analysis checklist fails with guidance.
- Connect wrong COM in Programming and verify identity warning is shown.
- Attempt play in CN0359 mode before preflight and verify gate prompt appears.

## E) Expected PASS outcomes
- No app crashes/freezes.
- Deterministic data/log output files created.
- Actionable errors for invalid prerequisites.
- End-to-end run can be completed on emulator path.
