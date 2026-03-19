"""
Serial Port Selector
Allows selection of COM ports for DUT, IBP reference sensors, syringe pump, chiller, and tic (via serial) in one dialog

Doc status: done, MK, 01/30/2026
"""
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
                              QPushButton, QComboBox, QGroupBox, QMessageBox,
                              QLineEdit, QInputDialog)
from PySide6.QtCore import Qt
import serial.tools.list_ports

# Load CN0359 mode flag and pre-configured sensor list from config.
# If CN0359 is enabled, the dialog shows up to 8 sensor rows instead of
# the single DUT dropdown. _CN0359_SENSORS holds saved sensor entries from
# config.ini so the dialog can pre-populate COM port selections.
try:
    from modes.utils import config as _cfg
    _CN0359_ENABLED = getattr(_cfg, 'CN0359_ENABLED', False)
    _CN0359_SENSORS = getattr(_cfg, 'CN0359_SENSORS', [])
except ImportError:
    _CN0359_ENABLED = False
    _CN0359_SENSORS = []

class UnifiedSerialSelector(QDialog):
    """Unified dialog for selecting DUT, IBP reference sensor, syringe pump, chiller ports, and Tic serial"""
    MAX_CN0359_SENSORS = 8
    CN0359_SENSOR_GRID_COLUMNS = 4
    
    def __init__(self, parent=None, default_dut=None, default_ref1=None, 
                 default_ref2=None, default_pump=None, default_chiller=None, 
                 default_tic_a_serial=None, default_tic_b_serial=None, enable_ibp=True):
        """
        Initialize the unified serial device selector dialog.
        
        Creates a comprehensive dialog for selecting and configuring all serial
        devices including DUT, IBP references, syringe pump, chiller, and TIC controllers.
        When CN0359 mode is enabled, replaces the single DUT port with up to 8 sensor port selectors.
        
        Args:
            parent (QWidget, optional): Parent widget. Defaults to None.
            default_dut (str, optional): Default DUT COM port. Defaults to None.
            default_ref1 (str, optional): Default IBP reference 1 port. Defaults to None.
            default_ref2 (str, optional): Default IBP reference 2 port. Defaults to None.
            default_pump (str, optional): Default syringe pump port. Defaults to None.
            default_chiller (str, optional): Default chiller port. Defaults to None.
            default_tic_a_serial (str, optional): Default TIC A serial number. Defaults to None.
            default_tic_b_serial (str, optional): Default TIC B serial number. Defaults to None.
            enable_ibp (bool, optional): Enable IBP reference configuration. Defaults to True.
        """
        super().__init__(parent)
        self.default_dut = default_dut
        self.default_ref1 = default_ref1
        self.default_ref2 = default_ref2
        self.default_pump = default_pump
        self.default_chiller = default_chiller
        self.default_tic_a_serial = default_tic_a_serial
        self.default_tic_b_serial = default_tic_b_serial
        self.enable_ibp = True  # IBP is always enabled
        # When True, dialog shows up to 8 CN0359 sensor rows.
        # When False, dialog shows the original single DUT dropdown.
        self.cn0359_mode = _CN0359_ENABLED
        
        self.selected_dut_port = None
        self.selected_ref1_port = None
        self.selected_ref2_port = None
        self.selected_pump_port = None
        self.selected_chiller_port = None
        self.selected_tic_a_serial = None
        self.selected_tic_b_serial = None
        self.use_ibp_references = True  # IBP is always enabled
        # Filled by accept_selection() when user clicks Connect in CN0359 mode.
        # List of (unit_id, port, "") tuples for sensors the user selected.
        self.selected_cn0359_sensors = []
        
        # CN0359 UI widget references (populated in init_ui if cn0359_mode).
        # cn0359_combos:      {unit_id: QComboBox} -- COM port dropdown per sensor
        # Address input is intentionally removed for V2 firmware flow
        # (always use bare "poll" from UI path).
        self.cn0359_combos = {}
        
        # Pre-populate sensor defaults from config.ini so the dialog
        # remembers the last-used ports.
        self._cn0359_defaults = {}
        for entry in _CN0359_SENSORS:
            if not entry:
                continue
            unit_id = entry[0]
            port = entry[1] if len(entry) > 1 else ""
            self._cn0359_defaults[unit_id] = (port, "")
        
        self.init_ui()
    
    def _create_combo(self):
        """Create combo box"""
        from PySide6.QtWidgets import QComboBox, QSizePolicy
        combo = QComboBox()
        combo.setStyleSheet("""
            QComboBox {
                padding: 5px;
                font-size: 11pt;
                min-height: 25px;
                background-color: white;
                color: black;
                border: 1px solid #ccc;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: white;
                color: black;
                selection-background-color: #4A90E2;
                selection-color: white;
                border: 2px solid #4A90E2;
                padding: 5px;
            }
        """)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        combo.setMaxVisibleItems(15)
        return combo
        
    def init_ui(self):
        """Initialize the dialog UI"""
        self.setWindowTitle("Select Serial Ports")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setMinimumHeight(800)
        if self.cn0359_mode:
            # Wider layout keeps 4-column CN0359 sensor grid readable.
            self.setMinimumWidth(1200)
        # Allow dialog to resize
        self.setSizeGripEnabled(True)

        

        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Title
        title = QLabel("Serial Port Configuration")
        title.setStyleSheet("font-size: 16pt; font-weight: bold; padding: 10px;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Info label
        info = QLabel("Select COM ports for all devices and Tic serial number.")
        info.setStyleSheet("color: #888; padding: 5px; font-size: 10pt;")
        info.setAlignment(Qt.AlignCenter)
        layout.addWidget(info)
        
        if self.cn0359_mode:
            # ---- CN0359 MODE: show up to 8 sensors in a compact 4-column grid ----
            cn0359_group = QGroupBox("CN0359 Conductivity Sensors")
            cn0359_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 11pt; }")
            cn0359_layout = QGridLayout()
            cn0359_layout.setHorizontalSpacing(12)
            cn0359_layout.setVerticalSpacing(8)
            # Leave room under the group title so first row does not overlap.
            cn0359_layout.setContentsMargins(8, 18, 8, 8)

            for idx, unit_id in enumerate(range(1, self.MAX_CN0359_SENSORS + 1)):
                row = idx // self.CN0359_SENSOR_GRID_COLUMNS
                col = idx % self.CN0359_SENSOR_GRID_COLUMNS

                sensor_row = QVBoxLayout()
                sensor_row.setSpacing(4)
                label = QLabel(f"Sensor {unit_id}:")
                label.setStyleSheet("font-size: 10pt;")
                label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                combo = self._create_combo()
                sensor_row.addWidget(label)
                sensor_row.addWidget(combo)

                cn0359_layout.addLayout(sensor_row, row, col)
                self.cn0359_combos[unit_id] = combo

            cn0359_group.setLayout(cn0359_layout)
            layout.addWidget(cn0359_group)

            # Create a hidden DUT combo so code that references self.dut_combo
            # (e.g., refresh_ports) doesn't crash with AttributeError.
            # It's never shown to the user in CN0359 mode.
            self.dut_combo = self._create_combo()
            self.dut_combo.setVisible(False)
        else:
            # Original single DUT port selector
            dut_group = QGroupBox("DUT Device (Main Sensor)")
            dut_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 11pt; }")
            dut_layout = QVBoxLayout()

            dut_port_layout = QHBoxLayout()
            dut_port_label = QLabel("Port:")
            dut_port_label.setMinimumWidth(80)
            self.dut_combo = self._create_combo()
            dut_port_layout.addWidget(dut_port_label)
            dut_port_layout.addWidget(self.dut_combo, 1)
            dut_layout.addLayout(dut_port_layout)

            dut_group.setLayout(dut_layout)
            layout.addWidget(dut_group)
        
        # IBP References section
        ibp_section = QVBoxLayout()
        
        # Reference 1 group
        self.ref1_group = QGroupBox("IBP Reference Sensor 1")
        self.ref1_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 11pt; }")
        ref1_layout = QVBoxLayout()
        
        ref1_port_layout = QHBoxLayout()
        ref1_port_label = QLabel("Port:")
        ref1_port_label.setMinimumWidth(80)
        self.ref1_combo = self._create_combo()
        ref1_port_layout.addWidget(ref1_port_label)
        ref1_port_layout.addWidget(self.ref1_combo, 1)
        ref1_layout.addLayout(ref1_port_layout)
        
        self.ref1_group.setLayout(ref1_layout)
        ibp_section.addWidget(self.ref1_group)
        
        # Reference 2 group
        self.ref2_group = QGroupBox("IBP Reference Sensor 2")
        self.ref2_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 11pt; }")
        ref2_layout = QVBoxLayout()
        
        ref2_port_layout = QHBoxLayout()
        ref2_port_label = QLabel("Port:")
        ref2_port_label.setMinimumWidth(80)
        self.ref2_combo = self._create_combo()
        ref2_port_layout.addWidget(ref2_port_label)
        ref2_port_layout.addWidget(self.ref2_combo, 1)
        ref2_layout.addLayout(ref2_port_layout)
        
        self.ref2_group.setLayout(ref2_layout)
        ibp_section.addWidget(self.ref2_group)
        
        layout.addLayout(ibp_section)
        
        # Syringe Pump section
        pump_group = QGroupBox("Syringe Pump (Optional)")
        pump_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 11pt; }")
        pump_layout = QVBoxLayout()
        
        pump_port_layout = QHBoxLayout()
        pump_port_label = QLabel("Port:")
        pump_port_label.setMinimumWidth(80)
        self.pump_combo = self._create_combo()
        pump_port_layout.addWidget(pump_port_label)
        pump_port_layout.addWidget(self.pump_combo, 1)
        pump_layout.addLayout(pump_port_layout)
        
        pump_group.setLayout(pump_layout)
        layout.addWidget(pump_group)
        
        # Chiller section
        chiller_group = QGroupBox("Chiller (Optional)")
        chiller_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 11pt; }")
        chiller_layout = QVBoxLayout()
        
        chiller_port_layout = QHBoxLayout()
        chiller_port_label = QLabel("Port:")
        chiller_port_label.setMinimumWidth(80)
        self.chiller_combo = self._create_combo()
        chiller_port_layout.addWidget(chiller_port_label)
        chiller_port_layout.addWidget(self.chiller_combo, 1)
        chiller_layout.addLayout(chiller_port_layout)
        
        chiller_group.setLayout(chiller_layout)
        layout.addWidget(chiller_group)
        
        # Tic Stepper Controllers section
        tic_group = QGroupBox("Tic Stepper Controllers (Optional)")
        tic_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 11pt; }")
        tic_layout = QVBoxLayout()
        
        # TIC A
        tic_a_label = QLabel("TIC A Serial Number:")
        tic_a_label.setStyleSheet("font-weight: bold; color: #3498DB;")
        tic_layout.addWidget(tic_a_label)
        
        tic_a_serial_layout = QHBoxLayout()
        tic_a_serial_label = QLabel("Serial Number:")
        tic_a_serial_label.setMinimumWidth(80)
        self.tic_a_serial_input = QLineEdit()
        self.tic_a_serial_input.setPlaceholderText("e.g., 00461802")
        self.tic_a_serial_input.setStyleSheet("padding: 5px; font-size: 11pt;")
        tic_a_serial_layout.addWidget(tic_a_serial_label)
        tic_a_serial_layout.addWidget(self.tic_a_serial_input, 1)
        
        # Add detect button for TIC A
        detect_tic_a_button = QPushButton(" Detect")
        detect_tic_a_button.setStyleSheet("padding: 5px 10px; font-size: 10pt;")
        detect_tic_a_button.clicked.connect(lambda: self.detect_tic_devices('A'))
        tic_a_serial_layout.addWidget(detect_tic_a_button)
        
        tic_layout.addLayout(tic_a_serial_layout)
        
        # TIC B
        tic_b_label = QLabel("TIC B Serial Number:")
        tic_b_label.setStyleSheet("font-weight: bold; color: #E74C3C; margin-top: 10px;")
        tic_layout.addWidget(tic_b_label)
        
        tic_b_serial_layout = QHBoxLayout()
        tic_b_serial_label = QLabel("Serial Number:")
        tic_b_serial_label.setMinimumWidth(80)
        self.tic_b_serial_input = QLineEdit()
        self.tic_b_serial_input.setPlaceholderText("e.g., 00461803")
        self.tic_b_serial_input.setStyleSheet("padding: 5px; font-size: 11pt;")
        tic_b_serial_layout.addWidget(tic_b_serial_label)
        tic_b_serial_layout.addWidget(self.tic_b_serial_input, 1)
        
        # Add detect button for TIC B
        detect_tic_b_button = QPushButton("Detect")
        detect_tic_b_button.setStyleSheet("padding: 5px 10px; font-size: 10pt;")
        detect_tic_b_button.clicked.connect(lambda: self.detect_tic_devices('B'))
        tic_b_serial_layout.addWidget(detect_tic_b_button)
        
        tic_layout.addLayout(tic_b_serial_layout)
        
        tic_group.setLayout(tic_layout)
        layout.addWidget(tic_group)
        
        # Refresh button
        refresh_button = QPushButton("Refresh Ports")
        refresh_button.setStyleSheet("padding: 8px; font-size: 11pt;")
        refresh_button.clicked.connect(self.refresh_ports)
        layout.addWidget(refresh_button)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.connect_button = QPushButton("Connect")
        self.connect_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 12px;
                font-size: 12pt;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.connect_button.clicked.connect(self.accept_selection)
        
        cancel_button = QPushButton("Cancel")
        cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                padding: 12px;
                font-size: 12pt;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
        """)
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self.connect_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
        # Populate ports and set initial state
        self.refresh_ports()
        self.toggle_ibp_controls()
        
    def toggle_ibp_controls(self):
        """IBP controls are always enabled"""
        # IBP is always enabled, controls always visible
        self.ref1_group.setEnabled(True)
        self.ref2_group.setEnabled(True)

    def refresh_ports(self):
        """Refresh available COM ports"""
        self.dut_combo.clear()
        self.ref1_combo.clear()
        self.ref2_combo.clear()
        self.pump_combo.clear()
        self.chiller_combo.clear()
        for combo in self.cn0359_combos.values():
            combo.clear()
        
        ports = list(serial.tools.list_ports.comports())
        emulator_entries = [
            (f"EMULATOR{unit_id}", f"CN0359 Emulator Sensor {unit_id}")
            for unit_id in range(1, self.MAX_CN0359_SENSORS + 1)
        ]
        has_physical_ports = len(ports) > 0
        can_connect = has_physical_ports or self.cn0359_mode
        self.connect_button.setEnabled(can_connect)

        # Add "None" option for optional devices and sensor slots.
        self.ref1_combo.addItem("None (Disabled)")
        self.ref2_combo.addItem("None (Disabled)")
        self.pump_combo.addItem("None (Disabled)")
        self.chiller_combo.addItem("None (Disabled)")
        for combo in self.cn0359_combos.values():
            combo.addItem("None (Disabled)")

        # Always expose CN0359 emulator targets in CN mode so acquisition
        # can be tested while hardware/fixture work is in progress.
        for combo in self.cn0359_combos.values():
            for emu_port, emu_desc in emulator_entries:
                combo.addItem(f"{emu_port} - {emu_desc}")

        if not has_physical_ports:
            self.dut_combo.addItem("No ports available")
            if not self.cn0359_mode:
                self.ref1_combo.clear()
                self.ref2_combo.clear()
                self.pump_combo.clear()
                self.chiller_combo.clear()
                self.ref1_combo.addItem("No ports available")
                self.ref2_combo.addItem("No ports available")
                self.pump_combo.addItem("No ports available")
                self.chiller_combo.addItem("No ports available")
        else:
            # Add physical ports to all combos.
            for port in ports:
                port_str = f"{port.device} - {port.description}"
                self.dut_combo.addItem(port_str)
                self.ref1_combo.addItem(port_str)
                self.ref2_combo.addItem(port_str)
                self.pump_combo.addItem(port_str)
                self.chiller_combo.addItem(port_str)
                for combo in self.cn0359_combos.values():
                    combo.addItem(port_str)
            
            # Set defaults if provided
            if self.default_dut:
                index = self.dut_combo.findText(self.default_dut, Qt.MatchStartsWith)
                if index >= 0:
                    self.dut_combo.setCurrentIndex(index)
            
            if self.default_ref1:
                index = self.ref1_combo.findText(self.default_ref1, Qt.MatchStartsWith)
                if index >= 0:
                    self.ref1_combo.setCurrentIndex(index)
            
            if self.default_ref2:
                index = self.ref2_combo.findText(self.default_ref2, Qt.MatchStartsWith)
                if index >= 0:
                    self.ref2_combo.setCurrentIndex(index)
            
            if self.default_pump:
                index = self.pump_combo.findText(self.default_pump, Qt.MatchStartsWith)
                if index >= 0:
                    self.pump_combo.setCurrentIndex(index)
            
            if self.default_chiller:
                index = self.chiller_combo.findText(self.default_chiller, Qt.MatchStartsWith)
                if index >= 0:
                    self.chiller_combo.setCurrentIndex(index)
            
            # Set default CN0359 sensor ports from config
            for unit_id, combo in self.cn0359_combos.items():
                defaults = self._cn0359_defaults.get(unit_id)
                if defaults and defaults[0]:
                    index = combo.findText(defaults[0], Qt.MatchStartsWith)
                    if index >= 0:
                        combo.setCurrentIndex(index)

        # In hardware-free CN0359 mode, prefill Sensor N -> EMULATORN
        # unless config.ini already supplied an explicit default.
        if self.cn0359_mode and not has_physical_ports:
            for unit_id, combo in self.cn0359_combos.items():
                defaults = self._cn0359_defaults.get(unit_id)
                if defaults and defaults[0]:
                    continue
                emu_port = f"EMULATOR{unit_id}"
                index = combo.findText(emu_port, Qt.MatchStartsWith)
                if index >= 0:
                    combo.setCurrentIndex(index)

        # Set default Tic serials if provided.
        if self.default_tic_a_serial:
            self.tic_a_serial_input.setText(self.default_tic_a_serial)

        if self.default_tic_b_serial:
            self.tic_b_serial_input.setText(self.default_tic_b_serial)
    
    def detect_tic_devices(self, tic_id='A'):
        """Detect connected Tic devices and populate serial field for specified TIC"""
        try:
            # Import here to avoid dependency if not used
            from modes.hardware.tic_handler import list_tic_devices
            
            devices = list_tic_devices()
            
            if not devices:
                QMessageBox.information(
                    self,
                    "No Tic Devices",
                    "No Tic devices detected.\n\n"
                    "Make sure:\n"
                    "1. Tic is connected via USB\n"
                    "2. ticcmd is installed\n"
                    "3. Tic drivers are installed"
                )
                return
            
            if len(devices) == 1:
                # Auto-fill if only one device
                if tic_id == 'A':
                    self.tic_a_serial_input.setText(devices[0]['serial'])
                else:
                    self.tic_b_serial_input.setText(devices[0]['serial'])
                
                QMessageBox.information(
                    self,
                    "Tic Detected",
                    f"Found Tic device for TIC {tic_id}:\n\n"
                    f"Serial: {devices[0]['serial']}\n"
                    f"Name: {devices[0]['name']}"
                )
            else:
                # Multiple devices - show selection dialog
                serials = [f"{d['serial']} - {d['name']}" for d in devices]
                serial, ok = QInputDialog.getItem(
                    self,
                    f"Select Tic Device for TIC {tic_id}",
                    f"Found {len(devices)} Tic devices.\nSelect one for TIC {tic_id}:",
                    serials,
                    0,
                    False
                )
                
                if ok and serial:
                    # Extract just the serial number
                    serial_num = serial.split(' - ')[0]
                    if tic_id == 'A':
                        self.tic_a_serial_input.setText(serial_num)
                    else:
                        self.tic_b_serial_input.setText(serial_num)
        
        except ImportError:
            QMessageBox.warning(
                self,
                "Error",
                "Unable to import Tic handler module."
            )
        except Exception as e:
            QMessageBox.warning(
                self,
                "Detection Error",
                f"Error detecting Tic devices:\n{str(e)}\n\n"
                "Make sure ticcmd is installed."
            )
    
    def accept_selection(self):
        """Validate and accept port selection"""
        # ---- CN0359 VALIDATION ----
        # In CN0359 mode, we extract port for each sensor the user
        # selected, validate there are no duplicate ports, and require at
        # least one sensor to be configured.
        if self.cn0359_mode:
            self.selected_cn0359_sensors = []
            cn0359_ports_used = []
            for unit_id in range(1, self.MAX_CN0359_SENSORS + 1):
                combo = self.cn0359_combos[unit_id]
                text = combo.currentText()
                if text and text != "No ports available" and text != "None (Disabled)":
                    port = text.split(' - ')[0]
                    address = ""
                    if port in cn0359_ports_used:
                        QMessageBox.warning(
                            self, "Duplicate Ports",
                            f"Sensor {unit_id} uses the same port as another sensor.\n"
                            "Please select different ports."
                        )
                        return
                    cn0359_ports_used.append(port)
                    self.selected_cn0359_sensors.append((unit_id, port, address))
            if not self.selected_cn0359_sensors:
                QMessageBox.warning(self, "No Sensors", "At least one CN0359 sensor port must be selected.")
                return
            self.selected_dut_port = None
        else:
            if self.dut_combo.currentText() == "No ports available":
                QMessageBox.warning(self, "No Ports", "No serial ports available.")
                return
            dut_text = self.dut_combo.currentText()
            self.selected_dut_port = dut_text.split(' - ')[0]
        
        # Extract IBP ports (always enabled, but can be None)
        ref1_text = self.ref1_combo.currentText()
        ref2_text = self.ref2_combo.currentText()
        
        # Handle "None (Disabled)" selection
        if ref1_text == "None (Disabled)":
            self.selected_ref1_port = None
        else:
            self.selected_ref1_port = ref1_text.split(' - ')[0]
        
        if ref2_text == "None (Disabled)":
            self.selected_ref2_port = None
        else:
            self.selected_ref2_port = ref2_text.split(' - ')[0]
        
        # Check for duplicate ports (skip if None)
        ports_in_use = [self.selected_dut_port]
        
        if self.selected_ref1_port and self.selected_ref1_port == self.selected_dut_port:
            QMessageBox.warning(
                self,
                "Duplicate Ports",
                "IBP Reference 1 cannot use the same port as the DUT.\n"
                "Please select a different port."
            )
            return
        if self.selected_ref1_port:
            ports_in_use.append(self.selected_ref1_port)
        
        if self.selected_ref2_port and self.selected_ref2_port == self.selected_dut_port:
            QMessageBox.warning(
                self,
                "Duplicate Ports",
                "IBP Reference 2 cannot use the same port as the DUT.\n"
                "Please select a different port."
            )
            return
        
        if self.selected_ref1_port and self.selected_ref2_port and self.selected_ref2_port == self.selected_ref1_port:
            QMessageBox.warning(
                self,
                "Duplicate Ports",
                "IBP Reference 1 and Reference 2 must use different ports.\n"
                "Please select different ports."
            )
            return
        
        # Extract syringe pump port
        pump_text = self.pump_combo.currentText()
        if pump_text and pump_text != "No ports available" and pump_text != "None (Disabled)":
            self.selected_pump_port = pump_text.split(' - ')[0]
            
            # Check pump port doesn't duplicate DUT or IBP ports
            if self.selected_pump_port == self.selected_dut_port:
                QMessageBox.warning(
                    self,
                    "Duplicate Ports",
                    "Syringe pump cannot use the same port as the DUT.\n"
                    "Please select a different port."
                )
                return
            
            if self.selected_ref1_port and self.selected_pump_port == self.selected_ref1_port:
                QMessageBox.warning(
                    self,
                    "Duplicate Ports",
                    "Syringe pump cannot use the same port as IBP Reference 1.\n"
                    "Please select a different port."
                )
                return
            
            if self.selected_ref2_port and self.selected_pump_port == self.selected_ref2_port:
                QMessageBox.warning(
                    self,
                    "Duplicate Ports",
                    "Syringe pump cannot use the same port as IBP Reference 2.\n"
                    "Please select a different port."
                )
                return
        else:
            self.selected_pump_port = None
        
        # Extract chiller port
        chiller_text = self.chiller_combo.currentText()
        if chiller_text and chiller_text != "No ports available" and chiller_text != "None (Disabled)":
            self.selected_chiller_port = chiller_text.split(' - ')[0]
            
            # Check chiller port doesn't duplicate other ports
            used_ports = [self.selected_dut_port]
            
            if self.selected_ref1_port:
                used_ports.append(self.selected_ref1_port)
            if self.selected_ref2_port:
                used_ports.append(self.selected_ref2_port)
            
            if self.selected_pump_port:
                used_ports.append(self.selected_pump_port)
            
            if self.selected_chiller_port in used_ports:
                QMessageBox.warning(
                    self,
                    "Duplicate Ports",
                    "Chiller cannot use the same port as another device.\n"
                    "Please select a different port."
                )
                return
        else:
            self.selected_chiller_port = None
        
        # Extract Tic serial numbers
        tic_a_serial = self.tic_a_serial_input.text().strip()
        if tic_a_serial:
            self.selected_tic_a_serial = tic_a_serial
        else:
            self.selected_tic_a_serial = None
        
        tic_b_serial = self.tic_b_serial_input.text().strip()
        if tic_b_serial:
            self.selected_tic_b_serial = tic_b_serial
        else:
            self.selected_tic_b_serial = None
        
        # Check if TIC A and TIC B have the same serial number (only if both are set)
        if self.selected_tic_a_serial and self.selected_tic_b_serial:
            if self.selected_tic_a_serial == self.selected_tic_b_serial:
                QMessageBox.warning(
                    self,
                    "Duplicate TIC Serial Numbers",
                    "TIC A and TIC B cannot have the same serial number.\n"
                    "Please use different serial numbers for each TIC controller."
                )
                return
        
        self.accept()
    
    def get_selected_ports(self):
        """Return selected ports as tuple (dut, ref1, ref2, pump, chiller, tic_a_serial, tic_b_serial, use_ibp)"""
        return (
            self.selected_dut_port, 
            self.selected_ref1_port, 
            self.selected_ref2_port,
            self.selected_pump_port,
            self.selected_chiller_port,
            self.selected_tic_a_serial,
            self.selected_tic_b_serial,
            True  # IBP is always enabled
        )

    def get_cn0359_sensors(self):
        """Return the CN0359 sensors the user selected in the dialog.

        Called by acquisition_mode.py after the dialog closes.
        Returns a list of (unit_id, port, "") tuples, e.g.:
            [(1, "COM3", ""), (3, "COM5", "")]
        Empty list if no sensors were selected or CN0359 mode is off.
        """
        return self.selected_cn0359_sensors