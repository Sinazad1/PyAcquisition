# System End-to-End Verification and Validation Protocol

Purpose: define a repeatable end-to-end V&V workflow for the full software stack:
1) CN0359 Troubleshooter precheck, 2) Acquisition run, 3) Analysis validation, 4) Programming verification.

Scope: software and operator workflow validation for 8-sensor calibration process.

## 1. Preconditions

- Use known software build versions (record exact EXE names).
- Confirm fixture hardware is powered and connected.
- Confirm expected COM ports are visible.
- Confirm save directory has write permission.
- Confirm protocol file and config file are selected and versioned.

## 2. Stage A - Troubleshooter Precheck (8-Sensor Go/No-Go)

Objective: verify all 8 sensors are responsive and calibration-ready before acquisition.

### Steps

1. Launch CN0359 Troubleshooter.
2. Run 8-sensor pre-fixture verify/factory screening mode.
3. Use expected 8 COM ports (slot-mapped list).
4. Run at production baud, no baud/address sweeping.
5. Save generated screening report.

### Pass Criteria

- Exactly 8/8 sensors detected.
- All sensors return parseable poll data.
- No sensor flagged as non-responsive.
- `READY FOR FIXTURE: YES`.

### Fail Criteria

- Any missing sensor, parse failure, or unreadable sensor response.
- `READY FOR FIXTURE: NO`.

### Evidence to Archive

- Troubleshooter report file (`cn0359_screening_*.txt`).
- Screenshot/export of final summary.
- COM mapping table used for this run.

## 3. Stage B - Acquisition Protocol Execution

Objective: run full protocol and verify stable data/log generation.

### Steps

1. Open Acquisition mode.
2. Confirm sensor assignment (8 sensors).
3. Run preflight check; confirm status summary.
4. Start protocol and complete full run.
5. Stop run safely and keep session/log context.

### Pass Criteria

- Acquisition completes without crash/hang.
- Expected files created and non-empty:
  - `measurements_*.csv`
  - `events_*.csv`
  - `serial_log_*.txt`
- CSV includes required DUT columns for DUT1..DUT8.
- Timestamps are valid and monotonic.

### Fail Criteria

- Missing files, empty files, malformed columns, or repeated parser/log errors.

### Evidence to Archive

- Raw generated files (CSV + logs).
- Protocol file used.
- Acquisition screenshot showing completion state.

## 4. Stage C - Analysis Validation

Objective: verify correct file selection, parsing, model fit, and output artifacts.

### Steps

1. Open Analysis mode.
2. Select the intended `measurements_*.csv`.
3. Confirm matched event file is correct.
4. Run checklist and ensure all required inputs pass.
5. Run analysis for all 8 sensors.
6. Review accept/reject status and output quality.

### Pass Criteria

- Checklist passes without missing required inputs.
- Correct files are selected (not stale/wrong run files).
- Analysis completes and generates:
  - coefficients output
  - analysis log
  - analysis PDF/plots
- Sensor accept/reject outcomes are persisted correctly.

### Fail Criteria

- Wrong file pairing, checklist bypass with invalid inputs, missing outputs, or analysis crash.

### Evidence to Archive

- Analysis output files and logs.
- Screenshot of checklist result and completion message.
- Accepted/rejected sensor summary table.

## 5. Stage D - Programming Verification

Objective: verify coefficients are programmed only to valid targets and write operation is traceable.

### Steps

1. Open Programming mode.
2. Connect DUT port and run identity probe.
3. Load latest coefficients file from Stage C.
4. Program accepted sensors.
5. Verify write confirmations and final status per sensor.

### Pass Criteria

- DUT connection/identity check succeeds (or explicit override is logged).
- Only ACCEPTED sensors are programmed.
- Programming completes without silent failures.
- `programming_log_*.txt` contains unit-by-unit outcome.

### Fail Criteria

- Programming wrong sensor set, missing write verification, or unlogged failures.

### Evidence to Archive

- Programming log and coefficients file used.
- Operator confirmation record (if override used).
- Final per-sensor result table.

## 6. End-to-End Verdict (Calibration Readiness)

Use this final gate:

- Stage A PASS + Stage B PASS + Stage C PASS + Stage D PASS = `SYSTEM READY`.
- Any stage FAIL = `SYSTEM NOT READY` and corrective action required.

## 7. Required Traceability Bundle (Per Validation Run)

Archive one folder per run containing:

- Troubleshooter report(s)
- Acquisition files (`measurements`, `events`, `serial_log`)
- Analysis outputs (coefficients, plots/PDF, analysis log)
- Programming log
- Version manifest (EXE names, build date, config/protocol checksum)
- Completed signoff form

## 8. Signoff Template

Run ID:
Date:
Operator:
Fixture ID:
Sensor Lot ID:
Software Versions:

Stage A Troubleshooter: PASS / FAIL
Stage B Acquisition: PASS / FAIL
Stage C Analysis: PASS / FAIL
Stage D Programming: PASS / FAIL

Final System Verdict: READY / NOT READY

Blocking Issues:
Corrective Actions:
Approver Name/Date:
