# Changelog Manual Patch Map (v1 -> Current)

## Change Count Summary

- Files edited: 12 existing files
- Files added: 2 files
- Estimated lines touched: ~300 (adds + deletes + replacements)

---

## File-by-File Old -> New Map

### `modes/dialogs/serial_selector.py`

- `from PySide6.QtWidgets import (..., QCheckBox, QLineEdit, ...)`
  -> `from PySide6.QtWidgets import (..., QLineEdit, ...)`
- `self.cn0359_addr_inputs = {}`
  -> removed
- `self.use_addressing_checkbox = QCheckBox("Use sensor addresses (advanced)")`
  -> removed
- `addr_label = QLabel("Addr:")`
  -> removed
- `addr_input = QLineEdit()` / `addr_input.setPlaceholderText("optional")`
  -> removed
- `address = self.cn0359_addr_inputs[unit_id].text().strip() if use_addresses else ""`
  -> `address = ""`
- Old CN0359 list was one vertical stack of rows
  -> New CN0359 section uses compact `QGridLayout` (2-column horizontal style)
- Comments referencing `port/address`
  -> updated to address-removed flow `(unit_id, port, "")`

### `modes/utils/settings.py`

- In default config template:
  - `sensor_1_address =` ... `sensor_7_address =`
  -> removed
- `# list of (unit_id, port, address) tuples`
  -> `# list of (unit_id, port, address) tuples; address is always ""`
- `addr_key = f'sensor_{i}_address'` and address parsing
  -> removed
- `sensors.append((i, port, address))`
  -> `sensors.append((i, port, ""))`

### `modes/hardware/cn0359_handler.py`

- Header doc:
  - `talk to 1-6 CN0359...`
  -> `talk to 1-7 CN0359...`
- Polling behavior docs:
  - `"{address} poll\n"`
  -> `"poll\n"`
- Validation message:
  - `"sensor_configs must contain at least one (unit_id, port, address) tuple"`
  -> `"sensor_configs must contain at least one sensor tuple"`
- Config unpack:
  - `for unit_id, port_name, address in self.sensor_configs:`
  -> now supports `(id, port)` and `(id, port, legacy_address)` then forces address empty
- Command send:
  - `if sensor.address: ... else b"poll\n"`
  -> always `sensor.ser.write(b"poll\n")`

### `tests/test_cn0359_handler.py`

- `sensor.ser.write.assert_called_once_with(b"30 poll\n")`
  -> `sensor.ser.write.assert_called_once_with(b"poll\n")`
- `sensor.ser.write.assert_called_once_with(b"42 poll\n")`
  -> `sensor.ser.write.assert_called_once_with(b"poll\n")`
- Test name:
  - `test_poll_with_address_sends_prefix`
  -> `test_poll_with_address_still_sends_bare_poll`

### `tests/live_demo.py`

- Comment:
  - `responds to "{address} poll\n"`
  -> `responds to "poll\n"`
- `self._address = "30"`
  -> removed
- `expected = f"{self._address} poll"` / `if cmd == expected:`
  -> `if cmd == "poll":`
- Sensor tuples:
  - `(1, "FAKE_COM_A", "30")`
  -> `(1, "FAKE_COM_A", "")`

### `tests/cn0359_simulator.py`

- Header comment:
  - `responds to "{address} poll\n"`
  -> `responds to "poll\n"`
- Usage:
  - `--address 30`
  -> removed from usage docs
- Function signature:
  - `run_simulator(port, baudrate, address, ...)`
  -> `run_simulator(port, baudrate, ...)`
- `expected = f"{address} poll"`
  -> `expected = "poll"`
- CLI parser:
  - `parser.add_argument("--address", ...)`
  -> removed

### `config.ini` (project root)

- `[CN0359]` address keys:
  - `sensor_1_address` ... `sensor_7_address`
  -> removed
- Kept:
  - `sensor_1_port` ... `sensor_7_port`

### `modes/controllers/data_manager.py`

- Multiple loops:
  - `range(1, 7)` -> `range(1, 8)`
- Bounds:
  - `if 1 <= unit_id <= 6` -> `if 1 <= unit_id <= 7`
- Comments:
  - `up to 6 units` -> `up to 7 units`
- CSV header/data generation updated to include DUT7 columns.

### `dist/alyPyAcquisition_v10/config.ini`

- `[CN0359] enabled = false`
  -> `[CN0359] enabled = true`

### `Sensor_board_firmware scripts/cn0359_troubleshooter_exe/cn0359_troubleshooter.py`

- Added:
  - `TOOL_VERSION = "v3"`
- Title:
  - `CN0359 Troubleshooter`
  -> `CN0359 Troubleshooter v3`
- Added helper:
  - `get_port_details()`
- Improved `default_port()`:
  - now prefers likely USB-serial device descriptions
- Added menu option:
  - `6) Quick COM sanity check`
- Added:
  - `quick_sanity_check()` per-COM probe and diagnosis

### `Sensor_board_firmware scripts/cn0359_troubleshooter_exe/build_troubleshooter.bat`

- Build name:
  - `CN0359Troubleshooter`
  -> `CN0359Troubleshooter_v3`
- Output echo:
  - `dist\CN0359Troubleshooter.exe`
  -> `dist\CN0359Troubleshooter_v3.exe`

### `Sensor_board_firmware scripts/cn0359_troubleshooter_exe/README.md`

- Output name:
  - `CN0359Troubleshooter.exe`
  -> `CN0359Troubleshooter_v3.exe`
- Usage menu:
  - added item `6. Quick COM sanity check`

---

## Added Files

1. `dist/alyPyAcquisition_v11/config.ini`
2. `dist/alyPyAcquisition_v12/config.ini`

---

## Rebuild/Verify Commands

```powershell
python -m pytest tests/test_cn0359_handler.py tests/test_integration.py -q
python -m pytest tests/ -q
python -m PyInstaller -y --onedir --windowed --name "alyPyAcquisition_v12" --add-data "config.ini;." main.py
```

```powershell
cd "Sensor_board_firmware scripts\cn0359_troubleshooter_exe"
python -m PyInstaller -y --onefile --console --name "CN0359Troubleshooter_v3" "cn0359_troubleshooter.py"
```

---

## Final Acceptance Checks

- CN0359 selector shows 7 sensors.
- Address field is removed from CN0359 selector.
- One sensor on valid COM updates live.
- Log shows `poll | RX: Received data from: U1`.
- Troubleshooter v3 option `6` identifies usable COM behavior.
