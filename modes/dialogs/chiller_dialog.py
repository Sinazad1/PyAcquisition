"""
Chiller Control Dialog (within Acquisition Mode)
DYNEO DD-200F (Julabo) chiller control

Doc status: done, MK, 01/30/2026
"""
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
                              QLabel, QPushButton, QLineEdit, QGroupBox, 
                              QTextEdit, QMessageBox)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication

import time

# Import chiller thread from hardware module
from modes.hardware.chiller_handler import ChillerThread

# Import chiller settings from config
try:
    from modes.utils.config import CHILLER_BAUDRATE
except ImportError:
    CHILLER_BAUDRATE = 4800

# Import UI constants
from modes.utils.ui_constants import (COLOR_CHILLER, COLOR_SUCCESS, COLOR_ERROR, COLOR_INFO,
                          COLOR_WARNING, COLOR_TEXT_SECONDARY, COLOR_LOG_BACKGROUND,
                          COLOR_LOG_TEXT, COLOR_BUTTON_NORMAL, COLOR_BUTTON_HOVER,
                          COLOR_DISPLAY_BACKGROUND, COLOR_DISPLAY_VALUE, COLOR_INFO_DARK,
                          COLOR_DISABLED, COLOR_DISABLED_TEXT,
                          FONT_SIZE_NORMAL, FONT_SIZE_MEDIUM, FONT_SIZE_LARGE,
                          FONT_SIZE_XLARGE, FONT_SIZE_DISPLAY, FONT_FAMILY_MONO,
                          PADDING_MEDIUM, PADDING_LARGE, BORDER_RADIUS_SMALL)

class ChillerDialog(QDialog):
    """chiller control dialog"""
    
    def __init__(self, parent=None, port=None):
        """
        Initialize the chiller dialog.
        
        Creates a dialog for configuring and controlling chiller settings including
        temperature setpoint and on/off control.
        
        Args:
            parent (QWidget, optional): Parent widget. Defaults to None.
            port (str, optional): COM port for chiller communication. Defaults to None.
        """
        super().__init__(parent)
        self.parent_window = parent
        self.chiller_thread = None
        self.is_connected = False
        self.is_running = False
        self.port = port
        
        # Default values
        self.current_temperature = 0.0
        self.target_temperature = 25.0
        self.pump_speed = 50  # 50%
        
        # Timer for periodic temperature updates
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.request_temperature_update)
        
        self.init_ui()
        
        # Auto-connect if port provided
        if self.port:
            self.connect_chiller()
        
    def init_ui(self):
        """Initialize simplified user interface"""
        self.setWindowTitle("Chiller Control")
        self.setModal(False)
        self.setMinimumWidth(450)
        self.setMinimumHeight(550)
        
        main_layout = QVBoxLayout()
        
        # Title and status
        title_layout = QVBoxLayout()
        
        title = QLabel("Chiller Control")
        title.setStyleSheet("font-size: 16pt; font-weight: bold; padding: 10px;")
        title.setAlignment(Qt.AlignCenter)
        title_layout.addWidget(title)
        
        subtitle = QLabel("DYNEO DD-200F (Julabo)")
        subtitle.setStyleSheet("color: #666; font-size: 10pt;")
        subtitle.setAlignment(Qt.AlignCenter)
        title_layout.addWidget(subtitle)
        
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
        
        # Current temperature display
        main_layout.addWidget(self._create_temperature_display())
        
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
        
        Calculates position to align dialog to the right side of the parent
        window at a specified vertical position.
        
        Args:
            vertical_fraction (float, optional): Vertical position as fraction
                of screen height (0.0=top, 1.0=bottom). Defaults to 0.25.
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
    
    def _create_temperature_display(self):
        """Create temperature display"""
        group = QGroupBox("Current Temperature")
        layout = QVBoxLayout()
        
        self.temp_display = QLabel("--.-°C")
        self.temp_display.setStyleSheet("""
            QLabel {
                background-color: #2C3E50;
                color: #3498DB;
                font-size: 36pt;
                font-weight: bold;
                padding: 20px;
                border-radius: 5px;
                font-family: 'Arial', sans-serif;
            }
        """)
        self.temp_display.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.temp_display)
        
        group.setLayout(layout)
        return group
    
    def _create_parameters_section(self):
        """Create parameter input section"""
        group = QGroupBox("Chiller Parameters")
        layout = QGridLayout()
        
        # Target temperature
        layout.addWidget(QLabel("Target Temperature (°C):"), 0, 0)
        self.temp_input = QLineEdit(f"{self.target_temperature:.2f}")
        self.temp_input.setStyleSheet("padding: 5px; font-size: 10pt;")
        layout.addWidget(self.temp_input, 0, 1)
        
        set_temp_button = QPushButton("Set")
        set_temp_button.setStyleSheet("""
            QPushButton {
                background-color: #3498DB;
                color: white;
                padding: 5px 15px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #2980B9;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        set_temp_button.clicked.connect(self.set_temperature)
        layout.addWidget(set_temp_button, 0, 2)
        
        # Pump speed
        layout.addWidget(QLabel("Pump Speed (%):"), 1, 0)
        self.speed_input = QLineEdit(str(self.pump_speed))
        self.speed_input.setStyleSheet("padding: 5px; font-size: 10pt;")
        layout.addWidget(self.speed_input, 1, 1)
        
        set_speed_button = QPushButton("Set")
        set_speed_button.setStyleSheet("""
            QPushButton {
                background-color: #3498DB;
                color: white;
                padding: 5px 15px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #2980B9;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        set_speed_button.clicked.connect(self.set_pump_speed)
        layout.addWidget(set_speed_button, 1, 2)
        
        group.setLayout(layout)
        return group
    
    def _create_control_buttons(self):
        """Create control buttons"""
        group = QGroupBox("Chiller Control")
        layout = QHBoxLayout()
        
        # START button
        self.start_button = QPushButton("START")
        self.start_button.setEnabled(False)
        self.start_button.setStyleSheet("""
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
        self.start_button.clicked.connect(self.start_chiller)
        layout.addWidget(self.start_button)
        
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
        self.stop_button.clicked.connect(self.stop_chiller)
        layout.addWidget(self.stop_button)
        
        group.setLayout(layout)
        return group
    
    def connect_chiller(self):
        """Connect to chiller"""
        if not self.port:
            QMessageBox.warning(self, "No Port", "No port specified for chiller.")
            return
        
        # Log to main window
        if self.parent_window and hasattr(self.parent_window, 'log_event'):
            self.parent_window.log_event(
                f"Connecting to chiller on {self.port}...",
                color=COLOR_CHILLER,
                log_type="CHILLER"
            )
        
        # Create and start chiller thread
        self.chiller_thread = ChillerThread(self.port, baudrate=CHILLER_BAUDRATE)
        self.chiller_thread.temperature_received.connect(self.handle_temperature)
        self.chiller_thread.status_received.connect(self.handle_status)
        self.chiller_thread.setpoint_confirmed.connect(self.handle_setpoint_confirmed)
        self.chiller_thread.pump_speed_confirmed.connect(self.handle_pump_speed_confirmed)
        self.chiller_thread.error_occurred.connect(self.handle_error)
        self.chiller_thread.connection_status.connect(self.handle_connection_status)
        self.chiller_thread.command_log.connect(self.handle_command_log)
        self.chiller_thread.start()
    
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
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(True)
            
            # Start periodic temperature updates (every 2 seconds)
            self.update_timer.start(2000)
            
            # Log to main window if available
            if self.parent_window and hasattr(self.parent_window, 'log_event'):
                self.parent_window.log_event(
                    f"Chiller connected: {self.port}",
                    color=COLOR_SUCCESS,
                    log_type="CHILLER"
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
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            
            # Log to main window
            if self.parent_window and hasattr(self.parent_window, 'log_event'):
                self.parent_window.log_event(
                    f"Chiller connection failed: {message}",
                    color=COLOR_ERROR,
                    log_type="CHILLER"
                )
    
    def handle_temperature(self, temperature):
        """Handle temperature updates"""
        self.current_temperature = temperature
        self.temp_display.setText(f"{temperature:.2f}°C")
    
    def handle_status(self, running):
        """Handle chiller running status"""
        self.is_running = running
        # Log to main window
        if self.parent_window and hasattr(self.parent_window, 'log_event'):
            if running:
                self.parent_window.log_event(
                    "Chiller STARTED",
                    color=COLOR_SUCCESS,
                    log_type="CHILLER"
                )
            else:
                self.parent_window.log_event(
                    "Chiller STOPPED",
                    color=COLOR_INFO,
                    log_type="CHILLER"
                )
    
    def handle_setpoint_confirmed(self, temperature):
        """Handle setpoint confirmation"""
        # Log to main window
        if self.parent_window and hasattr(self.parent_window, 'log_event'):
            self.parent_window.log_event(
                f"Chiller setpoint confirmed: {temperature:.2f}°C",
                color=COLOR_INFO,
                log_type="CHILLER"
            )
    
    def handle_pump_speed_confirmed(self, speed):
        """Handle pump speed confirmation"""
        # Log to main window
        if self.parent_window and hasattr(self.parent_window, 'log_event'):
            self.parent_window.log_event(
                f"Chiller pump speed confirmed: {speed}%",
                color=COLOR_INFO,
                log_type="CHILLER"
            )
    
    def handle_error(self, error):
        """Handle errors from chiller"""
        # Log to main window if available
        if self.parent_window and hasattr(self.parent_window, 'log_event'):
            self.parent_window.log_event(
                f"Chiller error: {error}",
                color=COLOR_ERROR,
                log_type="CHILLER-ERROR"
            )
    
    def handle_command_log(self, command, response):
        """Handle command/response logging"""
        # Log to parent window with TX/RX format
        if self.parent_window and hasattr(self.parent_window, 'log_event'):
            self.parent_window.log_event(
                f"CHILLER {command} | {response}",
                color=COLOR_CHILLER,
                log_type="CHILLER-SERIAL"
            )
    
    def request_temperature_update(self):
        """Request temperature update from chiller"""
        if self.chiller_thread and self.is_connected:
            self.chiller_thread.query_status()
    
    def set_temperature(self):
        """Set target temperature"""
        if not self.is_connected or not self.chiller_thread:
            return
        
        try:
            temp = float(self.temp_input.text())
            
            # Validate reasonable range
            if temp < 0 or temp > 80:
                QMessageBox.warning(self, "Invalid Temperature", 
                                  "Temperature must be between 0°C and 80°C.")
                return
            
            self.chiller_thread.set_temperature(temp)
            self.target_temperature = temp
            
            # Log to main window
            if self.parent_window and hasattr(self.parent_window, 'log_event'):
                self.parent_window.log_event(
                    f"Chiller setpoint: {temp:.2f}°C",
                    color=COLOR_INFO,
                    log_type="CHILLER"
                )
            
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Please enter a valid temperature.")
    
    def set_pump_speed(self):
        """Set pump speed"""
        if not self.is_connected or not self.chiller_thread:
            return
        
        try:
            speed = int(self.speed_input.text())
            
            # Validate range
            if speed < 0 or speed > 100:
                QMessageBox.warning(self, "Invalid Speed", 
                                  "Pump speed must be between 0% and 100%.")
                return
            
            self.chiller_thread.set_pump_speed(speed)
            self.pump_speed = speed
            
            # Log to main window
            if self.parent_window and hasattr(self.parent_window, 'log_event'):
                self.parent_window.log_event(
                    f"Chiller pump speed: {speed}%",
                    color=COLOR_INFO,
                    log_type="CHILLER"
                )
            
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Please enter a valid speed percentage.")
    
    def start_chiller(self):
        """Start the chiller"""
        if not self.is_connected or not self.chiller_thread:
            return
        
        success = self.chiller_thread.start_chiller()
        
        if success:
            # Log to main window
            if self.parent_window and hasattr(self.parent_window, 'log_event'):
                self.parent_window.log_event(
                    "Chiller STARTED",
                    color=COLOR_SUCCESS,
                    log_type="CHILLER"
                )
    
    def stop_chiller(self):
        """Stop the chiller"""
        if not self.is_connected or not self.chiller_thread:
            return
        
        success = self.chiller_thread.stop_chiller()
        
        if success:
            # Log to main window
            if self.parent_window and hasattr(self.parent_window, 'log_event'):
                self.parent_window.log_event(
                    "Chiller STOPPED",
                    color=COLOR_ERROR,
                    log_type="CHILLER"
                )
    
    def closeEvent(self, event):
        """Handle dialog close"""
        # Stop update timer
        self.update_timer.stop()
        
        # Stop thread
        if self.chiller_thread:
            self.chiller_thread.stop()
            
            # Wait for thread to finish
            if self.chiller_thread.isRunning():
                self.chiller_thread.wait(2000)
            
            # Clear the reference
            self.chiller_thread = None
            self.is_connected = False
        
        event.accept()
