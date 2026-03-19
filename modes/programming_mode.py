"""
Programming Mode
Interface to program calibration coefficients onto DUT sensors

Doc status: done, MK, 01/30/2026
"""
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QTextEdit, QLabel, QPushButton, QFileDialog, 
                             QMessageBox, QComboBox, QGroupBox, QProgressBar, QInputDialog)
from PySide6.QtCore import Qt, QTimer, Signal, QThread
from PySide6.QtGui import QFont, QTextCursor
import os
import re
import serial
import serial.tools.list_ports
import time

from modes.dialogs.serial_selector import UnifiedSerialSelector
from modes.utils.version import VERSION_STRING

try:
    from modes.utils import config
except ImportError:
    class ConfigDefaults:
        """
        Configuration defaults for programming mode.
        """
        BAUDRATE = 115200
        TIMEOUT = 5
        DUT_COM_PORT = None
    config = ConfigDefaults()

class ProgrammingWindow(QMainWindow):
    """Main window for programming mode"""
    
    # region INITIALIZATION
    
    def __init__(self):
        """
        Initialize the programming mode window.
        
        Sets up the UI for coefficient programming operations.
        Provides interface for selecting coefficient files and updating DUT devices
        with calibration data.
        """
        super().__init__()
        self.serial_port = None
        self.port_name = None
        self.coefficient_data = {}  # Dict of sensor_num -> coefficients
        self.accepted_sensors = []
        self.rejected_sensors = []
        self.worker_thread = None
        self.sensor_port_map = {}
        self.sensor_port_map_override = {}
        
        # Initialize log file variables (log file created when programming starts)
        self.log_file = None
        self.log_file_path = None
        
        self.init_ui()
        
        # Try to connect to DUT automatically only if the configured port exists.
        if config.DUT_COM_PORT:
            configured_port = str(config.DUT_COM_PORT).strip()
            if configured_port and self.is_port_available(configured_port):
                QTimer.singleShot(500, lambda: self.connect_to_port(configured_port, show_error_dialog=False))
            else:
                self.log(
                    f"Saved DUT port '{config.DUT_COM_PORT}' not found. Please select an active COM port.",
                    "orange",
                )
    
    def setup_log_file(self):
        """Setup log file for programming mode"""
        from datetime import datetime
        
        # Use the same save directory as analysis mode (from settings)
        try:
            from modes.utils import settings
            save_directory = settings.SAVE_DIRECTORY if hasattr(settings, 'SAVE_DIRECTORY') and settings.SAVE_DIRECTORY else "."
        except ImportError:
            save_directory = "."
        
        save_directory = os.path.expanduser(save_directory)
        save_directory = os.path.abspath(save_directory)
        
        # Create directory if it doesn't exist
        try:
            os.makedirs(save_directory, exist_ok=True)
        except Exception as e:
            print(f"Could not create save directory: {str(e)}")
            save_directory = os.getcwd()
        
        # Create timestamped log filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file_path = os.path.join(save_directory, f"programming_log_{timestamp}.txt")
        
        # Initialize log file
        try:
            self.log_file = open(self.log_file_path, 'w', encoding='utf-8')
            self.log_file.write(f"Programming Mode Log - Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            self.log_file.write("=" * 80 + "\n\n")
            self.log_file.flush()
            print(f"Programming log file: {self.log_file_path}")
        except Exception as e:
            print(f"Failed to create programming log file: {str(e)}")
            self.log_file = None
    
    def write_to_log(self, message):
        """Write message to log file with timestamp"""
        if self.log_file and not self.log_file.closed:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            try:
                self.log_file.write(f"[{timestamp}] {message}\n")
                self.log_file.flush()
            except Exception as e:
                print(f"Error writing to log: {str(e)}")
    
    def close_log_file(self):
        """Close the log file"""
        if self.log_file and not self.log_file.closed:
            from datetime import datetime
            self.log_file.write(f"\nProgramming Mode Log - Ended at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            self.log_file.write("=" * 80 + "\n")
            self.log_file.close()
            print(f"Programming log file closed: {self.log_file_path}")
    
    def log_and_display(self, message, color="white"):
        """Write message to both log file and display"""
        self.write_to_log(message)
        self.append_log(message, color)

    # endregion
    
    # region UI INITIALIZATION

    
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle(f"DUT Programming Mode - {VERSION_STRING}")
        self.setMinimumSize(900, 700)
        
        # Central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Title
        title = QLabel("DUT Coefficient Programming")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)
        
        # Connection section
        conn_group = QGroupBox("Serial Connection")
        conn_layout = QHBoxLayout()
        
        self.port_label = QLabel("Not Connected")
        self.port_label.setStyleSheet("color: red; font-weight: bold;")
        conn_layout.addWidget(QLabel("DUT Port:"))
        conn_layout.addWidget(self.port_label)
        conn_layout.addStretch()
        
        self.connect_btn = QPushButton("Connect to DUT")
        self.connect_btn.clicked.connect(self.select_serial_port)
        conn_layout.addWidget(self.connect_btn)
        
        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.clicked.connect(self.disconnect_serial)
        self.disconnect_btn.setEnabled(False)
        conn_layout.addWidget(self.disconnect_btn)

        self.mapping_btn = QPushButton("Open Port Mapping Setup")
        self.mapping_btn.clicked.connect(self.open_port_mapping_setup)
        conn_layout.addWidget(self.mapping_btn)
        
        conn_group.setLayout(conn_layout)
        main_layout.addWidget(conn_group)

        self.mode_badge = QLabel("")
        self.mode_badge.setVisible(False)
        self.mode_badge.setStyleSheet("""
            QLabel {
                background-color: #8B4513;
                color: #FFD700;
                font-weight: bold;
                padding: 6px;
                border: 1px solid #AA7733;
            }
        """)
        main_layout.addWidget(self.mode_badge)
        
        # File selection section
        file_group = QGroupBox("Coefficient File")
        file_layout = QHBoxLayout()
        
        self.file_label = QLabel("No file selected")
        file_layout.addWidget(QLabel("File:"))
        file_layout.addWidget(self.file_label, 1)
        
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self.browse_coefficient_file)
        file_layout.addWidget(self.browse_btn)
        
        file_group.setLayout(file_layout)
        main_layout.addWidget(file_group)
        
        # Sensor selection section
        sensor_group = QGroupBox("Sensors to Program")
        sensor_layout = QHBoxLayout()
        
        sensor_layout.addWidget(QLabel("Select sensors:"))
        
        self.sensor_combo = QComboBox()
        self.sensor_combo.setEnabled(False)
        sensor_layout.addWidget(self.sensor_combo, 1)
        
        sensor_layout.addStretch()
        
        sensor_group.setLayout(sensor_layout)
        main_layout.addWidget(sensor_group)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)
        
        # Log display
        log_label = QLabel("Programming Log:")
        main_layout.addWidget(log_label)
        
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setFont(QFont("Courier New", 9))
        self.log_display.setStyleSheet("""
            QTextEdit {
                background-color: #000000;
                color: #FFFFFF;
                border: 1px solid #666666;
            }
        """)
        main_layout.addWidget(self.log_display, 1)
        
        # Control buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.program_btn = QPushButton("Program DUT")
        self.program_btn.setEnabled(False)
        self.program_btn.clicked.connect(self.start_programming)
        self.program_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 10px 30px;
                border-radius: 5px;
                font-size: 11pt;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        button_layout.addWidget(self.program_btn)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_programming)
        button_layout.addWidget(self.cancel_btn)
        
        self.clear_log_btn = QPushButton("Clear Log")
        self.clear_log_btn.clicked.connect(self.clear_log)
        button_layout.addWidget(self.clear_log_btn)
        
        button_layout.addStretch()
        
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)
        button_layout.addWidget(self.close_btn)
        
        main_layout.addLayout(button_layout)
        
        # Initial log message
        self.log("Programming Mode initialized. Connect to DUT and load coefficient file to begin.", "blue")
    
    # endregion
    
    # region SERIAL CONNECTION
    
    def select_serial_port(self):
        """Open a DUT-only serial port picker and connect."""
        ports = list(serial.tools.list_ports.comports())
        if not ports:
            QMessageBox.warning(self, "No Ports", "No serial ports were detected. Connect DUT and try again.")
            self.log("No COM ports detected.", "orange")
            return

        port_entries = [f"{p.device} - {p.description}" for p in ports]
        devices = [p.device for p in ports]
        default_port = self.port_name or getattr(config, "DUT_COM_PORT", None)
        default_index = 0
        if default_port and default_port in devices:
            default_index = devices.index(default_port)

        selected_text, ok = QInputDialog.getItem(
            self,
            "Select DUT COM Port",
            "DUT Port:",
            port_entries,
            default_index,
            False,
        )
        if not ok or not selected_text:
            return

        dut_port = selected_text.split(" - ")[0].strip()
        if dut_port:
            self.connect_to_port(dut_port)

    def open_port_mapping_setup(self):
        """Open unified selector to edit and save sensor COM mapping."""
        if not getattr(config, "CN0359_ENABLED", False):
            QMessageBox.information(
                self,
                "CN0359 Mapping Disabled",
                "CN0359 mapping is currently disabled in configuration.\n"
                "Enable CN0359 mode to edit per-sensor COM mappings."
            )
            return

        dialog = UnifiedSerialSelector(
            self,
            default_dut=self.port_name or getattr(config, "DUT_COM_PORT", None),
            default_ref1=getattr(config, "IBP_REF1_PORT", None),
            default_ref2=getattr(config, "IBP_REF2_PORT", None),
            default_pump=getattr(config, "SYRINGE_PUMP_PORT", None),
            default_chiller=getattr(config, "CHILLER_PORT", None),
            default_tic_a_serial=getattr(config, "TIC_A_SERIAL_NUMBER", None),
            default_tic_b_serial=getattr(config, "TIC_B_SERIAL_NUMBER", None),
            enable_ibp=True,
        )
        if not dialog.exec():
            return

        cn0359_sensors = dialog.get_cn0359_sensors()
        updated_map = {
            int(unit_id): str(port).strip()
            for unit_id, port, *_ in cn0359_sensors
            if str(port).strip()
        }
        if not updated_map:
            QMessageBox.warning(
                self,
                "No Sensor Mappings",
                "No CN0359 sensor COM mappings were selected."
            )
            return

        self.sensor_port_map_override = updated_map
        config.CN0359_SENSORS = [(unit_id, port, "") for unit_id, port in sorted(updated_map.items())]

        try:
            from modes.utils.settings import save_ports_to_config, save_cn0359_sensors_to_config
            ports = dialog.get_selected_ports()
            save_ports_to_config(
                dut_port=ports[0],
                ref1_port=ports[1],
                ref2_port=ports[2],
                pump_port=ports[3],
                chiller_port=ports[4],
                tic_a_serial=ports[5],
                tic_b_serial=ports[6],
            )
            save_cn0359_sensors_to_config(
                sensor_configs=config.CN0359_SENSORS,
                enabled=getattr(config, "CN0359_ENABLED", True),
            )
        except Exception:
            self.log("Warning: Could not persist mapping to config.ini (session mapping still applied).", "orange")

        mapped_summary = ", ".join(f"S{unit}->{port}" for unit, port in sorted(updated_map.items()))
        self.log(f"Updated sensor fixture mapping: {mapped_summary}", "blue")
    
    def connect_to_port(self, port_name, show_error_dialog=True):
        """Connect to the specified serial port"""
        try:
            self.serial_port = serial.Serial(
                port=port_name,
                baudrate=config.BAUDRATE,
                timeout=config.TIMEOUT
            )
            
            self.port_name = port_name
            self.port_label.setText(f"{port_name} (Connected)")
            self.port_label.setStyleSheet("color: green; font-weight: bold;")
            
            self.connect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(True)
            
            self.log(f"Connected to DUT on {port_name}", "green")
            self.save_dut_port_to_config(port_name)
            if str(port_name).upper().startswith("EMULATOR"):
                self.mode_badge.setText("EMULATOR MODE ACTIVE (programming target is simulated)")
                self.mode_badge.setVisible(True)
            else:
                self.mode_badge.setVisible(False)

            probe_ok, probe_summary = self.probe_dut_identity()
            if probe_ok:
                self.log(f"DUT identity check: {probe_summary}", "blue")
            else:
                reply = QMessageBox.warning(
                    self,
                    "DUT Identity Not Confirmed",
                    "Connected COM port did not return a valid DUT identity.\n\n"
                    f"Details: {probe_summary}\n\n"
                    "Continue anyway?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if reply != QMessageBox.Yes:
                    self.disconnect_serial()
                    return
                self.log(
                    f"Proceeding without DUT identity confirmation on {port_name}: {probe_summary}",
                    "orange",
                )
            
            self.update_program_button_state()
            
        except Exception as e:
            if show_error_dialog:
                QMessageBox.critical(self, "Connection Error", 
                                  f"Failed to connect to {port_name}:\n{str(e)}")
            self.log(f"Connection failed: {str(e)}", "red")

    def is_port_available(self, port_name):
        """Return True if the requested COM port is currently enumerated."""
        try:
            available = {p.device for p in serial.tools.list_ports.comports()}
            return str(port_name).strip() in available
        except Exception:
            return False

    def save_dut_port_to_config(self, port_name):
        """Persist selected DUT port so reconnect defaults are correct next launch."""
        try:
            from modes.utils.settings import save_ports_to_config
            if save_ports_to_config(dut_port=port_name):
                config.DUT_COM_PORT = port_name
        except Exception:
            # Non-fatal: programming can proceed without persisting config.
            pass

    def probe_dut_identity(self):
        """Probe DUT identity from the connected serial device."""
        if not self.serial_port or not self.serial_port.is_open:
            return False, "serial port not open"
        try:
            self.serial_port.reset_input_buffer()
            self.serial_port.write(b"getver\n")
            self.serial_port.flush()
            time.sleep(0.2)

            deadline = time.time() + 1.5
            response = ""
            while time.time() < deadline:
                waiting = getattr(self.serial_port, "in_waiting", 0)
                if waiting:
                    chunk = self.serial_port.read(waiting).decode("utf-8", errors="ignore")
                    response += chunk
                    if "Serial Number" in response and "Firmware version" in response:
                        break
                time.sleep(0.05)

            blob = response.strip()
            if not blob:
                return False, "no response to getver"
            if "Firmware version" in blob or "Hardware version" in blob or "Serial Number" in blob:
                summary = " | ".join(
                    ln.strip() for ln in blob.splitlines()
                    if ln.strip() and (
                        "Firmware version" in ln
                        or "Hardware version" in ln
                        or "Serial Number" in ln
                    )
                )
                return True, summary or "version block received"
            return False, f"unexpected getver response: {blob[:120]}"
        except Exception as e:
            return False, str(e)
    
    def disconnect_serial(self):
        """Disconnect from serial port"""
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
            self.log(f"Disconnected from {self.port_name}", "orange")
        
        self.serial_port = None
        self.port_name = None
        self.port_label.setText("Not Connected")
        self.port_label.setStyleSheet("color: red; font-weight: bold;")
        self.mode_badge.setVisible(False)
        
        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)
        
        self.update_program_button_state()
    
    # endregion
    
    # region COEFFICIENT FILE HANDLING
    
    def browse_coefficient_file(self):
        """Open file browser to select coefficient file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Coefficient File",
            "",
            "Text Files (*_coefficients.txt);;All Files (*.*)"
        )
        
        if file_path:
            self.load_coefficient_file(file_path)
    
    def load_coefficient_file(self, file_path):
        """Parse and load coefficient file"""
        self.write_to_log(f"Loading coefficient file: {file_path}")
        try:
            self.coefficient_data = {}
            
            with open(file_path, 'r') as f:
                content = f.read()
            
            # First, parse acceptance status
            acceptance_status = {}
            acceptance_section = content.split('CALIBRATION ACCEPTANCE STATUS')
            if len(acceptance_section) > 1:
                acceptance_text = acceptance_section[1]
                # Look for patterns like "J1: ACCEPTED" or "J1: REJECTED"
                for match in re.finditer(r'J(\d+):\s*(ACCEPTED|REJECTED)', acceptance_text, re.IGNORECASE):
                    sensor_num = int(match.group(1))
                    status = match.group(2).upper()
                    acceptance_status[sensor_num] = status
                    self.log(f"Sensor {sensor_num}: {status}", "blue" if status == "ACCEPTED" else "red")
            
            # Parse the file for each sensor
            # Look for patterns like "SENSOR 1" followed by temperature and model sections
            sensor_pattern = r'SENSOR\s+(\d+)'
            sensor_matches = list(re.finditer(sensor_pattern, content))
            
            rejected_sensors = []
            accepted_sensors = []
            
            for i, match in enumerate(sensor_matches):
                sensor_num = int(match.group(1))
                start_pos = match.end()
                
                # Check acceptance status - skip if rejected
                if acceptance_status.get(sensor_num) == "REJECTED":
                    rejected_sensors.append(sensor_num)
                    continue
                
                # Find end position (next sensor or end of file)
                if i + 1 < len(sensor_matches):
                    end_pos = sensor_matches[i + 1].start()
                else:
                    # Look for summary section or end of file
                    summary_match = re.search(r'SUMMARY TABLE', content[start_pos:])
                    if summary_match:
                        end_pos = start_pos + summary_match.start()
                    else:
                        end_pos = len(content)
                
                sensor_section = content[start_pos:end_pos]
                
                # Extract temperature calibration
                temp_scale = self.extract_value(sensor_section, r'Scale:\s*([-\d.]+)')
                temp_offset = self.extract_value(sensor_section, r'Offset:\s*([-\d.]+)')
                
                # Extract Dual-Range Aly Model 2 coefficients (all three sets)
                # Look for HIGH RANGE, LOW RANGE, and GLOBAL MODEL sections
                
                # HIGH RANGE coefficients
                high_range_match = re.search(r'HIGH RANGE.*?K:\s*([-\d.]+)\s+Alpha:\s*([-\d.]+)\s+Eta:\s*([-\d.]+)\s+Zeta:\s*([-\d.]+)', sensor_section, re.DOTALL)
                if high_range_match:
                    k_high = float(high_range_match.group(1))
                    alpha_high = float(high_range_match.group(2))
                    eta_high = float(high_range_match.group(3))
                    zeta_high = float(high_range_match.group(4))
                else:
                    k_high = alpha_high = eta_high = zeta_high = None
                
                # LOW RANGE coefficients
                low_range_match = re.search(r'LOW RANGE.*?K:\s*([-\d.]+)\s+Alpha:\s*([-\d.]+)\s+Eta:\s*([-\d.]+)\s+Zeta:\s*([-\d.]+)', sensor_section, re.DOTALL)
                if low_range_match:
                    k_low = float(low_range_match.group(1))
                    alpha_low = float(low_range_match.group(2))
                    eta_low = float(low_range_match.group(3))
                    zeta_low = float(low_range_match.group(4))
                else:
                    k_low = alpha_low = eta_low = zeta_low = None
                
                # GLOBAL MODEL coefficients
                global_match = re.search(r'GLOBAL MODEL.*?K:\s*([-\d.]+)\s+Alpha:\s*([-\d.]+)\s+Eta:\s*([-\d.]+)\s+Zeta:\s*([-\d.]+)', sensor_section, re.DOTALL)
                if global_match:
                    k_global = float(global_match.group(1))
                    alpha_global = float(global_match.group(2))
                    eta_global = float(global_match.group(3))
                    zeta_global = float(global_match.group(4))
                else:
                    k_global = alpha_global = eta_global = zeta_global = None
                
                # Check if we have all required coefficients
                if temp_scale is not None and temp_offset is not None:
                    if all(v is not None for v in [k_high, alpha_high, eta_high, zeta_high, 
                                                    k_low, alpha_low, eta_low, zeta_low,
                                                    k_global, alpha_global, eta_global, zeta_global]):
                        self.coefficient_data[sensor_num] = {
                            'temp_scale': temp_scale,
                            'temp_offset': temp_offset,
                            'k_high': k_high,
                            'alpha_high': alpha_high,
                            'eta_high': eta_high,
                            'zeta_high': zeta_high,
                            'k_low': k_low,
                            'alpha_low': alpha_low,
                            'eta_low': eta_low,
                            'zeta_low': zeta_low,
                            'k_global': k_global,
                            'alpha_global': alpha_global,
                            'eta_global': eta_global,
                            'zeta_global': zeta_global
                        }
                        accepted_sensors.append(sensor_num)
            
            if self.coefficient_data:
                self.accepted_sensors = sorted(accepted_sensors)
                self.rejected_sensors = sorted(rejected_sensors)
                self.file_label.setText(os.path.basename(file_path))
                
                # Update sensor combo box
                self.sensor_combo.clear()
                sensor_nums = sorted(self.coefficient_data.keys())
                
                # Add individual sensors
                for num in sensor_nums:
                    self.sensor_combo.addItem(f"Sensor {num}", num)
                
                # Add "All Sensors" option
                if len(sensor_nums) > 1:
                    self.sensor_combo.insertItem(0, f"All Sensors ({len(sensor_nums)} total)", "all")
                    self.sensor_combo.setCurrentIndex(0)
                
                self.sensor_combo.setEnabled(True)
                
                self.log(f"Loaded coefficients for {len(sensor_nums)} ACCEPTED sensor(s): {sensor_nums}", "green")
                
                if rejected_sensors:
                    self.log(f"Skipped {len(rejected_sensors)} REJECTED sensor(s): {rejected_sensors}", "orange")
                
                # Show coefficient summary
                for num in sensor_nums:
                    coeffs = self.coefficient_data[num]
                    self.log(f"\nSensor {num}:", "blue")
                    self.log(f"  Temp: Scale={coeffs['temp_scale']:.10f}, Offset={coeffs['temp_offset']:.10f}", "white")
                    self.log(f"  HIGH RANGE: K={coeffs['k_high']:.10f}, α={coeffs['alpha_high']:.10f}, η={coeffs['eta_high']:.10f}, ζ={coeffs['zeta_high']:.10f}", "white")
                    self.log(f"  LOW RANGE:  K={coeffs['k_low']:.10f}, α={coeffs['alpha_low']:.10f}, η={coeffs['eta_low']:.10f}, ζ={coeffs['zeta_low']:.10f}", "white")
                    self.log(f"  GLOBAL:     K={coeffs['k_global']:.10f}, α={coeffs['alpha_global']:.10f}, η={coeffs['eta_global']:.10f}, ζ={coeffs['zeta_global']:.10f}", "white")
            else:
                self.accepted_sensors = []
                self.rejected_sensors = sorted(rejected_sensors)
                if rejected_sensors:
                    raise ValueError(f"All sensors in file are REJECTED: {rejected_sensors}")
                else:
                    raise ValueError("No valid sensor data found in file")
            
            self.update_program_button_state()
            
        except Exception as e:
            QMessageBox.critical(self, "File Error", 
                               f"Failed to load coefficient file:\n{str(e)}")
            self.log(f"File load error: {str(e)}", "red")
            self.file_label.setText("No file selected")
            self.sensor_combo.clear()
            self.sensor_combo.setEnabled(False)
    
    def extract_value(self, text, pattern):
        """Extract float value using regex pattern"""
        match = re.search(pattern, text)
        if match:
            return float(match.group(1))
        return None
    
    # endregion
    
    # region PROGRAMMING OPERATIONS
    
    def update_program_button_state(self):
        """Enable/disable program button based on connection and file status"""
        can_program = (
            self.serial_port is not None and 
            self.serial_port.is_open and 
            len(self.coefficient_data) > 0
        )
        self.program_btn.setEnabled(can_program)
    
    def start_programming(self):
        """Start the programming process"""
        # Setup log file now (only when programming is actually started)
        if self.log_file is None:
            self.setup_log_file()
        
        # Determine which sensors to program
        current_data = self.sensor_combo.currentData()
        
        if current_data == "all":
            sensors_to_program = sorted(self.coefficient_data.keys())
        else:
            sensors_to_program = [current_data]

        sensor_port_map = self.get_sensor_port_map()
        dut_write_port = self.port_name or "Unknown"
        missing_mapping = [sensor_num for sensor_num in sensors_to_program if sensor_num not in sensor_port_map]
        mapping_lines = []
        for sensor_num in sensors_to_program:
            mapped_port = sensor_port_map.get(sensor_num, "(not configured)")
            mapping_lines.append(f"  Sensor {sensor_num} -> {mapped_port}")
        mapping_text = "\n".join(mapping_lines) if mapping_lines else "  (none)"

        # Enforce traceable mapping before any EEPROM write.
        if missing_mapping:
            missing_txt = ", ".join(str(n) for n in missing_mapping)
            QMessageBox.warning(
                self,
                "Missing Sensor Port Mapping",
                "Programming is blocked because one or more selected sensors "
                "do not have a configured fixture COM mapping.\n\n"
                f"Missing mapping for sensor(s): {missing_txt}\n\n"
                "Update sensor COM assignments in configuration, then retry."
            )
            self.log(
                f"Programming blocked: missing fixture COM mapping for sensor(s): {missing_txt}",
                "red",
            )
            return
        
        # Confirm with user
        sensor_list = ", ".join(str(s) for s in sensors_to_program)
        reply = QMessageBox.question(
            self,
            "Confirm Programming",
            f"Coefficient file: {self.file_label.text()}\n"
            f"DUT write COM port: {dut_write_port}\n"
            f"Accepted sensors in file: {self.accepted_sensors or 'n/a'}\n"
            f"Rejected sensors skipped: {self.rejected_sensors or 'none'}\n\n"
            f"Sensor-to-port mapping:\n{mapping_text}\n\n"
            f"Program coefficient(s) to sensor(s): {sensor_list}?\n\n"
            "This permanently writes to EEPROM.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # Prepare sensor data for worker
        sensor_data = [(num, self.coefficient_data[num]) for num in sensors_to_program]
        self.sensor_port_map = sensor_port_map
        
        # Disable controls
        self.program_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.connect_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(False)
        self.mapping_btn.setEnabled(False)
        self.browse_btn.setEnabled(False)
        self.sensor_combo.setEnabled(False)
        
        # Show progress bar
        self.progress_bar.setMaximum(len(sensors_to_program))
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        
        self.log(f"\n{'='*60}", "white")
        self.log(f"Starting programming for {len(sensors_to_program)} sensor(s)...", "blue")
        self.log(f"DUT write port: {self.port_name or 'Unknown'}", "blue")
        for sensor_num in sensors_to_program:
            mapped_port = self.sensor_port_map.get(sensor_num)
            if mapped_port:
                self.log(f"Sensor {sensor_num} mapped fixture port: {mapped_port}", "gray")
            else:
                self.log(f"Sensor {sensor_num} mapped fixture port: (not configured)", "gray")
        self.log(f"{'='*60}", "white")
        
        # Start worker thread
        self.worker_thread = ProgrammingWorker(
            self.serial_port,
            sensor_data,
            sensor_port_map=self.sensor_port_map,
            dut_port_name=self.port_name,
        )
        self.worker_thread.log_message.connect(self.log)
        self.worker_thread.progress_update.connect(self.update_progress)
        self.worker_thread.programming_complete.connect(self.programming_finished)
        self.worker_thread.start()
    
    def cancel_programming(self):
        """Cancel ongoing programming operation"""
        if self.worker_thread and self.worker_thread.isRunning():
            reply = QMessageBox.question(
                self,
                "Cancel Programming",
                "Are you sure you want to cancel the programming operation?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                self.log("Cancelling programming...", "orange")
                self.worker_thread.stop()
                self.worker_thread.wait()
                self.programming_finished(False, "Cancelled by user")
    
    def update_progress(self, current, total):
        """Update progress bar"""
        self.progress_bar.setValue(current)
        self.log(f"Progress: {current}/{total} sensors completed", "blue")
    
    def programming_finished(self, success, message):
        """Handle programming completion"""
        # Re-enable controls
        self.program_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.connect_btn.setEnabled(not self.serial_port or not self.serial_port.is_open)
        self.disconnect_btn.setEnabled(self.serial_port and self.serial_port.is_open)
        self.mapping_btn.setEnabled(True)
        self.browse_btn.setEnabled(True)
        self.sensor_combo.setEnabled(True)
        
        # Hide progress bar
        self.progress_bar.setVisible(False)
        
        # Log result
        self.log(f"\n{'='*60}", "white")
        if success:
            self.log(f"[SUCCESS] {message}", "green")
            QMessageBox.information(self, "Success", message)
        else:
            self.log(f"[FAILED] {message}", "red")
            QMessageBox.warning(self, "Programming Failed", message)
        self.log(f"{'='*60}", "white")

        # region optional cloudHook
        # potential spot to add cloud hook, once programming is complete. 
        # end region
    
    # endregion
    
    # region UTILITY METHODS
    
    def log(self, message, color="white"):
        """Add message to log display with color and write to log file"""
        # Write to log file
        self.write_to_log(message)
        
        # Display in UI
        color_map = {
            "white": "#FFFFFF",
            "black": "#FFFFFF",  # Map black to white for visibility on black background
            "red": "#FF6666",
            "green": "#66FF66",
            "blue": "#6699FF",
            "orange": "#FFAA00",
            "gray": "#AAAAAA"
        }
        
        html_color = color_map.get(color, "#FFFFFF")
        self.log_display.append(f'<span style="color: {html_color};">{message}</span>')
        
        # Auto-scroll to bottom
        cursor = self.log_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_display.setTextCursor(cursor)
    
    def clear_log(self):
        """Clear the log display"""
        self.log_display.clear()
        self.log("Log cleared.", "gray")

    def get_sensor_port_map(self):
        """Read configured sensor->COM mapping (from CN0359 settings) for traceability logs."""
        if self.sensor_port_map_override:
            return dict(self.sensor_port_map_override)
        sensor_map = {}
        try:
            raw_entries = getattr(config, "CN0359_SENSORS", []) or []
            for entry in raw_entries:
                if not entry:
                    continue
                unit_id = int(entry[0])
                port = str(entry[1]).strip() if len(entry) > 1 else ""
                if unit_id > 0 and port:
                    sensor_map[unit_id] = port
        except Exception:
            pass
        return sensor_map
    
    # endregion
    
    # region EVENT HANDLERS
    
    def closeEvent(self, event):
        """Handle window close event"""
        # Stop worker thread if running
        if self.worker_thread and self.worker_thread.isRunning():
            reply = QMessageBox.question(
                self,
                "Programming in Progress",
                "Programming is in progress. Are you sure you want to exit?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply != QMessageBox.Yes:
                event.ignore()
                return
            
            self.worker_thread.stop()
            self.worker_thread.wait()
        
        # Disconnect serial
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
        
        # Close log file
        self.close_log_file()
        
        event.accept()
    
    # endregion

class ProgrammingWorker(QThread):
    """Worker thread for programming operations"""
    log_message = Signal(str, str)  # message, color
    progress_update = Signal(int, int)  # current, total
    programming_complete = Signal(bool, str)  # success, message
    
    def __init__(self, serial_port, sensor_data, sensor_port_map=None, dut_port_name=None):
        """
        Initialize the programming worker thread.
        
        Creates a worker thread for programming calibration coefficients to DUT
        devices via serial communication.
        
        Args:
            serial_port (serial.Serial): Open serial port for DUT communication.
            sensor_data (list): List of (sensor_num, coefficients) tuples to program.
        """
        super().__init__()
        self.serial_port = serial_port
        self.sensor_data = sensor_data  # List of (sensor_num, coefficients) tuples
        self.sensor_port_map = sensor_port_map or {}
        self.dut_port_name = dut_port_name
        self.running = True
        
    def run(self):
        """Program all sensors"""
        try:
            total_sensors = len(self.sensor_data)
            successful_sensors = []
            failed_sensors = []
            
            for idx, (sensor_num, coeffs) in enumerate(self.sensor_data):
                if not self.running:
                    self.programming_complete.emit(False, "Programming cancelled by user")
                    return
                
                self.progress_update.emit(idx + 1, total_sensors)
                self.log_message.emit(f"\n=== Programming Sensor {sensor_num} ===", "blue")
                mapped_port = self.sensor_port_map.get(sensor_num)
                if mapped_port:
                    self.log_message.emit(
                        f"Traceability: Sensor {sensor_num} fixture port={mapped_port}; DUT write port={self.dut_port_name or 'Unknown'}",
                        "gray",
                    )
                
                # Select the sensor
                success = self.send_command_and_wait(f"j {sensor_num}", f"Selected Unit: {sensor_num}")
                if not success:
                    self.log_message.emit(f"[ERROR] Failed to select sensor {sensor_num}, skipping...", "red")
                    failed_sensors.append(sensor_num)
                    continue  # Continue to next sensor instead of returning
                
                # Build the save command with coefficients in device order
                # Format: k_high,alpha_high,eta_high,zeta_high,k_low,alpha_low,eta_low,zeta_low,k_global,alpha_global,eta_global,zeta_global,temp_scale,temp_offset
                # Device stores: 0-7 as doubles (high/low range), 8-13 as floats (global + temp)
                save_cmd = (f"save,{coeffs['k_high']},{coeffs['alpha_high']},{coeffs['eta_high']},{coeffs['zeta_high']},"
                           f"{coeffs['k_low']},{coeffs['alpha_low']},{coeffs['eta_low']},{coeffs['zeta_low']},"
                           f"{coeffs['k_global']},{coeffs['alpha_global']},{coeffs['eta_global']},{coeffs['zeta_global']},"
                           f"{coeffs['temp_scale']},{coeffs['temp_offset']}")
                self.log_message.emit(f"Sending save command with all coefficient sets...", "white")
                self.log_message.emit(f"  HIGH RANGE: K={coeffs['k_high']:.10f}, α={coeffs['alpha_high']:.10f}, η={coeffs['eta_high']:.10f}, ζ={coeffs['zeta_high']:.10f}", "gray")
                self.log_message.emit(f"  LOW RANGE:  K={coeffs['k_low']:.10f}, α={coeffs['alpha_low']:.10f}, η={coeffs['eta_low']:.10f}, ζ={coeffs['zeta_low']:.10f}", "gray")
                self.log_message.emit(f"  GLOBAL:     K={coeffs['k_global']:.10f}, α={coeffs['alpha_global']:.10f}, η={coeffs['eta_global']:.10f}, ζ={coeffs['zeta_global']:.10f}", "gray")
                self.log_message.emit(f"  TEMP:       Scale={coeffs['temp_scale']:.10f}, Offset={coeffs['temp_offset']:.10f}", "gray")
                
                # Send save command
                self.serial_port.write((save_cmd + '\r\n').encode('utf-8'))
                self.serial_port.flush()
                time.sleep(0.5)
                
                # Read the confirmation prompt
                confirmation_text = self.read_until_prompt("Confirm write to EEPROM? (y/n)")
                if confirmation_text:
                    self.log_message.emit(confirmation_text, "gray")
                    
                    # Verify the values in the confirmation
                    if not self.verify_confirmation_values(confirmation_text, coeffs):
                        self.log_message.emit(f"[ERROR] Coefficient mismatch in sensor {sensor_num} confirmation, skipping...", "red")
                        failed_sensors.append(sensor_num)
                        continue  # Continue to next sensor instead of returning
                else:
                    self.log_message.emit(f"[ERROR] No confirmation prompt received for sensor {sensor_num}, skipping...", "red")
                    failed_sensors.append(sensor_num)
                    continue  # Continue to next sensor instead of returning
                
                # Send confirmation
                self.log_message.emit("Sending: y", "white")
                self.serial_port.write(b'y\r\n')
                self.serial_port.flush()
                time.sleep(0.5)
                
                # Read response after confirmation
                response = self.read_response(timeout=2.0)
                self.log_message.emit(response, "green")
                
                # Check if all values are zeros (device not connected/powered)
                if "Verification Failed" in response and response.count("0.000000") >= 10:
                    self.log_message.emit("", "red")
                    self.log_message.emit("=" * 60, "red")
                    self.log_message.emit(f"PROGRAMMING ERROR: CHECK CONNECTION OF SENSOR {sensor_num}", "red")
                    self.log_message.emit("=" * 60, "red")
                    self.log_message.emit("All coefficient values read back as zero.", "red")
                    self.log_message.emit("This sensor may not be connected or powered.", "red")
                    self.log_message.emit("=" * 60, "red")
                    failed_sensors.append(sensor_num)
                    continue  # Continue to next sensor instead of returning
                
                # Check for success
                if "verification successful" in response.lower() or "successfully" in response.lower() or "saved" in response.lower():
                    self.log_message.emit(f"[SUCCESS] Sensor {sensor_num} programmed successfully", "green")
                    successful_sensors.append(sensor_num)
                else:
                    self.log_message.emit(f"[WARNING] Unexpected response for sensor {sensor_num}", "orange")
                    failed_sensors.append(sensor_num)
                
                time.sleep(0.5)  # Brief pause between sensors
            
            # Report final results
            if failed_sensors:
                message = f"Programming completed: {len(successful_sensors)} succeeded, {len(failed_sensors)} failed\nFailed sensors: {failed_sensors}"
                self.programming_complete.emit(len(failed_sensors) == 0, message)
            else:
                self.programming_complete.emit(True, f"Successfully programmed all {total_sensors} sensor(s)")
            
        except Exception as e:
            self.programming_complete.emit(False, f"Programming error: {str(e)}")
    
    def send_command_and_wait(self, command, expected_response=None, timeout=2.0):
        """Send command and optionally wait for expected response"""
        try:
            self.serial_port.write((command + '\r\n').encode('utf-8'))
            self.serial_port.flush()
            time.sleep(0.3)
            
            if expected_response:
                response = self.read_response(timeout)
                self.log_message.emit(response, "gray")
                return expected_response.lower() in response.lower()
            return True
        except Exception as e:
            self.log_message.emit(f"Command error: {str(e)}", "red")
            return False
    
    def read_response(self, timeout=2.0):
        """Read response from serial port"""
        response = ""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if self.serial_port.in_waiting > 0:
                try:
                    data = self.serial_port.read(self.serial_port.in_waiting)
                    response += data.decode('utf-8', errors='ignore')
                    time.sleep(0.1)
                except:
                    pass
            else:
                if response:  # If we've received some data and no more is coming
                    time.sleep(0.1)
                    if self.serial_port.in_waiting == 0:
                        break
                time.sleep(0.05)
        
        return response.strip()
    
    def read_until_prompt(self, prompt_text, timeout=5.0):
        """Read until specific prompt text is found"""
        response = ""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if self.serial_port.in_waiting > 0:
                try:
                    data = self.serial_port.read(self.serial_port.in_waiting)
                    response += data.decode('utf-8', errors='ignore')
                    
                    if prompt_text in response:
                        return response
                    
                    time.sleep(0.1)
                except:
                    pass
            else:
                time.sleep(0.05)
        
        return response if response else None
    
    def verify_confirmation_values(self, confirmation_text, expected_coeffs):
        """Verify that confirmation shows correct coefficient values"""
        try:
            # Extract numbers from confirmation text (both doubles and floats)
            lines = confirmation_text.split('\n')
            values = []
            
            for line in lines:
                # Look for lines like "0 (double): 0.2475990407" or "8 (float): 0.964659"
                match = re.search(r'\d+\s*\((double|float)\):\s*([-\d.]+)', line)
                if match:
                    values.append(float(match.group(2)))
            
            # Should have 14 values total
            # 0-7: HIGH and LOW range coefficients (doubles)
            # 8-11: GLOBAL coefficients (floats)
            # 12-13: Temperature coefficients (floats)
            if len(values) != 14:
                self.log_message.emit(f"[WARNING] Expected 14 values (8 doubles + 6 floats), found {len(values)}", "orange")
                self.log_message.emit(f"Values found: {values}", "gray")
                return False
            
            # Expected values in device order
            expected_values = [
                # 0-3: HIGH RANGE (doubles)
                expected_coeffs['k_high'],
                expected_coeffs['alpha_high'],
                expected_coeffs['eta_high'],
                expected_coeffs['zeta_high'],
                # 4-7: LOW RANGE (doubles)
                expected_coeffs['k_low'],
                expected_coeffs['alpha_low'],
                expected_coeffs['eta_low'],
                expected_coeffs['zeta_low'],
                # 8-11: GLOBAL (floats)
                expected_coeffs['k_global'],
                expected_coeffs['alpha_global'],
                expected_coeffs['eta_global'],
                expected_coeffs['zeta_global'],
                # 12-13: TEMP (floats)
                expected_coeffs['temp_scale'],
                expected_coeffs['temp_offset']
            ]
            
            # Use different tolerances for doubles (0-7) vs floats (8-13)
            for i, (found, expected) in enumerate(zip(values, expected_values)):
                # Floats have lower precision, use larger tolerance
                tolerance = 1e-5 if i >= 8 else 1e-8
                
                if abs(found - expected) > tolerance:
                    self.log_message.emit(
                        f"[ERROR] Value mismatch at index {i}: expected {expected}, found {found}", 
                        "red"
                    )
                    return False
            
            self.log_message.emit("[SUCCESS] All 14 values verified (8 doubles + 6 floats)", "green")
            return True
            
        except Exception as e:
            self.log_message.emit(f"Verification error: {str(e)}", "orange")
            return False
    
    def stop(self):
        """Stop the programming operation"""
        self.running = False

