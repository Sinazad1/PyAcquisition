# Operational Mode Recipes

These JSON files are default mode templates for commissioning and routine operation:

- `prime_mode.json`
- `flush_mode.json`
- `circulation_mode.json`
- `stabilize_mode.json`
- `calibration_mode.json`
- `rinse_mode.json`
- `safe_idle_mode.json`

Run from CLI:

- `python ionin_ops_cli.py list-modes`
- `python ionin_ops_cli.py run-mode flush --dry-run --skip-waits`
- `python ionin_ops_cli.py run-chain --dry-run --skip-waits`

Important:

- These are starting templates.
- Validate rates, temperatures, and durations against your fixture limits before real runs.

Policy and gating:

- `operation_policy.json` controls thresholds, interlocks, and mode entry/exit checks.
- Every run writes a traceable manifest under `data/runs/<run_id>/manifest.json`.
