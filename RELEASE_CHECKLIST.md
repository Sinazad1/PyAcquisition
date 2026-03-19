# Release Checklist (Acquisition + Analysis + Programming)

Use this checklist before shipping a new executable set.

## 1) Automated checks
- [ ] `python -m pytest` passes with zero failures.
- [ ] `tests/test_offline_e2e_smoke.py` passes.
- [ ] No new linter errors in touched files.

## 2) Acquisition checks
- [ ] CN0359 preflight runs and status line updates (`PASS`/`PARTIAL`/`FAIL`).
- [ ] Play is gated by preflight in CN0359 mode.
- [ ] Stop halts acquisition without closing the app window.
- [ ] CSV has deterministic DUT1..DUT8 columns.
- [ ] Log file is created and appended during run.

## 3) Emulator safety checks
- [ ] Emulator ports can be selected in CN0359 mode.
- [ ] UI clearly indicates emulator mode is active.
- [ ] Emulator run still generates valid measurements/events files.

## 4) Analysis checks
- [ ] 8-Sensor Checklist gives actionable failures when inputs are wrong.
- [ ] Analysis runs with valid inputs and produces:
  - [ ] `*_analysis.pdf`
  - [ ] `*_coefficients.txt`
  - [ ] `analysis_log_*.txt`
- [ ] Sensor range text reflects configured unit count (not hardcoded 1-6).

## 5) Programming checks
- [ ] DUT connect performs identity probe (`getver`) and handles failure clearly.
- [ ] Coefficient file parser includes accepted sensors and skips rejected sensors.
- [ ] Confirmation dialog shows file name + accepted/rejected overview.
- [ ] Programming worker logs selection/save/verify flow and summary.
- [ ] `programming_log_*.txt` created.

## 6) Build checks
- [ ] Acquisition EXE builds and launches.
- [ ] Troubleshooter EXE builds and launches.
- [ ] Startup menu/version labels match expected release numbers.
