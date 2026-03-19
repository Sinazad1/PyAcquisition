"""
Syringe Pump Control Dialog  (within Acquisition Mode)

Doc status: done, MK, 01/30/2026
Patch in for pump rate units, MK 02/03/2026
"""
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
                              QLabel, QPushButton, QLineEdit, QGroupBox, 
                              QTextEdit, QMessageBox)
from PySide6.QtCore import Qt
import time
from PySide6.QtGui import QGuiApplication

# Import pump thread from hardware module
from modes.hardware.syringe_pump_handler import SyringePumpThread

# Import pump settings from config
try:
    from modes.utils.config import PUMP_BAUDRATE, PUMP_RATE_UNITS
except ImportError:
    PUMP_BAUDRATE = 19200
    PUMP_RATE_UNITS = 'MM'  # rate now per config, Default to mL/min

# Import UI constants
from modes.utils.ui_constants import COLOR_PUMP

class SyringePumpDialog(QDialog):
    """Simplified syringe pump control dialog"""
    
    def __init__(self, parent=None, port=None):
        """
        Initialize the syringe pump dialog.
        
        Creates a dialog for controlling syringe pump operations including
        infusion/withdrawal rates, direction, and volume settings.
        
        Args:
            parent (QWidget, optional): Parent widget. Defaults to None.
            port (str, optional): COM port for syringe pump communication. Defaults to None.
        """
        super().__init__(parent)
        self.parent_window = parent
        self.pump_thread = None
        self.is_connected = False
        self.port = port
        
        # Patch in for rates - MK, 02/03/2026; Rate units configuration from config.ini
        self.rate_units = PUMP_RATE_UNITS
        
        # Map rate unit codes to display labels
        self.rate_units_map = {
            'MM': 'mL/min',
            'MH': 'mL/hr',
            'UM': 'µL/min',
            'UH': 'µL/hr'
        }
        
        # Default values
        self.current_diameter = "29.5"  # mm for 60mL syringe
        self.current_rate = "10.0"  # rate value
        self.current_volume = "5.0"  # mL
        self.current_direction = "INF"  # Infuse
        
        self.init_ui()
        
        # Auto-connect if port provided
        if self.port:
            self.connect_pump()
        
    def init_ui(self):
        """Initialize UI"""
        self.setWindowTitle("Syringe Pump Control")
        self.setModal(False)
        self.setMinimumWidth(450)
        self.setMinimumHeight(500)
        
        main_layout = QVBoxLayout()
        
        # Title and status
        title_layout = QVBoxLayout()
        
        title = QLabel("Syringe Pump")
        title.setStyleSheet("font-size: 16pt; font-weight: bold; padding: 10px;")
        title.setAlignment(Qt.AlignCenter)
        title_layout.addWidget(title)
        
        self.status_label = QLabel("Connecting..." if self.port else "Not Connected")
        self.status_label.setStyleSheet("""
            QLabel {
                background-color: #FFA500;
                color: black;
                padding: 8px;
                font-weight: bold;
                font-size: 12pt;
                border-radius: 3px;
            }
        """)
        self.status_label.setAlignment(Qt.AlignCenter)
        title_layout.addWidget(self.status_label)
        
        if self.port:
            port_label = QLabel(f"Port: {self.port}")
            port_label.setStyleSheet("color: #666; font-size: 10pt; padding: 5px;")
            port_label.setAlignment(Qt.AlignCenter)
            title_layout.addWidget(port_label)
        
        main_layout.addLayout(title_layout)
        
        # Parameters
        main_layout.addWidget(self._create_parameters_section())
        
        # Control buttons
        main_layout.addWidget(self._create_control_buttons())
        
        # Close button
        close_layout = QHBoxLayout()
        close_layout.addStretch()
        close_button = QPushButton("Close")
        close_button.setStyleSheet("""
            QPushButton {
                background-color: #666;
                color: white;
                padding: 10px 30px;
                font-size: 11pt;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #555;
            }
        """)
        close_button.clicked.connect(self.close)
        close_layout.addWidget(close_button)
        close_layout.addStretch()
        main_layout.addLayout(close_layout)
        
        self.setLayout(main_layout)
        self.position_aligned_right_offset(0.225)

    def position_aligned_right_offset(self, vertical_fraction=0.25):
        """
        Position dialog aligned to the right with vertical offset.
        
        Args:
            vertical_fraction (float, optional): Vertical position as fraction
                of screen height. Defaults to 0.25.
        """
        # ensure we have a real size
        self.adjustSize()
        dlg = self.frameGeometry()

        parent = self.parent()
        if not parent:
            return

        parent_geom = parent.frameGeometry()
        screen = QGuiApplication.screenAt(parent_geom.center()) or QGuiApplication.primaryScreen()
        screen_geom = screen.availableGeometry()

        # Right-align dialog with parent's right edge
        x = parent_geom.right() - dlg.width() + 1

        # Top = parent top + 1/4 parent height
        y = parent_geom.top() + int(parent_geom.height() * vertical_fraction)

        # Clamp to screen
        x = max(screen_geom.left(), min(x, screen_geom.right() - dlg.width()))
        y = max(screen_geom.top(),  min(y, screen_geom.bottom() - dlg.height()))
        self.move(x, y)
   
    def _create_parameters_section(self):
        """Create parameter input section"""
        group = QGroupBox("Pump Parameters")
        layout = QGridLayout()
        
        # Direction
        layout.addWidget(QLabel("Direction:"), 0, 0)
        self.dir_inf_button = QPushButton("Infuse")
        self.dir_wdr_button = QPushButton("Withdraw")
        self.dir_inf_button.setCheckable(True)
        self.dir_wdr_button.setCheckable(True)
        self.dir_inf_button.setChecked(True)
        
        button_style = """
            QPushButton {
                padding: 8px;
                font-size: 10pt;
                border: 2px solid #ccc;
                border-radius: 3px;
            }
            QPushButton:checked {
                background-color: #4CAF50;
                color: white;
                border-color: #4CAF50;
            }
        """
        self.dir_inf_button.setStyleSheet(button_style)
        self.dir_wdr_button.setStyleSheet(button_style)
        
        self.dir_inf_button.clicked.connect(lambda: self._set_direction("INF"))
        self.dir_wdr_button.clicked.connect(lambda: self._set_direction("WDR"))
        
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(self.dir_inf_button)
        dir_layout.addWidget(self.dir_wdr_button)
        layout.addLayout(dir_layout, 0, 1)
        
        # Diameter
        layout.addWidget(QLabel("Syringe Diameter (mm):"), 1, 0)
        self.diameter_input = QLineEdit(self.current_diameter)
        self.diameter_input.setStyleSheet("padding: 5px; font-size: 10pt;")
        layout.addWidget(self.diameter_input, 1, 1)
        
        # Rate
        rate_units_display = self.rate_units_map.get(self.rate_units, self.rate_units)
        layout.addWidget(QLabel(f"Rate ({rate_units_display}):"), 2, 0)
        self.rate_input = QLineEdit(self.current_rate)
        self.rate_input.setStyleSheet("padding: 5px; font-size: 10pt;")
        layout.addWidget(self.rate_input, 2, 1)
        
        # Volume
        layout.addWidget(QLabel("Volume (mL):"), 3, 0)
        self.volume_input = QLineEdit(self.current_volume)
        self.volume_input.setStyleSheet("padding: 5px; font-size: 10pt;")
        layout.addWidget(self.volume_input, 3, 1)
        
        group.setLayout(layout)
        return group
    
    def _create_control_buttons(self):
        """Create control buttons"""
        group = QGroupBox("Pump Control")
        layout = QHBoxLayout()
        
        # RUN button
        self.run_button = QPushButton("RUN")
        self.run_button.setEnabled(False)
        self.run_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 15px 30px;
                font-size: 14pt;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666;
            }
        """)
        self.run_button.clicked.connect(self.run_pump)
        layout.addWidget(self.run_button)
        
        # STOP button
        self.stop_button = QPushButton("STOP")
        self.stop_button.setEnabled(False)
        self.stop_button.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                padding: 15px 30px;
                font-size: 14pt;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666;
            }
        """)
        self.stop_button.clicked.connect(self.stop_pump)
        layout.addWidget(self.stop_button)
        
        group.setLayout(layout)
        return group
    
    def _set_direction(self, direction):
        """Set pump direction"""
        self.current_direction = direction
        if direction == "INF":
            self.dir_inf_button.setChecked(True)
            self.dir_wdr_button.setChecked(False)
        else:
            self.dir_inf_button.setChecked(False)
            self.dir_wdr_button.setChecked(True)
    
    def connect_pump(self):
        """Connect to syringe pump"""
        if not self.port:
            QMessageBox.warning(self, "No Port", "No port specified for syringe pump.")
            return
        
        # Log to main window
        if self.parent_window and hasattr(self.parent_window, 'log_event'):
            self.parent_window.log_event(
                f"Connecting to pump on {self.port}...",
                color=COLOR_PUMP,
                log_type="PUMP"
            )
        
        # Create and start pump thread
        self.pump_thread = SyringePumpThread(self.port, baudrate=PUMP_BAUDRATE)
        self.pump_thread.message_received.connect(self.handle_message)
        self.pump_thread.error_occurred.connect(self.handle_error)
        self.pump_thread.connection_status.connect(self.handle_connection_status)
        self.pump_thread.command_log.connect(self.handle_command_log)
        self.pump_thread.start()
    
    def handle_connection_status(self, connected, message):
        """Handle connection status updates"""
        self.is_connected = connected
        
        if connected:
            self.status_label.setText("Connected")
            self.status_label.setStyleSheet("""
                QLabel {
                    background-color: #4CAF50;
                    color: white;
                    padding: 8px;
                    font-weight: bold;
                    font-size: 12pt;
                    border-radius: 3px;
                }
            """)
            self.run_button.setEnabled(True)
            self.stop_button.setEnabled(True)
            
            # Log to main window if available
            if self.parent_window and hasattr(self.parent_window, 'log_event'):
                self.parent_window.log_event(
                    f"Syringe pump connected: {self.port}",
                    color="#4CAF50",
                    log_type="PUMP"
                )
        else:
            self.status_label.setText("Connection Failed")
            self.status_label.setStyleSheet("""
                QLabel {
                    background-color: #f44336;
                    color: white;
                    padding: 8px;
                    font-weight: bold;
                    font-size: 12pt;
                    border-radius: 3px;
                }
            """)
            self.run_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            
            # Log to main window
            if self.parent_window and hasattr(self.parent_window, 'log_event'):
                self.parent_window.log_event(
                    f"Pump connection failed: {message}",
                    color="#f44336",
                    log_type="PUMP"
                )
    
    def handle_message(self, message):
        """Handle messages from pump"""
        # Only log significant messages to main window
        if message and self.parent_window and hasattr(self.parent_window, 'log_event'):
            self.parent_window.log_event(
                f"Pump: {message}",
                color=COLOR_PUMP,
                log_type="PUMP"
            )
    
    def handle_error(self, error):
        """Handle errors from pump"""
        # Log to main window if available
        if self.parent_window and hasattr(self.parent_window, 'log_event'):
            self.parent_window.log_event(
                f"Syringe pump error: {error}",
                color="#f44336",
                log_type="PUMP-ERROR"
            )
    
    def handle_command_log(self, command, response):
        """Handle command/response logging"""
        # Log to parent window with TX/RX format
        if self.parent_window and hasattr(self.parent_window, 'log_event'):
            self.parent_window.log_event(
                f"PUMP {command} | {response}",
                color=COLOR_PUMP,
                log_type="PUMP-SERIAL"
            )
    
    def run_pump(self):
        """Run the pump with current parameters"""
        if not self.is_connected or not self.pump_thread:
            return
        
        try:
            # Get parameters
            diameter = self.diameter_input.text()
            rate = self.rate_input.text()
            volume = self.volume_input.text()
            direction = self.current_direction
            
            # Validate
            float(diameter)
            float(rate)
            float(volume)
            
            self.pump_thread.send_command(f"DIA {diameter}")
            time.sleep(0.1)
            
            self.pump_thread.send_command(f"DIR {direction}")
            time.sleep(0.1)
            
            self.pump_thread.send_command(f"RAT {rate} {self.rate_units}")
            time.sleep(0.1)
            
            self.pump_thread.send_command(f"VOL {volume}")
            time.sleep(0.1)
            
            self.pump_thread.send_command("RUN")
            
            # Log to main window with correct units
            rate_units_display = self.rate_units_map.get(self.rate_units, self.rate_units)
            if self.parent_window and hasattr(self.parent_window, 'log_event'):
                self.parent_window.log_event(
                    f"Pump RUN: {direction} {volume}mL @ {rate}{rate_units_display}",
                    color="#4CAF50",
                    log_type="PUMP"
                )
            
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Please enter valid numeric values.")
        except Exception as e:
            # Log error to main window
            if self.parent_window and hasattr(self.parent_window, 'log_event'):
                self.parent_window.log_event(
                    f"Pump error: {str(e)}",
                    color="#f44336",
                    log_type="PUMP-ERROR"
                )
    
    def stop_pump(self):
        """Stop the pump"""
        if not self.is_connected or not self.pump_thread:
            return
        
        self.pump_thread.send_command("STP")
        
        # Log to main window
        if self.parent_window and hasattr(self.parent_window, 'log_event'):
            self.parent_window.log_event(
                "Pump STOPPED",
                color="#f44336",
                log_type="PUMP"
            )
    
    def closeEvent(self, event):
        """Handle dialog close"""
        if self.pump_thread:
            # Don't send STP command - let the pump continue running
            # Just cleanly disconnect from the serial port
            
            # Stop the thread (this will close the serial port internally)
            self.pump_thread.stop()
            
            # Wait for thread to finish
            if self.pump_thread.isRunning():
                self.pump_thread.wait(2000)
            
            # Clear the reference
            self.pump_thread = None
            self.is_connected = False
        
        event.accept()
