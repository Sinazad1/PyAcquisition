"""
Protocol Control Dialog (within Acquisition Mode)
Interface for loading and executing automated test protocols

Doc status: done, MK, 01/30/2026
"""
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
                              QLabel, QPushButton, QTextEdit, QGroupBox, 
                              QFileDialog, QMessageBox, QProgressBar)
from PySide6.QtCore import Qt
from datetime import timedelta
from PySide6.QtGui import QGuiApplication

from modes.hardware.protocol_handler import ProtocolHandler
import json
try:
    from ionin.protocols import ProtocolDefinition
    from ionin.runtime import ProtocolEngine
    from modes.integration.ionin_fixture_adapter import AppFixtureAdapter
except Exception:
    ProtocolDefinition = None
    ProtocolEngine = None
    AppFixtureAdapter = None

# Import UI constants
from modes.utils.ui_constants import COLOR_INFO, COLOR_ERROR_DARK, COLOR_SUCCESS_DARK

class ProtocolDialog(QDialog):
    """Protocol control dialog"""
    
    # region INITIALIZATION
    
    def __init__(self, parent=None):
        """
        Initialize the protocol dialog.
        
        Creates a dialog for selecting, loading, and executing calibration protocols.
        Displays protocol settings and provides control interface for protocol run.
        
        Args:
            parent (QWidget, optional): Parent widget (typically AcquisitionWindow).
                Defaults to None.
        """
        super().__init__(parent)
        self.parent_window = parent
        
        # Protocol handler
        self.protocol_handler = ProtocolHandler()
        self.ionin_runtime_enabled = False
        self.ionin_protocol_engine = None
        self.ionin_fixture_adapter = None
        if ProtocolEngine is not None and ProtocolDefinition is not None and AppFixtureAdapter is not None and self.parent_window:
            try:
                self.ionin_protocol_engine = ProtocolEngine()
                self.ionin_fixture_adapter = AppFixtureAdapter(self.parent_window)
                self.ionin_runtime_enabled = True
                if hasattr(self.parent_window, "log_event"):
                    self.parent_window.log_event(
                        "IonIn runtime bridge enabled for protocol step execution",
                        color=COLOR_INFO,
                        log_type="IONIN-RUNTIME",
                    )
            except Exception as e:
                self.ionin_runtime_enabled = False
                if hasattr(self.parent_window, "log_event"):
                    self.parent_window.log_event(
                        f"IonIn runtime bridge unavailable, using legacy step executor: {e}",
                        color=COLOR_ERROR_DARK,
                        log_type="IONIN-RUNTIME",
                    )
        
        # Connect signals
        self.protocol_handler.protocol_starting.connect(self.handle_protocol_starting)
        self.protocol_handler.step_started.connect(self.handle_step_started)
        self.protocol_handler.step_completed.connect(self.handle_step_completed)
        self.protocol_handler.protocol_completed.connect(self.handle_protocol_completed)
        self.protocol_handler.protocol_aborted.connect(self.handle_protocol_aborted)
        self.protocol_handler.time_remaining.connect(self.handle_time_update)
        self.protocol_handler.error_occurred.connect(self.handle_error)
        
        self.current_protocol_file = None
        
        self.init_ui()
    
    def init_ui(self):
        """Initialize UI"""
        self.setWindowTitle("Protocol Control")
        self.setModal(False)
        self.setMinimumWidth(450)
        self.setMinimumHeight(500)
        
        main_layout = QVBoxLayout()
        
        # Title
        title = QLabel("Protocol Control")
        title.setStyleSheet("font-size: 16pt; font-weight: bold; padding: 10px;")
        title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)
        
        # File controls
        main_layout.addWidget(self._create_file_controls())
        
        # Protocol info
        main_layout.addWidget(self._create_protocol_info())
        
        # Current step display
        main_layout.addWidget(self._create_current_step_display())
        
        # Progress bar
        #main_layout.addWidget(self._create_progress_section())
        
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
    
    # endregion
    

    # region UI
    
    def _create_file_controls(self):
        """Create file loading controls"""
        group = QGroupBox("Protocol File")
        layout = QHBoxLayout()
        
        self.file_label = QLabel("No protocol loaded")
        self.file_label.setStyleSheet("color: #888; font-size: 10pt;")
        layout.addWidget(self.file_label, 1)
        
        load_button = QPushButton("Load Protocol")
        load_button.setStyleSheet("""
            QPushButton {
                background-color: #3498DB;
                color: white;
                padding: 8px 15px;
                font-weight: bold;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #2980B9;
            }
        """)
        load_button.clicked.connect(self.load_protocol)
        layout.addWidget(load_button)
        
        group.setLayout(layout)
        return group
    
    def _create_protocol_info(self):
        """Create protocol information display"""
        group = QGroupBox("Protocol Summary")
        layout = QVBoxLayout()
        
        self.protocol_info = QTextEdit()
        self.protocol_info.setReadOnly(True)
        self.protocol_info.setMaximumHeight(120)
        self.protocol_info.setPlainText("No protocol loaded")
        self.protocol_info.setStyleSheet("""
            QTextEdit {
                background-color: #f5f5f5;
                color: #2c3e50;
                padding: 8px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 10pt;
                border: 1px solid #bdc3c7;
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.protocol_info)
        
        group.setLayout(layout)
        return group
    
    def _create_current_step_display(self):
        """Create current step display"""
        group = QGroupBox("Current Step")
        layout = QGridLayout()
        
        layout.addWidget(QLabel("Step:"), 0, 0)
        self.step_label = QLabel("--")
        self.step_label.setStyleSheet("font-size: 14pt; font-weight: bold; color: #3498DB;")
        layout.addWidget(self.step_label, 0, 1)
        
        layout.addWidget(QLabel("Description:"), 1, 0)
        self.description_label = QLabel("--")
        self.description_label.setStyleSheet("font-size: 11pt;")
        layout.addWidget(self.description_label, 1, 1)
        
        layout.addWidget(QLabel("Time Remaining:"), 2, 0)
        self.time_label = QLabel("--:--")
        self.time_label.setStyleSheet("font-size: 16pt; font-weight: bold; color: #E74C3C;")
        layout.addWidget(self.time_label, 2, 1)
        
        layout.addWidget(QLabel("Est. Completion:"), 3, 0)
        self.completion_time_label = QLabel("--:--")
        self.completion_time_label.setStyleSheet("font-size: 12pt; color: #27AE60;")
        layout.addWidget(self.completion_time_label, 3, 1)
        
        group.setLayout(layout)
        return group
    
    def _create_progress_section(self):
        """Create progress bar section"""
        group = QGroupBox("Protocol Progress")
        layout = QVBoxLayout()
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #3498DB;
                border-radius: 5px;
                text-align: center;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #3498DB;
            }
        """)
        layout.addWidget(self.progress_bar)
        
        group.setLayout(layout)
        return group
    
    def _create_control_buttons(self):
        """Create control buttons"""
        group = QGroupBox("Control")
        layout = QHBoxLayout()
        
        # START button
        self.start_button = QPushButton("START")
        self.start_button.setEnabled(False)
        self.start_button.setStyleSheet("""
            QPushButton {
                background-color: #27AE60;
                color: white;
                padding: 15px 20px;
                font-size: 14pt;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #229954;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666;
            }
        """)
        self.start_button.clicked.connect(self.start_protocol)
        layout.addWidget(self.start_button)
        
        # ABORT button
        self.abort_button = QPushButton("ABORT")
        self.abort_button.setEnabled(False)
        self.abort_button.setStyleSheet("""
            QPushButton {
                background-color: #E74C3C;
                color: white;
                padding: 15px 20px;
                font-size: 14pt;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #C0392B;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666;
            }
        """)
        self.abort_button.clicked.connect(self.abort_protocol)
        layout.addWidget(self.abort_button)
        
        group.setLayout(layout)
        return group
    
    def position_aligned_right_offset(self, vertical_fraction=0.25):
        """Position dialog aligned to right of parent with vertical offset"""
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
    
    # endregion
    
    # region PROTOCOL FILE OPERATIONS
    
    def load_protocol(self):
        """Load protocol from JSON file"""
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Load Protocol",
            "",
            "Protocol Files (*.json);;All Files (*)"
        )
        
        if filepath:
            success = self.protocol_handler.load_protocol(filepath)
            
            if success:
                self.current_protocol_file = filepath
                self.file_label.setText(filepath)
                self.file_label.setStyleSheet("color: #27AE60; font-size: 10pt;")
                
                # Update protocol info
                summary = self.protocol_handler.get_protocol_summary()
                self.protocol_info.setPlainText(summary)
                
                # Enable start button
                self.start_button.setEnabled(True)
                
                # Log to main window
                if self.parent_window and hasattr(self.parent_window, 'log_event'):
                    meta = getattr(self.protocol_handler, "protocol_metadata", {}) or {}
                    checksum = meta.get("protocol_checksum")
                    checksum_msg = f" | checksum={checksum}" if checksum else ""
                    self.parent_window.log_event(
                        f"Protocol loaded: {filepath}{checksum_msg}",
                        color=COLOR_INFO,
                        log_type="PROTOCOL"
                    )
                
            else:
                # Log to main window
                if self.parent_window and hasattr(self.parent_window, 'log_event'):
                    self.parent_window.log_event(
                        f"Failed to load protocol: {filepath}",
                        color=COLOR_ERROR_DARK,
                        log_type="PROTOCOL"
                    )
    
    # endregion
    
    # region PROTOCOL EXECUTION CONTROL
    
    def start_protocol(self):
        """Start protocol execution"""
        if not self.parent_window:
            QMessageBox.warning(self, "Error", "Parent window not available")
            return
        
        # Confirm start
        reply = QMessageBox.question(
            self,
            "Start Protocol",
            "Start protocol execution?\n\n"
            "This will control the syringe pump, Tic controller, and chiller.\n"
            "DUT and reference sensor monitoring will continue normally.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Get save directory and measurement timestamp from parent's data manager
            save_directory = None
            measurement_timestamp = None
            if hasattr(self.parent_window, 'data_manager'):
                if hasattr(self.parent_window.data_manager, 'save_directory'):
                    save_directory = self.parent_window.data_manager.save_directory
                if hasattr(self.parent_window.data_manager, 'get_measurement_timestamp'):
                    measurement_timestamp = self.parent_window.data_manager.get_measurement_timestamp()
            
            # Start protocol with measurement timestamp
            success, needs_new_files, timestamp = self.protocol_handler.start_protocol(
                save_directory, 
                measurement_timestamp
            )
            
            if needs_new_files:
                # Event file already exists - need to create new measurement files
                if self.parent_window and hasattr(self.parent_window, 'log_event'):
                    self.parent_window.log_event(
                        f"Event file for {timestamp} already exists. Creating new measurement files...",
                        color=COLOR_INFO,
                        log_type="PROTOCOL"
                    )
                
                # Create new measurement and log files
                if hasattr(self.parent_window, 'data_manager') and hasattr(self.parent_window.data_manager, 'create_new_files'):
                    file_created = self.parent_window.data_manager.create_new_files()
                    if file_created:
                        # Get new timestamp and try again
                        new_timestamp = self.parent_window.data_manager.get_measurement_timestamp()
                        success, needs_new_files, timestamp = self.protocol_handler.start_protocol(
                            save_directory,
                            new_timestamp
                        )
                        
                        if success:
                            self.start_button.setEnabled(False)
                            self.abort_button.setEnabled(True)
                            if self.parent_window and hasattr(self.parent_window, 'log_event'):
                                self.parent_window.log_event(
                                    f"New measurement files created with timestamp: {new_timestamp}",
                                    color=COLOR_SUCCESS_DARK,
                                    log_type="PROTOCOL"
                                )
                    else:
                        QMessageBox.warning(
                            self,
                            "Error",
                            "Failed to create new measurement files. Protocol not started."
                        )
            elif success:
                self.start_button.setEnabled(False)
                self.abort_button.setEnabled(True)
                
                # Note: protocol starting message is handled by handle_protocol_starting

    def abort_protocol(self):
        """Abort protocol execution"""
        reply = QMessageBox.question(
            self,
            "Abort Protocol",
            "Abort protocol execution?\n\n"
            "All devices will remain in their current state.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.protocol_handler.abort_protocol()
    
    # endregion

    # region PROTOCOL EVENT HANDLERS
    
    def handle_protocol_starting(self):
        """Handle protocol starting"""
        # Unpause the system if it's paused
        if self.parent_window and hasattr(self.parent_window, 'unpause'):
            self.parent_window.unpause()
        
        # Log to main window
        if self.parent_window and hasattr(self.parent_window, 'log_event'):
            self.parent_window.log_event(
                "Protocol starting, please wait...",
                color=COLOR_SUCCESS_DARK,
                log_type="PROTOCOL"
            )
    
    def handle_step_started(self, step_number, step):
        """Handle step started"""
        self.step_label.setText(f"Step {step_number} / {self.protocol_handler.get_step_count()}")
        self.description_label.setText(step.description or "No description")
        
        # Update progress
        progress = ((step_number - 1) / self.protocol_handler.get_step_count()) * 100
        #self.progress_bar.setValue(int(progress))
        
        # Calculate and update estimated completion time
        self._update_completion_time()
        
        # Log to main window
        if self.parent_window and hasattr(self.parent_window, 'log_event'):
            self.parent_window.log_event(
                f"Protocol step {step_number} started: {step.description}",
                color=COLOR_INFO,
                log_type="PROTOCOL"
            )
        
        # Apply settings to devices
        self._apply_step_settings(step)
    
    def handle_step_completed(self, step_number):
        """Handle step completed"""
        # Log to main window
        if self.parent_window and hasattr(self.parent_window, 'log_event'):
            self.parent_window.log_event(
                f"Protocol step {step_number} completed",
                color=COLOR_INFO,
                log_type="PROTOCOL"
            )
    
    def handle_protocol_completed(self):
        """Handle protocol completion"""
        self.step_label.setText("Complete")
        self.description_label.setText("Protocol execution finished")
        self.time_label.setText("00:00")
        self.completion_time_label.setText("Completed")
        #self.progress_bar.setValue(100)
        
        self.start_button.setEnabled(True)
        self.abort_button.setEnabled(False)
        
        # Stop all TIC threads
        if self.parent_window and hasattr(self.parent_window, 'device_controller'):
            if hasattr(self.parent_window.device_controller, 'stop_all_tic_threads'):
                self.parent_window.device_controller.stop_all_tic_threads()
        
        # Pause the system after protocol completion
        if self.parent_window and hasattr(self.parent_window, 'pause'):
            self.parent_window.pause()
        
        # Log to main window
        if self.parent_window and hasattr(self.parent_window, 'log_event'):
            self.parent_window.log_event(
                "Protocol execution completed",
                color=COLOR_SUCCESS_DARK,
                log_type="PROTOCOL"
            )
        
        QMessageBox.information(
            self,
            "Protocol Complete",
            "Protocol execution completed successfully!"
        )
    
    def handle_protocol_aborted(self):
        """Handle protocol abortion"""
        self.step_label.setText("Aborted")
        self.description_label.setText("Protocol execution aborted")
        self.time_label.setText("--:--")
        self.completion_time_label.setText("--:--")
        
        self.start_button.setEnabled(True)
        self.abort_button.setEnabled(False)
        
        # Log to main window first
        if self.parent_window and hasattr(self.parent_window, 'log_event'):
            self.parent_window.log_event(
                "Protocol execution aborted - Stopping all devices...",
                color=COLOR_ERROR_DARK,
                log_type="PROTOCOL"
            )
        
        # Stop all devices (pump, chiller, TICs)
        if self.parent_window and hasattr(self.parent_window, 'device_controller'):
            if hasattr(self.parent_window.device_controller, 'stop_all_devices'):
                self.parent_window.device_controller.stop_all_devices()
                
                # Log devices stopped to protocol events file
                if hasattr(self.protocol_handler, '_log_protocol_event'):
                    self.protocol_handler._log_protocol_event("All devices stopped (Pump, Chiller, TIC A, TIC B)")
                
                # Confirm devices stopped in UI
                if hasattr(self.parent_window, 'log_event'):
                    self.parent_window.log_event(
                        "All devices stopped",
                        color=COLOR_INFO,
                        log_type="PROTOCOL"
                    )
        
        # Pause the system after protocol abortion
        if self.parent_window and hasattr(self.parent_window, 'pause'):
            self.parent_window.pause()
    
    def handle_time_update(self, seconds_remaining):
        """Handle time remaining update"""
        minutes = seconds_remaining // 60
        seconds = seconds_remaining % 60
        self.time_label.setText(f"{minutes:02d}:{seconds:02d}")
        
        # Update completion time estimate
        self._update_completion_time()
    
    def handle_error(self, error):
        """Handle error"""
        # Log to main window
        if self.parent_window and hasattr(self.parent_window, 'log_event'):
            self.parent_window.log_event(
                f"Protocol error: {error}",
                color=COLOR_ERROR_DARK,
                log_type="PROTOCOL"
            )
        QMessageBox.critical(self, "Protocol Error", error)
    
    # endregion
    
    # region UTILITY METHODS
    
    def _update_completion_time(self):
        """Calculate and update estimated completion time"""
        from datetime import datetime, timedelta
        
        if not self.protocol_handler.is_running:
            self.completion_time_label.setText("--:--")
            return
        
        # Calculate remaining time in all steps
        total_remaining_seconds = 0
        
        # Add remaining time in current step
        current_step = self.protocol_handler.get_current_step()
        if current_step:
            current_remaining = self.protocol_handler.step_duration_seconds - self.protocol_handler.time_elapsed_seconds
            total_remaining_seconds += current_remaining
        
        # Add time for all remaining steps
        current_index = self.protocol_handler.current_step_index
        for i in range(current_index + 1, len(self.protocol_handler.protocol_steps)):
            step = self.protocol_handler.protocol_steps[i]
            total_remaining_seconds += step.duration_minutes * 60
        
        # Calculate completion time
        completion_time = datetime.now() + timedelta(seconds=total_remaining_seconds)
        
        # Format as time (HH:MM:SS or HH:MM AM/PM)
        time_str = completion_time.strftime("%I:%M:%S %p")
        self.completion_time_label.setText(time_str)
    
    def _apply_step_settings(self, step):
        """Apply step settings to devices"""
        # This method calls the parent window to apply settings
        if not self.parent_window:
            return

        if self.ionin_runtime_enabled and self.ionin_protocol_engine and self.ionin_fixture_adapter:
            try:
                actions = [
                    {
                        "name": f"step_{step.step_number}_start",
                        "action": "event",
                        "params": {"payload": {"step": step.step_number, "description": step.description or ""}},
                    }
                ]
                if step.pump_settings:
                    actions.append(
                        {
                            "name": f"step_{step.step_number}_pump",
                            "action": "pump_settings",
                            "params": dict(step.pump_settings),
                        }
                    )
                if step.tic_a_settings:
                    actions.append(
                        {
                            "name": f"step_{step.step_number}_tic_a",
                            "action": "tic_a_settings",
                            "params": dict(step.tic_a_settings),
                        }
                    )
                if step.tic_b_settings:
                    actions.append(
                        {
                            "name": f"step_{step.step_number}_tic_b",
                            "action": "tic_b_settings",
                            "params": dict(step.tic_b_settings),
                        }
                    )
                if step.chiller_settings:
                    actions.append(
                        {
                            "name": f"step_{step.step_number}_chiller",
                            "action": "chiller_settings",
                            "params": dict(step.chiller_settings),
                        }
                    )
                actions.append(
                    {
                        "name": f"step_{step.step_number}_sample",
                        "action": "sample",
                        "params": {},
                    }
                )

                protocol = ProtocolDefinition.from_dict(
                    {
                        "protocol_name": "ui_protocol_step_bridge",
                        "protocol_version": "1.0.0",
                        "steps": actions,
                    }
                )
                summary = self.ionin_protocol_engine.execute(protocol, self.ionin_fixture_adapter)
                if hasattr(self.parent_window, "log_event"):
                    self.parent_window.log_event(
                        f"IonIn bridge step {step.step_number}: actions={summary.step_count}, samples={summary.sample_count}",
                        color=COLOR_SUCCESS_DARK,
                        log_type="IONIN-RUNTIME",
                    )
                return
            except Exception as e:
                if hasattr(self.parent_window, "log_event"):
                    self.parent_window.log_event(
                        f"IonIn bridge failed on step {step.step_number}, falling back to legacy path: {e}",
                        color=COLOR_ERROR_DARK,
                        log_type="IONIN-RUNTIME",
                    )
        
        # Apply pump settings
        if step.pump_settings and hasattr(self.parent_window, 'apply_pump_settings'):
            self.parent_window.apply_pump_settings(step.pump_settings)
        
        # Apply TIC A settings
        if step.tic_a_settings and hasattr(self.parent_window, 'apply_tic_a_settings'):
            self.parent_window.apply_tic_a_settings(step.tic_a_settings)
        
        # Apply TIC B settings
        if step.tic_b_settings and hasattr(self.parent_window, 'apply_tic_b_settings'):
            self.parent_window.apply_tic_b_settings(step.tic_b_settings)
        
        # Apply chiller settings
        if step.chiller_settings and hasattr(self.parent_window, 'apply_chiller_settings'):
            self.parent_window.apply_chiller_settings(step.chiller_settings)
    
    # endregion
    
    # region EVENT HANDLERS
    
    def closeEvent(self, event):
        """Handle dialog close"""
        if self.protocol_handler.is_running:
            reply = QMessageBox.question(
                self,
                "Protocol Running",
                "Protocol is still running.\n\n"
                "Abort and close?",
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                self.protocol_handler.abort_protocol()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
    
    # endregion