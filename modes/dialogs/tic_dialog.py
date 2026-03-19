"""
Tic Controller Dialog (within Acquisition Mode)
Control interface for Pololu Tic 36v4 stepper motor controller
Uses ticcmd subprocess calls
Supports dual TICs with selector

Doc status: done, MK, 01/30/2026
"""
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
                              QLabel, QPushButton, QLineEdit, QGroupBox, 
                              QTextEdit, QMessageBox, QSlider, QComboBox)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication

import time
import threading

# Import Tic handler from hardware module
from modes.hardware.tic_handler import TicThread, check_ticcmd_installed

# Import UI constants
from modes.utils.ui_constants import COLOR_TIC

class TicDialog(QDialog):
    """Tic stepper motor controller dialog with dual TIC support"""
    
    def __init__(self, parent=None, serial_number_a=None, serial_number_b=None):
        """
        Initialize the TIC stepper controller dialog.
        
        Creates a dialog for controlling dual TIC stepper motor position, homing,
        and movement settings for TIC A and TIC B controllers.
        
        Args:
            parent (QWidget, optional): Parent widget. Defaults to None.
            serial_number_a (str, optional): Serial number of TIC A device. Defaults to None.
            serial_number_b (str, optional): Serial number of TIC B device. Defaults to None.
        """
        super().__init__(parent)
        self.parent_window = parent
        
        # TIC A and B configurations
        self.tic_threads = {'A': None, 'B': None}
        self.is_connected = {'A': False, 'B': False}
        self.is_energized = {'A': False, 'B': False}
        self.serial_numbers = {
            'A': serial_number_a,
            'B': serial_number_b
        }
        
        # Current status for each TIC
        self.current_position = {'A': 0, 'B': 0}
        self.current_velocity = {'A': 0, 'B': 0}
        self.target_velocity = {'A': 0, 'B': 0}
        self.vin_voltage = {'A': 0.0, 'B': 0.0}
        
        # Currently selected TIC
        self.selected_tic = 'A'
        
        # Timer for periodic status updates
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.request_status_update)
        self._is_closing = False
        self._status_poll_inflight = {'A': False, 'B': False}
        
        self.init_ui()
        
        # Check if ticcmd is installed
        installed, version = check_ticcmd_installed()
        if not installed:
            QMessageBox.critical(
                self,
                "ticcmd Not Found",
                "ticcmd utility not found.\n\n"
                "Please install Pololu Tic software:\n"
                "pololu-tic-1.8.2-win.msi\n\n"
                "Download from: https://www.pololu.com/tic/software"
            )
            # Log to main window
            if self.parent_window and hasattr(self.parent_window, 'log_event'):
                self.parent_window.log_event(
                    "ERROR: ticcmd not installed",
                    color="#f44336",
                    log_type="TIC-ERROR"
                )
        else:
            # Log to main window
            if self.parent_window and hasattr(self.parent_window, 'log_event'):
                self.parent_window.log_event(
                    f"ticcmd found: {version}",
                    color="#4CAF50",
                    log_type="TIC"
                )
            
            # Auto-connect both TICs if serial numbers provided
            if self.serial_numbers['A']:
                self.connect_tic('A')
            if self.serial_numbers['B']:
                self.connect_tic('B')
        
    def init_ui(self):
        """Initialize user interface"""
        self.setWindowTitle("Tic Controller")
        self.setModal(False)
        self.setMinimumWidth(450)
        self.setMinimumHeight(600)
        
        main_layout = QVBoxLayout()
        
        # Title
        title_layout = QVBoxLayout()
        
        title = QLabel("Tic Stepper Controller")
        title.setStyleSheet("font-size: 16pt; font-weight: bold; padding: 10px;")
        title.setAlignment(Qt.AlignCenter)
        title_layout.addWidget(title)
        
        subtitle = QLabel("Pololu Tic 36v4")
        subtitle.setStyleSheet("color: #666; font-size: 10pt;")
        subtitle.setAlignment(Qt.AlignCenter)
        #title_layout.addWidget(subtitle)
        
        main_layout.addLayout(title_layout)
        
        # TIC Selector
        selector_layout = QHBoxLayout()
        selector_layout.addStretch()
        
        selector_label = QLabel("Select TIC:")
        selector_label.setStyleSheet("font-size: 11pt; font-weight: bold;")
        selector_layout.addWidget(selector_label)
        
        self.tic_selector = QComboBox()
        # Format items with serial numbers if available
        tic_a_display = f"TIC A - {self.serial_numbers['A']}" if self.serial_numbers['A'] else "TIC A (Not Configured)"
        tic_b_display = f"TIC B - {self.serial_numbers['B']}" if self.serial_numbers['B'] else "TIC B (Not Configured)"
        self.tic_selector.addItems([tic_a_display, tic_b_display])
        self.tic_selector.setStyleSheet("""
            QComboBox {
                padding: 5px 15px;
                font-size: 11pt;
                font-weight: bold;
                border: 2px solid #3498DB;
                border-radius: 3px;
                background-color: white;
                color: black;
                min-width: 200px;
            }
            QComboBox:hover {
                border-color: #2980B9;
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
        self.tic_selector.currentIndexChanged.connect(self.on_tic_selector_changed)
        selector_layout.addWidget(self.tic_selector)
        
        selector_layout.addStretch()
        main_layout.addLayout(selector_layout)
        
        # Status indicator and serial number
        status_layout = QVBoxLayout()
        
        self.status_label = QLabel("Connecting..." if self.serial_numbers['A'] else "Not Connected")
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
        status_layout.addWidget(self.status_label)
        
        self.serial_label = QLabel(self._get_serial_display())
        self.serial_label.setStyleSheet("color: #666; font-size: 10pt; padding: 5px;")
        self.serial_label.setAlignment(Qt.AlignCenter)
        status_layout.addWidget(self.serial_label)
        
        main_layout.addLayout(status_layout)
        
        # Status display
        main_layout.addWidget(self._create_status_display())
        
        # Velocity control
        main_layout.addWidget(self._create_velocity_control())
        
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
      
    def _get_serial_display(self):
        """Get serial number display string"""
        tic = self.selected_tic
        serial = self.serial_numbers[tic]
        if serial:
            return f"TIC {tic} Serial: {serial}"
        else:
            return f"TIC {tic}: No serial configured"
    
    def on_tic_selector_changed(self, index):
        """Handle TIC selector change"""
        self.selected_tic = 'A' if index == 0 else 'B'
        
        # Log to parent window
        if self.parent_window and hasattr(self.parent_window, 'log_event'):
            self.parent_window.log_event(
                f"Switched to TIC {self.selected_tic}",
                color="#3498DB",
                log_type="TIC"
            )
        
        # Update displays - force velocity update when switching TICs
        self.update_display_for_selected_tic(force_velocity_update=True)
    
    def update_display_for_selected_tic(self, force_velocity_update=False):
        """Update all displays for the currently selected TIC
        
        Args:
            force_velocity_update: If True, always update velocity input/slider (used when switching TICs)
        """
        tic = self.selected_tic
        
        # Update serial label
        self.serial_label.setText(self._get_serial_display())
        
        # Update connection status
        if self.is_connected[tic]:
            self.status_label.setText(f"TIC {tic} Connected")
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
            self.stop_button.setEnabled(True)
            self.energize_button.setEnabled(True)
            self.deenergize_button.setEnabled(True)
        else:
            self.status_label.setText(f"TIC {tic} Not Connected")
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
            self.stop_button.setEnabled(False)
            self.energize_button.setEnabled(False)
            self.deenergize_button.setEnabled(False)
        
        # Update status values
        self.position_label.setText(str(self.current_position[tic]))
        self.current_vel_label.setText(str(self.current_velocity[tic]))
        self.voltage_label.setText(f"{self.vin_voltage[tic]:.2f} V")
        
        if self.is_energized[tic]:
            self.energized_label.setText("Energized")
            self.energized_label.setStyleSheet("font-size: 11pt; color: #27AE60;")
        else:
            self.energized_label.setText("De-energized")
            self.energized_label.setStyleSheet("font-size: 11pt; color: #E67E22;")
        
        # Update velocity input/slider intelligently
        # Always update if forced (e.g., when switching TICs)
        # Otherwise, only update if input doesn't have focus (user not typing)
        should_update = force_velocity_update or not self.velocity_input.hasFocus()
        
        if should_update:
            # Only update if the value actually changed to avoid cursor jumping
            current_text = self.velocity_input.text()
            target_text = str(self.target_velocity[tic])
            if current_text != target_text:
                self.velocity_input.setText(target_text)
                self.velocity_slider.blockSignals(True)  # Prevent triggering slider_velocity_changed
                self.velocity_slider.setValue(self.target_velocity[tic])
                self.velocity_slider.blockSignals(False)
    
    def _create_status_display(self):
        """Create status information display"""
        group = QGroupBox("Motor Status")
        layout = QGridLayout()
        
        # Position
        layout.addWidget(QLabel("Position:"), 0, 0)
        self.position_label = QLabel("0")
        self.position_label.setStyleSheet("font-size: 14pt; font-weight: bold; color: #3498DB;")
        layout.addWidget(self.position_label, 0, 1)
        layout.addWidget(QLabel("steps"), 0, 2)
        
        # Current velocity
        layout.addWidget(QLabel("Current Velocity:"), 1, 0)
        self.current_vel_label = QLabel("0")
        self.current_vel_label.setStyleSheet("font-size: 14pt; font-weight: bold; color: #2ECC71;")
        layout.addWidget(self.current_vel_label, 1, 1)
        layout.addWidget(QLabel("steps/10000s"), 1, 2)
        
        # VIN voltage
        layout.addWidget(QLabel("VIN Voltage:"), 2, 0)
        self.voltage_label = QLabel("0.00 V")
        self.voltage_label.setStyleSheet("font-size: 12pt; color: #E74C3C;")
        layout.addWidget(self.voltage_label, 2, 1, 1, 2)
        
        # Energized status
        layout.addWidget(QLabel("Motor:"), 3, 0)
        self.energized_label = QLabel("De-energized")
        self.energized_label.setStyleSheet("font-size: 11pt; color: #E67E22;")
        layout.addWidget(self.energized_label, 3, 1, 1, 2)
        
        group.setLayout(layout)
        return group
    
    def _create_velocity_control(self):
        """Create velocity control section"""
        group = QGroupBox("Velocity Control")
        layout = QVBoxLayout()
        
        # Velocity input
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("Target Velocity:"))
        
        self.velocity_input = QLineEdit("0")
        self.velocity_input.setStyleSheet("padding: 5px; font-size: 11pt;")
        self.velocity_input.setMaximumWidth(100)
        input_layout.addWidget(self.velocity_input)
        
        input_layout.addWidget(QLabel("steps/10000s"))
        
        set_vel_button = QPushButton("Set")
        set_vel_button.setStyleSheet("""
            QPushButton {
                background-color: #3498DB;
                color: white;
                padding: 5px 20px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #2980B9;
            }
        """)
        set_vel_button.clicked.connect(self.set_velocity_from_input)
        input_layout.addWidget(set_vel_button)
        
        input_layout.addStretch()
        layout.addLayout(input_layout)
        
        # Velocity slider
        slider_layout = QVBoxLayout()
        slider_label = QLabel("Quick Velocity Adjustment")
        slider_label.setStyleSheet("color: #666; font-size: 9pt;")
        slider_layout.addWidget(slider_label)
        
        self.velocity_slider = QSlider(Qt.Horizontal)
        self.velocity_slider.setMinimum(-2000000)
        self.velocity_slider.setMaximum(2000000)
        self.velocity_slider.setValue(0)
        self.velocity_slider.setTickPosition(QSlider.TicksBelow)
        self.velocity_slider.setTickInterval(500000)
        self.velocity_slider.valueChanged.connect(self.slider_velocity_changed)
        slider_layout.addWidget(self.velocity_slider)
        
        # Slider labels
        slider_labels = QHBoxLayout()
        slider_labels.addWidget(QLabel("-2M"))
        slider_labels.addStretch()
        slider_labels.addWidget(QLabel("0"))
        slider_labels.addStretch()
        slider_labels.addWidget(QLabel("+2M"))
        slider_layout.addLayout(slider_labels)
        
        # layout.addLayout(slider_layout)
        
        group.setLayout(layout)
        return group
    
    def _create_control_buttons(self):
        """Create control buttons section"""
        group = QGroupBox("Motor Control")
        layout = QVBoxLayout()
        
        # Row 1: Stop and Energize
        row1 = QHBoxLayout()
        
        self.stop_button = QPushButton("STOP (0 Velocity)")
        self.stop_button.setStyleSheet("""
            QPushButton {
                background-color: #E74C3C;
                color: white;
                padding: 15px;
                font-size: 12pt;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #C0392B;
            }
            QPushButton:disabled {
                background-color: #95A5A6;
            }
        """)
        self.stop_button.clicked.connect(self.stop_motor)
        self.stop_button.setEnabled(False)
        row1.addWidget(self.stop_button)
        
        layout.addLayout(row1)
        
        # Row 2: Energize and De-energize
        row2 = QHBoxLayout()
        
        self.energize_button = QPushButton("Energize Motor")
        self.energize_button.setStyleSheet("""
            QPushButton {
                background-color: #27AE60;
                color: white;
                padding: 10px;
                font-size: 11pt;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #229954;
            }
            QPushButton:disabled {
                background-color: #95A5A6;
            }
        """)
        self.energize_button.clicked.connect(self.energize_motor)
        self.energize_button.setEnabled(False)
        row2.addWidget(self.energize_button)
        
        self.deenergize_button = QPushButton("De-energize Motor")
        self.deenergize_button.setStyleSheet("""
            QPushButton {
                background-color: #E67E22;
                color: white;
                padding: 10px;
                font-size: 11pt;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #CA6F1E;
            }
            QPushButton:disabled {
                background-color: #95A5A6;
            }
        """)
        self.deenergize_button.clicked.connect(self.deenergize_motor)
        self.deenergize_button.setEnabled(False)
        row2.addWidget(self.deenergize_button)
        
        layout.addLayout(row2)
        
        group.setLayout(layout)
        return group
    
    def connect_tic(self, tic_id):
        """Connect to a TIC controller"""
        serial_number = self.serial_numbers[tic_id]
        
        if not serial_number:
            # Log error to parent window
            if self.parent_window and hasattr(self.parent_window, 'log_event'):
                self.parent_window.log_event(
                    f"ERROR: No serial number configured for TIC {tic_id}",
                    color="#f44336",
                    log_type=f"TIC-{tic_id}-ERROR"
                )
            return
        
        # Log connection attempt to parent window
        if self.parent_window and hasattr(self.parent_window, 'log_event'):
            self.parent_window.log_event(
                f"Connecting to TIC {tic_id} ({serial_number})...",
                color="#FFA500",
                log_type=f"TIC-{tic_id}"
            )
        
        # Create and start thread
        self.tic_threads[tic_id] = TicThread(serial_number)
        
        # Connect signals
        self.tic_threads[tic_id].status_received.connect(
            lambda status, tid=tic_id: self.handle_status(tid, status)
        )
        self.tic_threads[tic_id].velocity_confirmed.connect(
            lambda vel, tid=tic_id: self.handle_velocity_confirmed(tid, vel)
        )
        self.tic_threads[tic_id].position_received.connect(
            lambda pos, tid=tic_id: self.handle_position(tid, pos)
        )
        self.tic_threads[tic_id].error_occurred.connect(
            lambda err, tid=tic_id: self.handle_error(tid, err)
        )
        self.tic_threads[tic_id].connection_status.connect(
            lambda status, msg, tid=tic_id: self.handle_connection_status(tid, status, msg)
        )
        self.tic_threads[tic_id].command_log.connect(
            lambda cmd, resp, tid=tic_id: self.handle_command_log(tid, cmd, resp)
        )
        
        self.tic_threads[tic_id].start()
        
        # Start update timer if not already running
        if not self.update_timer.isActive():
            # Keep polling moderate because each status query is a subprocess call.
            self.update_timer.start(1500)
    
    def handle_connection_status(self, tic_id, connected, message):
        """Handle connection status updates"""
        self.is_connected[tic_id] = connected
        
        if connected:
            # Log to main window if available
            if self.parent_window and hasattr(self.parent_window, 'log_event'):
                self.parent_window.log_event(
                    f"Tic {tic_id} controller connected: {self.serial_numbers[tic_id]}",
                    color="#4CAF50",
                    log_type=f"TIC-{tic_id}"
                )
        else:
            # Log to main window
            if self.parent_window and hasattr(self.parent_window, 'log_event'):
                self.parent_window.log_event(
                    f"Tic {tic_id} connection failed: {message}",
                    color="#f44336",
                    log_type=f"TIC-{tic_id}"
                )
        
        # Update display if this is the selected TIC
        if tic_id == self.selected_tic:
            self.update_display_for_selected_tic()
    
    def handle_status(self, tic_id, status):
        """Handle status updates"""
        if self._is_closing:
            return
        # Update position
        if 'position' in status:
            self.current_position[tic_id] = status['position']
        
        # Update current velocity
        if 'current_velocity' in status:
            self.current_velocity[tic_id] = status['current_velocity']
        
        # Update VIN voltage
        if 'vin_voltage' in status:
            self.vin_voltage[tic_id] = status['vin_voltage']
        
        # Update energized status
        if 'energized' in status:
            self.is_energized[tic_id] = status['energized']
        
        # Update display if this is the selected TIC
        if tic_id == self.selected_tic:
            self.update_display_for_selected_tic()
    
    def handle_velocity_confirmed(self, tic_id, velocity):
        """Handle velocity confirmation"""
        if self._is_closing:
            return
        self.target_velocity[tic_id] = velocity
        # Log to main window
        if self.parent_window and hasattr(self.parent_window, 'log_event'):
            self.parent_window.log_event(
                f"TIC {tic_id} velocity set: {velocity} steps/10000s",
                color="#3498DB",
                log_type=f"TIC-{tic_id}"
            )
    
    def handle_position(self, tic_id, position):
        """Handle position updates"""
        if self._is_closing:
            return
        self.current_position[tic_id] = position
        if tic_id == self.selected_tic:
            self.position_label.setText(str(position))
    
    def handle_error(self, tic_id, error):
        """Handle errors from Tic"""
        if self._is_closing:
            return
        # Log to main window if available
        if self.parent_window and hasattr(self.parent_window, 'log_event'):
            self.parent_window.log_event(
                f"Tic {tic_id} error: {error}",
                color="#f44336",
                log_type=f"TIC-{tic_id}-ERROR"
            )
    
    def handle_command_log(self, tic_id, command, response):
        """Handle command/response logging"""
        if self._is_closing:
            return
        # Log to parent window with TX/RX format
        if self.parent_window and hasattr(self.parent_window, 'log_event'):
            self.parent_window.log_event(
                f"TIC {tic_id} {command} | {response}",
                color=COLOR_TIC,
                log_type=f"TIC-{tic_id}-SERIAL"
            )
    
    def request_status_update(self):
        """Request status update from both TICs"""
        for tic_id in ['A', 'B']:
            if self._is_closing:
                return
            if (
                self.tic_threads[tic_id]
                and self.is_connected[tic_id]
                and not self._status_poll_inflight[tic_id]
            ):
                self._status_poll_inflight[tic_id] = True
                threading.Thread(
                    target=self._poll_status_worker,
                    args=(tic_id,),
                    daemon=True
                ).start()

    def _poll_status_worker(self, tic_id):
        """Run blocking status query off the UI thread."""
        try:
            if not self._is_closing and self.tic_threads[tic_id]:
                self.tic_threads[tic_id].query_status()
        finally:
            QTimer.singleShot(0, lambda tid=tic_id: self._mark_poll_complete(tid))

    def _mark_poll_complete(self, tic_id):
        """Mark a TIC polling cycle as complete."""
        self._status_poll_inflight[tic_id] = False
    
    def set_velocity_from_input(self):
        """Set velocity from input field for selected TIC"""
        tic = self.selected_tic
        if not self.is_connected[tic] or not self.tic_threads[tic]:
            QMessageBox.warning(self, "Not Connected", f"TIC {tic} is not connected.")
            return
        
        try:
            velocity = int(self.velocity_input.text())
            self.set_velocity(velocity)
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Please enter a valid integer velocity.")
    
    def slider_velocity_changed(self, value): #slider was removed -MK
        """Handle slider velocity change -"""
        self.velocity_input.setText(str(value))
    
    def set_velocity(self, velocity):
        """Set motor velocity for selected TIC"""
        tic = self.selected_tic
        if not self.is_connected[tic] or not self.tic_threads[tic]:
            return
        
        success = self.tic_threads[tic].set_velocity(velocity)
        
        if success:
            # Update slider to match
            self.velocity_slider.setValue(velocity)
            
            # Log to main window
            if self.parent_window and hasattr(self.parent_window, 'log_event'):
                self.parent_window.log_event(
                    f"Tic {tic} velocity: {velocity} steps/10000s",
                    color="#3498DB",
                    log_type=f"TIC-{tic}"
                )
    
    def stop_motor(self):
        """Stop motor (set velocity to 0) for selected TIC"""
        tic = self.selected_tic
        if not self.is_connected[tic] or not self.tic_threads[tic]:
            return
        
        self.set_velocity(0)
        
        # Log to main window
        if self.parent_window and hasattr(self.parent_window, 'log_event'):
            self.parent_window.log_event(
                f"Tic {tic} motor STOPPED",
                color="#E74C3C",
                log_type=f"TIC-{tic}"
            )
    
    def energize_motor(self):
        """Energize the motor for selected TIC"""
        tic = self.selected_tic
        if not self.is_connected[tic] or not self.tic_threads[tic]:
            return
        
        success = self.tic_threads[tic].energize()
        
        if success and self.parent_window and hasattr(self.parent_window, 'log_event'):
            self.parent_window.log_event(
                f"Tic {tic} motor energized",
                color="#27AE60",
                log_type=f"TIC-{tic}"
            )
    
    def deenergize_motor(self):
        """De-energize the motor for selected TIC"""
        tic = self.selected_tic
        if not self.is_connected[tic] or not self.tic_threads[tic]:
            return
        
        success = self.tic_threads[tic].deenergize()
        
        if success and self.parent_window and hasattr(self.parent_window, 'log_event'):
            self.parent_window.log_event(
                f"Tic {tic} motor de-energized",
                color="#E67E22",
                log_type=f"TIC-{tic}"
            )
    
    def closeEvent(self, event):
        """Handle dialog close"""
        self._is_closing = True
        # Stop update timer
        self.update_timer.stop()
        
        # Stop both TIC motors and threads
        for tic_id in ['A', 'B']:
            if self.tic_threads[tic_id] and self.tic_threads[tic_id].isRunning():
                # Stop motor for safety
                try:
                    self.tic_threads[tic_id].set_velocity(0)
                    time.sleep(0.2)  # Give more time for command to complete
                except:
                    pass
                
                self.tic_threads[tic_id].stop()
                self.tic_threads[tic_id].wait(2000)  # Wait up to 2 seconds for thread to finish
        
        event.accept()