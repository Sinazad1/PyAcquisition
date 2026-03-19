# Strict Line Diff Map (v1 -> Current)

This document lists explicit **old line -> new line** changes to replay manually.

## 1) `modes/dialogs/serial_selector.py`

### Imports

- Old:
  - `from PySide6.QtWidgets import (..., QCheckBox, QLineEdit, ...)`
- New:
  - `from PySide6.QtWidgets import (..., QLineEdit, ...)`

### CN0359 address UI removal

- Old:
  - `self.cn0359_addr_inputs = {}`
- New:
  - *(line removed)*

- Old:
  - `self.use_addressing_checkbox = QCheckBox("Use sensor addresses (advanced)")`
- New:
  - *(line removed)*

- Old:
  - `addr_label = QLabel("Addr:")`
- New:
  - *(line removed)*

- Old:
  - `addr_input = QLineEdit()`
- New:
  - *(line removed)*

- Old:
  - `addr_input.setPlaceholderText("optional")`
- New:
  - *(line removed)*

- Old:
  - `row_layout.addWidget(addr_label)`
  - `row_layout.addWidget(addr_input)`
- New:
  - *(lines removed)*

### Force bare poll mode in selector output

- Old:
  - `address = self.cn0359_addr_inputs[unit_id].text().strip() if use_addresses else ""`
- New:
  - `address = ""`

- Old:
  - `self.cn0359_selected_sensors.append((unit_id, port, address))`
- New:
  - `self.cn0359_selected_sensors.append((unit_id, port, ""))`

### Layout update (vertical -> compact 2-column)

- Old:
  - `sensor_list_layout = QVBoxLayout()`
- New:
  - `sensor_grid = QGridLayout()`

- Old:
  - `sensor_list_layout.addLayout(row_layout)`
- New:
  - `sensor_grid.addLayout(row_layout, row, col)`


## 2) `modes/utils/settings.py`

### Default config template: remove address keys

- Old:
  - `sensor_1_address =`
  - `sensor_2_address =`
  - `sensor_3_address =`
  - `sensor_4_address =`
  - `sensor_5_address =`
  - `sensor_6_address =`
  - `sensor_7_address =`
- New:
  - *(all lines removed)*

### CN0359 sensor tuple load behavior

- Old:
  - `addr_key = f'sensor_{i}_address'`
  - `address = parser.get('CN0359', addr_key, fallback='').strip()`
  - `sensors.append((i, port, address))`
- New:
  - `sensors.append((i, port, ""))`

- Old:
  - `# list of (unit_id, port, address) tuples`
- New:
  - `# list of (unit_id, port, address) tuples; address forced empty for V2`


## 3) `modes/hardware/cn0359_handler.py`

### Capacity update docs

- Old:
  - `...talk to 1-6 CN0359 boards...`
- New:
  - `...talk to 1-7 CN0359 boards...`

### Constructor tuple parsing

- Old:
  - `for unit_id, port_name, address in self.sensor_configs:`
  - `sensor = SensorConn(unit_id, port_name, address)`
- New:
  - `for cfg in self.sensor_configs:`
  - `if len(cfg) == 2:`
  - `    unit_id, port_name = cfg`
  - `elif len(cfg) == 3:`
  - `    unit_id, port_name, _legacy_address = cfg`
  - `sensor = SensorConn(unit_id, port_name, "")`

### Poll command behavior (addressed -> bare poll)

- Old:
  - `if sensor.address:`
  - `    cmd = f"{sensor.address} poll\n".encode("ascii")`
  - `else:`
  - `    cmd = b"poll\n"`
  - `sensor.ser.write(cmd)`
- New:
  - `sensor.ser.write(b"poll\n")`

### Validation text

- Old:
  - `"sensor_configs must contain at least one (unit_id, port, address) tuple"`
- New:
  - `"sensor_configs must contain at least one sensor tuple"`


## 4) `modes/controllers/data_manager.py`

### 6 -> 7 DUT support (all loops/bounds)

- Old:
  - `for unit_id in range(1, 7):`
- New:
  - `for unit_id in range(1, 8):`

- Old:
  - `if not (1 <= unit_id <= 6):`
- New:
  - `if not (1 <= unit_id <= 7):`

- Old:
  - comments mentioning `up to 6 units`
- New:
  - comments mentioning `up to 7 units`


## 5) `modes/utils/graph_widgets.py`

### Graph capacity and color

- Old:
  - `self.max_dut_units = 6`
- New:
  - `self.max_dut_units = 7`

- Old:
  - loops based on `range(1, 7)`
- New:
  - loops based on `range(1, self.max_dut_units + 1)`

- Old:
  - 6 colors in `self.unit_colors`
- New:
  - 7 colors in `self.unit_colors` (added `#FF8C00`)


## 6) `tests/test_cn0359_handler.py`

### Command expectation updates

- Old:
  - `sensor.ser.write.assert_called_once_with(b"30 poll\n")`
- New:
  - `sensor.ser.write.assert_called_once_with(b"poll\n")`

- Old:
  - `sensor.ser.write.assert_called_once_with(b"42 poll\n")`
- New:
  - `sensor.ser.write.assert_called_once_with(b"poll\n")`

- Old:
  - `def test_poll_with_address_sends_prefix(...):`
- New:
  - `def test_poll_with_address_still_sends_bare_poll(...):`


## 7) `tests/live_demo.py`

### Fake serial parser behavior

- Old:
  - `self._address = "30"`
- New:
  - *(line removed)*

- Old:
  - `expected = f"{self._address} poll"`
  - `if cmd == expected:`
- New:
  - `if cmd == "poll":`

- Old:
  - `(1, "FAKE_COM_A", "30")`
- New:
  - `(1, "FAKE_COM_A", "")`


## 8) `tests/cn0359_simulator.py`

### Simulator command model

- Old:
  - `parser.add_argument("--address", ...)`
- New:
  - *(line removed)*

- Old:
  - `def run_simulator(port, baudrate, address, ...):`
- New:
  - `def run_simulator(port, baudrate, ...):`

- Old:
  - `expected = f"{address} poll"`
- New:
  - `expected = "poll"`


## 9) `config.ini` (root)

### CN0359 keys cleanup

- Old:
  - `sensor_1_address =` ... `sensor_7_address =`
- New:
  - *(all removed)*

- Old:
  - no `sensor_7_port` in older versions
- New:
  - `sensor_7_port =`


## 10) `dist/alyPyAcquisition_v10/config.ini`

- Old:
  - `[CN0359]`
  - `enabled = false`
- New:
  - `[CN0359]`
  - `enabled = true`


## 11) `Sensor_board_firmware scripts/cn0359_troubleshooter_exe/cn0359_troubleshooter.py`

### Versioning

- Old:
  - no version constant
- New:
  - `TOOL_VERSION = "v3"`

- Old:
  - title banner `CN0359 Troubleshooter`
- New:
  - title banner `CN0359 Troubleshooter v3`

### COM behavior improvements

- Old:
  - simple `default_port()` choosing static/fallback
- New:
  - `default_port()` prioritizes likely USB-serial descriptions

- Old:
  - no `get_port_details()`
- New:
  - added `get_port_details()` helper

### New menu + action

- Old:
  - menu items `1..5`
- New:
  - menu items `1..6` with `6) Quick COM sanity check`

- Old:
  - no quick sanity function
- New:
  - `quick_sanity_check()` added


## 12) `Sensor_board_firmware scripts/cn0359_troubleshooter_exe/build_troubleshooter.bat`

- Old:
  - `--name "CN0359Troubleshooter"`
- New:
  - `--name "CN0359Troubleshooter_v3"`

- Old:
  - `dist\CN0359Troubleshooter.exe`
- New:
  - `dist\CN0359Troubleshooter_v3.exe`


## 13) `Sensor_board_firmware scripts/cn0359_troubleshooter_exe/README.md`

- Old:
  - output EXE named `CN0359Troubleshooter.exe`
- New:
  - output EXE named `CN0359Troubleshooter_v3.exe`

- Old:
  - options 1-5 documented
- New:
  - option 6 documented: `Quick COM sanity check`


## 14) Added files

- New file:
  - `dist/alyPyAcquisition_v11/config.ini`
- New file:
  - `dist/alyPyAcquisition_v12/config.ini`


## Modified-Line Estimate

- Total modified files: 12
- Total added files: 2
- Estimated modified/replaced lines: ~300
- Estimated added lines (new files included): ~60

