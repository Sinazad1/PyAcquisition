"""
Control Panel Module
Handles the right-side control panel with buttons and status in acquisition mode

Doc status: done, MK, 01/30/2026
"""
from PySide6.QtWidgets import (QVBoxLayout, QGridLayout, QPushButton, 
                             QLabel, QWidget)
from PySide6.QtCore import Qt


class ControlPanel:
    """Manages the control panel UI and button callbacks"""
    
    def __init__(self, parent):
        """
        Initialize the control panel widget.
        
        Creates the main control panel with buttons for pause, protocol,
        device control, and other acquisition functions.
        
        Args:
            parent: Reference to parent window (AcquisitionWindow).
        """
        self.parent = parent
        
        # UI elements that need to be accessed later
        self.status_text = None
        self.data_counter_label = None
        self.countdown_label = None  # New countdown label
        self.pause_button = None
        
        # Store button references for production mode control
        self.stop_button = None
        self.add_event_button = None
        self.new_file_button = None
        self.clear_data_button = None
        self.open_save_button = None
        self.chiller_button = None
        self.syringe_pump_button = None
        self.tic_ctrl_button = None
        self.run_protocol_button = None
        self.preflight_button = None
        self.preflight_summary_label = None
    
    def create_control_panel(self):
        """Create the complete control panel layout"""
        control_layout = QVBoxLayout()
        control_layout.setSpacing(10)
        
        # Status section
        control_layout.addWidget(self._create_status_section())
        
        # Data counter
        self.data_counter_label = QLabel("Data Points: 0")
        self.data_counter_label.setAlignment(Qt.AlignCenter)
        self.data_counter_label.setStyleSheet("""
            QLabel {
                background-color: #2A2A2A;
                color: #00FF00;
                font-weight: bold;
                padding: 5px;
                font-size: 11pt;
            }
        """)
        control_layout.addWidget(self.data_counter_label)
        
        # Countdown timer
        self.countdown_label = QLabel("Next reading: --")
        self.countdown_label.setAlignment(Qt.AlignCenter)
        self.countdown_label.setStyleSheet("""
            QLabel {
                background-color: #1A1A3A;
                color: #00BFFF;
                font-weight: bold;
                padding: 5px;
                font-size: 10pt;
            }
        """)
        control_layout.addWidget(self.countdown_label)
        
        # Control buttons
        control_layout.addLayout(self._create_control_buttons())
        
        # Peripheral control
        control_layout.addWidget(self._create_peripheral_label())
        control_layout.addLayout(self._create_peripheral_buttons())
        
        # Protocol section
        control_layout.addWidget(self._create_protocol_label())
        control_layout.addLayout(self._create_protocol_buttons())
        
        control_layout.addStretch()
        
        return control_layout
    
    def _create_status_section(self):
        """Create status label section"""
        status_label = QLabel("STATUS")
        status_label.setAlignment(Qt.AlignCenter)
        status_label.setStyleSheet("""
            QLabel {
                background-color: #404040;
                color: white;
                font-weight: bold;
                padding: 5px;
                font-size: 14pt;
            }
        """)
        
        self.status_text = QLabel("Closing COM Ports")
        self.status_text.setAlignment(Qt.AlignCenter)
        self.status_text.setStyleSheet("""
            QLabel {
                background-color: #C0C0C0;
                color: black;
                font-weight: bold;
                padding: 8px;
                font-size: 13pt;
            }
        """)
        
        # Create a container for both labels
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(status_label)
        layout.addWidget(self.status_text)
        
        return container
    
    def _create_control_buttons(self):
        """Create control button grid"""
        button_grid = QGridLayout()
        button_grid.setSpacing(10)
        
        # Pause/Play button
        self.pause_button = QPushButton("||")
        self.pause_button.setMinimumSize(120, 100)
        self.pause_button.setStyleSheet("""
            QPushButton {
                background-color: #4A4A2A;
                color: white;
                font-size: 48pt;
                font-weight: bold;
                border: 2px solid #333;
                text-align: center;
                padding-bottom: 18px;
                min-width: 120px;
                min-height: 100px;
            }
            QPushButton:hover {
                background-color: #5A5A3A;
            }
            QPushButton:pressed {
                background-color: #3A3A1A;
            }
        """)
        self.pause_button.clicked.connect(self.parent.toggle_pause)
        button_grid.addWidget(self.pause_button, 0, 0)
        
        # Stop button
        self.stop_button = QPushButton("■")
        self.stop_button.setMinimumSize(120, 100)
        self.stop_button.setStyleSheet("""
            QPushButton {
                background-color: #2A2A2A;
                color: #CC0000;
                font-size: 64pt;
                font-weight: bold;
                border: 2px solid #333;
                padding-bottom: 18px;
                min-width: 120px;
                min-height: 100px;
            }
            QPushButton:hover {
                background-color: #3A3A3A;
            }
            QPushButton:pressed {
                background-color: #1A1A1A;
            }
        """)
        self.stop_button.setToolTip("Stop current run (keeps window open)")
        self.stop_button.clicked.connect(self.parent.stop_program)
        button_grid.addWidget(self.stop_button, 0, 1)
        
        # Add Event button
        self.add_event_button = QPushButton("Add Event")
        self.add_event_button.setMinimumSize(120, 70)
        self.add_event_button.setStyleSheet("""
            QPushButton {
                background-color: #2A2A2A;
                color: #FF00FF;
                font-size: 16pt;
                font-weight: bold;
                border: 2px solid #333;
            }
            QPushButton:hover {
                background-color: #3A3A3A;
            }
        """)
        self.add_event_button.clicked.connect(self.parent.add_event)
        button_grid.addWidget(self.add_event_button, 1, 0)
        
        # New Data File button
        self.new_file_button = QPushButton("New Data\nFile")
        self.new_file_button.setMinimumSize(120, 70)
        self.new_file_button.setStyleSheet("""
            QPushButton {
                background-color: #2A2A2A;
                color: #FFFF00;
                font-size: 16pt;
                font-weight: bold;
                border: 2px solid #333;
            }
            QPushButton:hover {
                background-color: #3A3A3A;
            }
        """)
        self.new_file_button.clicked.connect(self.parent.create_new_data_file)
        button_grid.addWidget(self.new_file_button, 1, 1)
        
        # Clear Data button
        self.clear_data_button = QPushButton("Clear Data")
        self.clear_data_button.setMinimumSize(120, 70)
        self.clear_data_button.setStyleSheet("""
            QPushButton {
                background-color: #2A2A2A;
                color: #FF4444;
                font-size: 16pt;
                font-weight: bold;
                border: 2px solid #333;
            }
            QPushButton:hover {
                background-color: #3A3A3A;
            }
        """)
        self.clear_data_button.clicked.connect(self.parent.clear_data)
        button_grid.addWidget(self.clear_data_button, 2, 0)
        
        # Open Save Location button
        self.open_save_button = QPushButton("Open Save\nLocation")
        self.open_save_button.setMinimumSize(120, 70)
        self.open_save_button.setStyleSheet("""
            QPushButton {
                background-color: #2A2A2A;
                color: white;
                font-size: 14pt;
                font-weight: bold;
                border: 2px solid #333;
            }
            QPushButton:hover {
                background-color: #3A3A3A;
            }
        """)
        self.open_save_button.clicked.connect(self.parent.open_save_location)
        button_grid.addWidget(self.open_save_button, 2, 1)
        
        # System Log button
        system_log_button = QPushButton("System Log")
        system_log_button.setMinimumSize(250, 70)
        system_log_button.setStyleSheet("""
            QPushButton {
                background-color: #2A2A2A;
                color: #00BFFF;
                font-size: 16pt;
                font-weight: bold;
                border: 2px solid #333;
            }
            QPushButton:hover {
                background-color: #3A3A3A;
            }
        """)
        #system_log_button.clicked.connect(self.parent.show_system_log_popup)
        #button_grid.addWidget(system_log_button, 3, 0, 1, 2)  # Span 2 columns - Removed, MK
        
        return button_grid
    
    def _create_peripheral_label(self):
        """Create peripheral control label"""
        peripheral_label = QLabel("Peripheral Control")
        peripheral_label.setAlignment(Qt.AlignCenter)
        peripheral_label.setStyleSheet("""
            QLabel {
                background-color: #404040;
                color: white;
                font-weight: bold;
                padding: 5px;
                font-size: 14pt;
                margin-top: 10px;
            }
        """)
        return peripheral_label
    
    def _create_peripheral_buttons(self):
        """Create peripheral control button grid"""
        peripheral_grid = QGridLayout()
        peripheral_grid.setSpacing(10)
        
        # Chiller button
        self.chiller_button = QPushButton("Chiller")
        self.chiller_button.setMinimumSize(120, 70)
        self.chiller_button.setStyleSheet("""
            QPushButton {
                background-color: #2A2A2A;
                color: #00CED1;
                font-size: 16pt;
                font-weight: bold;
                border: 2px solid #333;
            }
            QPushButton:hover {
                background-color: #3A3A3A;
            }
        """)
        self.chiller_button.clicked.connect(self.parent.control_chiller)
        peripheral_grid.addWidget(self.chiller_button, 0, 0)
        
        # Syringe Pump button
        self.syringe_pump_button = QPushButton("Syringe Pump")
        self.syringe_pump_button.setMinimumSize(120, 70)
        self.syringe_pump_button.setStyleSheet("""
            QPushButton {
                background-color: #2A2A2A;
                color: #FFA500;
                font-size: 16pt;
                font-weight: bold;
                border: 2px solid #333;
            }
            QPushButton:hover {
                background-color: #3A3A3A;
            }
        """)
        self.syringe_pump_button.clicked.connect(self.parent.control_syringe_pump)
        peripheral_grid.addWidget(self.syringe_pump_button, 0, 1)
        
        # Tic Ctrl button (spans both columns)
        self.tic_ctrl_button = QPushButton("Tic Ctrl")
        self.tic_ctrl_button.setMinimumSize(250, 70)
        self.tic_ctrl_button.setStyleSheet("""
            QPushButton {
                background-color: #2A2A2A;
                color: #9370DB;
                font-size: 16pt;
                font-weight: bold;
                border: 2px solid #333;
            }
            QPushButton:hover {
                background-color: #3A3A3A;
            }
        """)
        self.tic_ctrl_button.clicked.connect(self.parent.control_tic)
        peripheral_grid.addWidget(self.tic_ctrl_button, 1, 0, 1, 2)  # Span 2 columns
        
        return peripheral_grid
    
    def _create_protocol_label(self):
        """Create protocol control label"""
        protocol_label = QLabel("Protocol")
        protocol_label.setAlignment(Qt.AlignCenter)
        protocol_label.setStyleSheet("""
            QLabel {
                background-color: #404040;
                color: white;
                font-weight: bold;
                padding: 5px;
                font-size: 14pt;
                margin-top: 10px;
            }
        """)
        return protocol_label
    
    def _create_protocol_buttons(self):
        """Create protocol control button"""
        protocol_layout = QVBoxLayout()
        protocol_layout.setSpacing(10)
        
        # Run Protocol button
        self.run_protocol_button = QPushButton("Run Protocol")
        self.run_protocol_button.setMinimumSize(250, 70)
        self.run_protocol_button.setStyleSheet("""
            QPushButton {
                background-color: #2A2A2A;
                color: #00FF00;
                font-size: 18pt;
                font-weight: bold;
                border: 2px solid #333;
            }
            QPushButton:hover {
                background-color: #3A3A3A;
            }
            QPushButton:pressed {
                background-color: #1A4A1A;
            }
        """)
        self.run_protocol_button.clicked.connect(self.parent.run_protocol)
        protocol_layout.addWidget(self.run_protocol_button)

        # CN0359 preflight button (safe no-op in non-CN0359 mode)
        self.preflight_button = QPushButton("CN0359 Preflight")
        self.preflight_button.setMinimumSize(250, 56)
        self.preflight_button.setStyleSheet("""
            QPushButton {
                background-color: #2A2A2A;
                color: #00CED1;
                font-size: 14pt;
                font-weight: bold;
                border: 2px solid #333;
            }
            QPushButton:hover {
                background-color: #3A3A3A;
            }
        """)
        self.preflight_button.clicked.connect(self.parent.run_cn0359_preflight_check)
        protocol_layout.addWidget(self.preflight_button)

        self.preflight_summary_label = QLabel("Preflight: not run")
        self.preflight_summary_label.setAlignment(Qt.AlignCenter)
        self.preflight_summary_label.setStyleSheet("""
            QLabel {
                background-color: #1F1F1F;
                color: #BBBBBB;
                font-size: 10pt;
                padding: 6px;
                border: 1px solid #333;
            }
        """)
        protocol_layout.addWidget(self.preflight_summary_label)
        
        return protocol_layout
    
    def update_status(self, text, style=None):
        """Update status text and optionally style"""
        self.status_text.setText(text)
        if style:
            self.status_text.setStyleSheet(style)
    
    def update_data_counter(self, text):
        """Update data counter label"""
        self.data_counter_label.setText(text)
    
    def update_countdown(self, seconds):
        """Update countdown timer display"""
        if seconds is None:
            self.countdown_label.setText("Next reading: --")
        elif seconds <= 0:
            self.countdown_label.setText("Next reading: NOW")
        else:
            self.countdown_label.setText(f"Next reading: {seconds:.1f}s")
    
    def set_pause_button_state(self, is_paused):
        """Update pause button appearance based on state"""
        if is_paused:
            self.pause_button.setText("▶")
            self.pause_button.setStyleSheet("""
                QPushButton {
                    background-color: #2A5A2A;
                    color: white;
                    font-size: 48pt;
                    font-weight: bold;
                    border: 2px solid #333;
                    text-align: center;
                    padding-bottom: 18px;
                    min-width: 120px;
                    min-height: 100px;
                }
                QPushButton:hover {
                    background-color: #3A6A3A;
                }
                QPushButton:pressed {
                    background-color: #1A4A1A;
                }
            """)
        else:
            self.pause_button.setText("||")
            self.pause_button.setStyleSheet("""
                QPushButton {
                    background-color: #4A4A2A;
                    color: white;
                    font-size: 48pt;
                    font-weight: bold;
                    border: 2px solid #333;
                    text-align: center;
                    padding-bottom: 18px;
                    min-width: 120px;
                    min-height: 100px;
                }
                QPushButton:hover {
                    background-color: #5A5A3A;
                }
                QPushButton:pressed {
                    background-color: #3A3A1A;
                }
            """)

    def update_preflight_summary(self, text, status="neutral"):
        """Update compact CN0359 preflight summary line."""
        if not self.preflight_summary_label:
            return
        color = "#BBBBBB"
        if status == "ok":
            color = "#90EE90"
        elif status == "warn":
            color = "#FFA500"
        elif status == "bad":
            color = "#FF6666"
        self.preflight_summary_label.setText(f"Preflight: {text}")
        self.preflight_summary_label.setStyleSheet(f"""
            QLabel {{
                background-color: #1F1F1F;
                color: {color};
                font-size: 10pt;
                padding: 6px;
                border: 1px solid #333;
            }}
        """)
    
    def configure_production_mode(self, production_mode):
        """Configure button states for production mode
        
        In production mode, only these buttons are enabled:
        - Run Protocol
        - Stop
        - Open Save Location
        
        All other buttons are disabled (including pause/play).
        """
        if production_mode:
            # Disable most buttons
            self.add_event_button.setEnabled(False)
            self.new_file_button.setEnabled(False)
            self.clear_data_button.setEnabled(False)
            self.chiller_button.setEnabled(False)
            self.syringe_pump_button.setEnabled(False)
            self.tic_ctrl_button.setEnabled(False)
            self.pause_button.setEnabled(False)
            if self.preflight_button:
                self.preflight_button.setEnabled(False)
            
            # Keep these enabled
            # self.run_protocol_button - stays enabled
            # self.stop_button - stays enabled
            # self.open_save_button - stays enabled
            
            # Update visual styling for disabled buttons
            disabled_style = """
                QPushButton:disabled {
                    background-color: #1A1A1A;
                    color: #555555;
                    border: 2px solid #222;
                }
            """
            
            self.add_event_button.setStyleSheet(self.add_event_button.styleSheet() + disabled_style)
            self.new_file_button.setStyleSheet(self.new_file_button.styleSheet() + disabled_style)
            self.clear_data_button.setStyleSheet(self.clear_data_button.styleSheet() + disabled_style)
            self.chiller_button.setStyleSheet(self.chiller_button.styleSheet() + disabled_style)
            self.syringe_pump_button.setStyleSheet(self.syringe_pump_button.styleSheet() + disabled_style)
            self.tic_ctrl_button.setStyleSheet(self.tic_ctrl_button.styleSheet() + disabled_style)
            self.pause_button.setStyleSheet(self.pause_button.styleSheet() + disabled_style)
            if self.preflight_button:
                self.preflight_button.setStyleSheet(self.preflight_button.styleSheet() + disabled_style)
