"""
Acquisition Mode 
Coordinates all UI components and serial communication within this mode; 
also interfaces to each peripheral and protocol mode

Doc status: done, MK, 01/30/2026
"""
from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
                             QTextEdit, QLabel, QMessageBox, QInputDialog, QPushButton, QSplitter, QApplication)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPalette, QColor, QTextCursor
from datetime import datetime
import os
import platform
import subprocess
import time

from modes.hardware.dut_handler import DutHandler
# CN0359 direct sensor support -- replaces Teensy when config.ini [CN0359] enabled = true
from modes.hardware.cn0359_handler import CN0359Handler
from modes.hardware.ibp_reference_handler import IBPReferenceHandler
from modes.dialogs.serial_selector import UnifiedSerialSelector
from modes.dialogs.syringe_pump_dialog import SyringePumpDialog
from modes.dialogs.chiller_dialog import ChillerDialog
from modes.dialogs.tic_dialog import TicDialog
from modes.dialogs.protocol_dialog import ProtocolDialog
from modes.utils.control_panel import ControlPanel
from modes.utils.graph_widgets import GraphManager
from modes.controllers.device_controller import DeviceController
from modes.controllers.data_manager import DataManager
from modes.controllers.data_parser import DataParser
# CN0359 parser -- converts 22-line ASCII responses into the same dict format as DataParser
from modes.controllers.cn0359_parser import CN0359Parser
from modes.utils.version import VERSION_STRING
try:
    from ionin.compat import parse_for_legacy_app as ionin_parse_for_legacy_app
    from ionin.compat import LegacySessionAdapter as IonInLegacySessionAdapter
except Exception:
    ionin_parse_for_legacy_app = None
    IonInLegacySessionAdapter = None

# Import configuration module (not individual variables to get live values)
try:
    from modes.utils import config
    # Access values through config.VARIABLE_NAME to get live values after settings.py loads
except ImportError:
    # Create a dummy config object with defaults
    class ConfigDefaults:
        """
        Configuration defaults for the acquisition system.
        
        """
        BAUDRATE = 115200
        TIMEOUT = 5
        QUERY_INTERVAL = 5
        MAX_OUTPUT_LINES = 1000
        config.TIMESTAMP_FORMAT = "%H:%M:%S.%f"
        config.DUT_COM_PORT = None
        config.ENABLE_IBP_REFERENCES = True
        config.IBP_REF1_PORT = None
        config.IBP_REF2_PORT = None
        config.IBP_BAUDRATE = 115200
        config.IBP_TIMEOUT = 2.0
        config.SYRINGE_PUMP_PORT = None
        config.CHILLER_PORT = None
        config.TIC_A_SERIAL_NUMBER = None
        config.TIC_B_SERIAL_NUMBER = None
    config = ConfigDefaults()

class AcquisitionWindow(QMainWindow):
    """
    Main window for data acquisition mode.
    
    This window coordinates all UI components, hardware interfaces, and data
    collection for the acquisition system. It manages serial communication with
    the DUT, IBP reference sensors, syringe pump, chiller, and TIC controllers.
    
    Attributes:
        production_mode (bool): Whether running in production mode.
        setup_cancelled (bool): Flag indicating if setup was cancelled.
        dut_handler (DutHandler): Handler for DUT serial communication.
        is_paused (bool): Current pause state of data acquisition.
        ibp_ref1_handler (IBPReferenceHandler): Handler for first IBP reference.
        ibp_ref2_handler (IBPReferenceHandler): Handler for second IBP reference.
        pump_thread (SyringePumpHandler): Thread for syringe pump control.
        chiller_thread (ChillerHandler): Thread for chiller control.
        tic_thread (TicHandler): Thread for TIC stepper controller.
        data_manager (DataManager): Manager for data logging and CSV writing.
        graph_manager (GraphManager): Manager for real-time graph displays.
        control_panel (ControlPanel): UI control panel with buttons.
        device_controller (DeviceController): Controller for hardware devices.
    """
    # region INITIALIZATION
    
    def __init__(self, production_mode=False):
        """
        Initialize the acquisition window.
        
        Sets up all hardware handlers, UI components, and data managers. Checks
        for configuration file and prompts for serial device setup.
        
        Args:
            production_mode (bool, optional): Enable production mode features.
                Defaults to False.
        """
        super().__init__()
        
        # Production mode flag
        self.production_mode = production_mode

        # Flag to track if setup was cancelled
        self.setup_cancelled = False
        
        # Serial handler
        self.serial_handler = None
        # Check if CN0359 direct sensor mode is enabled in config.ini.
        # When True, the app talks directly to CN0359 boards instead of
        # going through the Teensy.  When False (default), the old Teensy
        # path is used -- nothing changes.
        self.cn0359_mode = getattr(config, 'CN0359_ENABLED', False)
        self.ionin_mode = bool(getattr(config, "IONIN_ENABLED", False))
        self.ionin_storage_adapter = None
        self.cn0359_preflight_state = "not_run"
        self.cn0359_emulator_active = False
        self.is_paused = True  # Start paused by default
        
        # IBP Reference handlers
        self.ibp_ref1_handler = None
        self.ibp_ref2_handler = None
        self.ibp_ref1_sn = None
        self.ibp_ref2_sn = None
        self.pending_ibp_data = {}  # Store IBP data for CSV writing
        
        # Syringe pump
        self.pump_port = None
        self.pump_thread = None
        
        # Chiller
        self.chiller_port = None
        self.chiller_thread = None
        
        # Tic stepper controllers
        self.tic_serial = None  # Kept for backward compatibility
        self.tic_a_serial = None
        self.tic_b_serial = None
        self.tic_thread = None
        
        # Protocol dialog reference
        self.protocol_dialog = None
        
        # Countdown tracking
        self.last_query_time = None
        self.countdown_timer = QTimer()
        self.countdown_timer.timeout.connect(self.update_countdown_display)
        self.countdown_timer.start(100)  # Update every 100ms for smooth countdown
        
        # Initialize managers
        self.data_manager = DataManager(parent=self)
        self.graph_manager = GraphManager()
        self.control_panel = ControlPanel(parent=self)
        self.device_controller = DeviceController(parent_window=self)
        
        # Initialize UI
        self.init_ui()
        
        # Set initial pause button state (system starts paused)
        self.control_panel.set_pause_button_state(self.is_paused)
        
        # Configure production mode if enabled
        if self.production_mode:
            self.control_panel.configure_production_mode(True)

        # Initialize IonIn storage adapter only after UI is ready (log widgets exist).
        if self.ionin_mode and IonInLegacySessionAdapter is not None:
            self._init_ionin_storage_adapter()
        
        # Check if config.ini exists and offer to create it
        self.check_and_offer_config_creation()
        
        # Setup serial connection (now includes IBP setup)
        self.setup_serial()
        self._log_ionin_mode_status()
    
    def check_and_offer_config_creation(self):
        """Check if config.ini exists and offer to create it if missing"""
        try:
            from modes.utils.settings import CONFIG_FILE_FOUND, create_default_config_file
            import sys
            from pathlib import Path
            
            if not CONFIG_FILE_FOUND:
                # Determine where config.ini should be created
                import sys
                from pathlib import Path
                
                # Check if running as compiled exe
                # Check only the filename, not the full path (path might contain "python" in folder name)
                exe_name = Path(sys.executable).name.lower()
                ends_with_exe = exe_name.endswith('.exe')
                contains_python = 'python' in exe_name
                is_frozen = ends_with_exe and not contains_python
                
                print(f"[DEBUG] sys.executable = {sys.executable}")
                print(f"[DEBUG] exe_name = {exe_name}")
                print(f"[DEBUG] ends_with_exe = {ends_with_exe}")
                print(f"[DEBUG] contains_python = {contains_python}")
                print(f"[DEBUG] is_frozen = {is_frozen}")
                
                if is_frozen:
                    # Running as .exe - get directory of the exe
                    config_dir = Path(sys.executable).parent
                    print(f"[DEBUG] Running as frozen exe")
                    print(f"[DEBUG] Using exe parent dir = {config_dir}")
                else:
                    # Running as script
                    config_dir = Path(__file__).parent.parent
                    print(f"[DEBUG] Running as script, config_dir = {config_dir}")
                
                config_path = config_dir / "config.ini"
                print(f"[DEBUG] Will create config at: {config_path}")
                
                # Show dialog asking if user wants to create config.ini
                reply = QMessageBox.question(
                    self,
                    'Create Configuration File?',
                    f'No config.ini file was found.\n\n'
                    f'Would you like to create a default configuration file?\n\n'
                    f'Location: {config_path}\n\n'
                    f'This file will allow you to:\n'
                    f'• Save default port assignments\n'
                    f'• Customize timeout values\n'
                    f'• Set serial communication parameters\n\n'
                    f'You can edit it with any text editor.',
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes  # Default to Yes
                )
                
                if reply == QMessageBox.Yes:
                    print(f"[DEBUG] User clicked Yes, creating config.ini")
                    if create_default_config_file(config_dir):
                        print(f"[DEBUG] Config file created successfully")
                        QMessageBox.information(
                            self,
                            'Configuration File Created',
                            f'config.ini has been created at:\n\n'
                            f'{config_path}\n\n'
                            f'You can:\n'
                            f'• Edit it with Notepad to customize settings\n'
                            f'• Save port selections later (after connecting)\n'
                            f'• Changes take effect after restarting the app'
                        )
                    else:
                        print(f"[DEBUG] Config file creation failed")
                        QMessageBox.warning(
                            self,
                            'Creation Failed',
                            f'Could not create config.ini at:\n\n'
                            f'{config_path}\n\n'
                            f'The application will use default settings.'
                        )
                else:
                    print(f"[DEBUG] User clicked No, skipping config creation")
        except Exception as e:
            print(f"[DEBUG] Exception in config creation: {e}")
            import traceback
            traceback.print_exc()
    
    # endregion

    def _log_ionin_mode_status(self):
        """Log effective IonIn mode so operators can verify runtime path."""
        if not self.ionin_mode:
            self.log_event("IONIN MODE: disabled (built-in parser/storage active)", color="#888888", log_type="SYSTEM")
            return

        parser_active = ionin_parse_for_legacy_app is not None
        storage_active = self.ionin_storage_adapter is not None

        if parser_active and storage_active:
            msg = "IONIN MODE: parser+storage active"
            color = "#00FF7F"
        elif parser_active:
            msg = "IONIN MODE: parser active, storage fallback"
            color = "#FFD700"
        elif storage_active:
            msg = "IONIN MODE: storage active, parser fallback"
            color = "#FFD700"
        else:
            msg = "IONIN MODE: requested but unavailable; built-in parser/storage active"
            color = "#FFA500"

        self.log_event(msg, color=color, log_type="SYSTEM")
    
    # region UI INITIALIZATION
    
    def init_ui(self):
        """Initialize the user interface"""
        title = "alyPyAcquisition - Acquisition Mode"
        if self.production_mode:
            title += " [PRODUCTION MODE]"
        self.setWindowTitle(title)
        self.setGeometry(100, 100, 1800, 700)
        
        # Set dark theme
        self.set_dark_theme()
        
        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        
        # Left/Middle: Graphs and serial output with splitter
        graphs_and_output_widget = QWidget()
        graphs_and_output_layout = QVBoxLayout(graphs_and_output_widget)
        graphs_and_output_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create a vertical splitter for graphs and system log
        splitter = QSplitter(Qt.Vertical)
        splitter.setHandleWidth(8)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #404040;
                border: 1px solid #505050;
            }
            QSplitter::handle:hover {
                background-color: #505050;
            }
        """)
        
        # Create graphs widget
        graphs_widget = QWidget()
        graphs_layout = QVBoxLayout(graphs_widget)
        graphs_layout.setContentsMargins(0, 0, 0, 0)
        graphs_layout.addLayout(self.graph_manager.create_graphs_layout())
        
        # Create system log widget
        system_log_widget = QWidget()
        system_log_layout = QVBoxLayout(system_log_widget)
        system_log_layout.setContentsMargins(0, 0, 0, 0)
        system_log_layout.addWidget(self._create_serial_output_label())
        system_log_layout.addWidget(self._create_serial_output_box())
        
        # Add both to splitter
        splitter.addWidget(graphs_widget)
        splitter.addWidget(system_log_widget)
        
        # Set initial sizes (graphs get more space than system log)
        splitter.setSizes([500, 150])
        
        graphs_and_output_layout.addWidget(splitter)
        
        main_layout.addWidget(graphs_and_output_widget, 3)
        
        # Right: Control panel
        main_layout.addLayout(self.control_panel.create_control_panel(), 1)
        
        # Add status bar with version info
        self.statusBar().showMessage(f"{VERSION_STRING}")
        
        # Create shutdown overlay (hidden by default)
        self.shutdown_overlay = self._create_shutdown_overlay()
        self.shutdown_overlay.hide()
    
    def _create_shutdown_overlay(self):
        """Create an overlay widget for shutdown message"""
        overlay = QWidget(self)
        overlay.setStyleSheet("""
            QWidget {
                background-color: rgba(0, 0, 0, 180);
            }
        """)
        
        # Layout for centered content
        layout = QVBoxLayout(overlay)
        layout.setAlignment(Qt.AlignCenter)
        
        # Message label
        message = QLabel("Stopping Acquisition Mode\n\nPlease wait...")
        message.setAlignment(Qt.AlignCenter)
        message.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 18pt;
                font-weight: bold;
                background-color: transparent;
                padding: 30px;
            }
        """)
        layout.addWidget(message)
        
        return overlay
    
    def _show_shutdown_overlay(self):
        """Show the shutdown overlay covering the entire window"""
        self.shutdown_overlay.setGeometry(self.rect())
        self.shutdown_overlay.raise_()
        self.shutdown_overlay.show()
        # Process events to ensure overlay is displayed
        QApplication.processEvents()
    
    def resizeEvent(self, event):
        """Handle window resize to keep overlay properly sized"""
        super().resizeEvent(event)
        if hasattr(self, 'shutdown_overlay'):
            self.shutdown_overlay.setGeometry(self.rect())
        
    def _create_serial_output_label(self):
        """Create header label for system log"""
        # System Log label
        output_label = QLabel("System Log")
        output_label.setAlignment(Qt.AlignLeft)
        output_label.setStyleSheet("""
            QLabel {
                color: white;
                font-weight: bold;
                padding: 5px;
                font-size: 12pt;
            }
        """)
        return output_label
    
    def _create_serial_output_box(self):
        """Create serial output text box"""
        self.serial_output = QTextEdit()
        self.serial_output.setReadOnly(True)
        self.serial_output.setStyleSheet("""
            QTextEdit {
                background-color: #1a1a1a;
                color: #00ff00;
                font-family: 'Courier New', monospace;
                font-size: 11pt;
                border: 1px solid #404040;
            }
        """)
        return self.serial_output
    
    def set_dark_theme(self):
        """Set dark theme for the application"""
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(53, 53, 53))
        palette.setColor(QPalette.WindowText, Qt.white)
        palette.setColor(QPalette.Base, QColor(25, 25, 25))
        palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
        palette.setColor(QPalette.ToolTipBase, Qt.white)
        palette.setColor(QPalette.ToolTipText, Qt.white)
        palette.setColor(QPalette.Text, Qt.white)
        palette.setColor(QPalette.Button, QColor(53, 53, 53))
        palette.setColor(QPalette.ButtonText, Qt.white)
        palette.setColor(QPalette.BrightText, Qt.red)
        palette.setColor(QPalette.Link, QColor(42, 130, 218))
        palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.HighlightedText, Qt.black)
        self.setPalette(palette)
    
    # endregion
    
    # region SERIAL & DEVICE SETUP
    
    def setup_serial(self):
        """Setup serial connection and IBP references using unified selector"""
            
        selector = UnifiedSerialSelector(
            None, 
            default_dut=config.DUT_COM_PORT,
            default_ref1=config.IBP_REF1_PORT, 
            default_ref2=config.IBP_REF2_PORT,
            default_pump=config.SYRINGE_PUMP_PORT,
            default_chiller=config.CHILLER_PORT,
            default_tic_a_serial=config.TIC_A_SERIAL_NUMBER if hasattr(config, 'TIC_A_SERIAL_NUMBER') else None,
            default_tic_b_serial=config.TIC_B_SERIAL_NUMBER if hasattr(config, 'TIC_B_SERIAL_NUMBER') else None,
            enable_ibp=config.ENABLE_IBP_REFERENCES
        )
        
        if selector.exec():
            dut_port, ref1_port, ref2_port, pump_port, chiller_port, tic_a_serial, tic_b_serial, use_ibp = selector.get_selected_ports()
            
            # Check if any values have changed from config
            ports_changed = (
                dut_port != config.DUT_COM_PORT or
                ref1_port != config.IBP_REF1_PORT or
                ref2_port != config.IBP_REF2_PORT or
                pump_port != config.SYRINGE_PUMP_PORT or
                chiller_port != config.CHILLER_PORT or
                tic_a_serial != (config.TIC_A_SERIAL_NUMBER if hasattr(config, 'TIC_A_SERIAL_NUMBER') else None) or
                tic_b_serial != (config.TIC_B_SERIAL_NUMBER if hasattr(config, 'TIC_B_SERIAL_NUMBER') else None)
            )
            
            # Only offer to save if values have changed
            if ports_changed:
                try:
                    from modes.utils.settings import save_ports_to_config
                    
                    # Build list of changes
                    changes = []
                    if dut_port != config.DUT_COM_PORT:
                        changes.append(f"DUT: {config.DUT_COM_PORT or 'None'} -> {dut_port or 'None'}")
                    if ref1_port != config.IBP_REF1_PORT:
                        changes.append(f"IBP Ref 1: {config.IBP_REF1_PORT or 'None'} -> {ref1_port or 'None'}")
                    if ref2_port != config.IBP_REF2_PORT:
                        changes.append(f"IBP Ref 2: {config.IBP_REF2_PORT or 'None'} -> {ref2_port or 'None'}")
                    if pump_port != config.SYRINGE_PUMP_PORT:
                        changes.append(f"Pump: {config.SYRINGE_PUMP_PORT or 'None'} -> {pump_port or 'None'}")
                    if chiller_port != config.CHILLER_PORT:
                        changes.append(f"Chiller: {config.CHILLER_PORT or 'None'} -> {chiller_port or 'None'}")
                    
                    tic_a_old = config.TIC_A_SERIAL_NUMBER if hasattr(config, 'TIC_A_SERIAL_NUMBER') else None
                    tic_b_old = config.TIC_B_SERIAL_NUMBER if hasattr(config, 'TIC_B_SERIAL_NUMBER') else None
                    
                    if tic_a_serial != tic_a_old:
                        changes.append(f"Tic A Serial: {tic_a_old or 'None'} -> {tic_a_serial or 'None'}")
                    if tic_b_serial != tic_b_old:
                        changes.append(f"Tic B Serial: {tic_b_old or 'None'} -> {tic_b_serial or 'None'}")
                    
                    changes_text = '\n'.join(changes)
                    
                    # Ask user if they want to save these selections
                    reply = QMessageBox.question(
                        self,
                        'Save Port Configuration?',
                        f'Port assignments have changed.\n\n'
                        f'Would you like to save these changes to config.ini?\n\n'
                        f'Changes:\n{changes_text}\n\n'
                        f'These will be pre-selected on next startup.',
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.Yes  # Default to Yes since they changed something
                    )
                    
                    if reply == QMessageBox.Yes:
                        if save_ports_to_config(dut_port, ref1_port, ref2_port, pump_port, chiller_port, tic_a_serial, tic_b_serial):
                            QMessageBox.information(
                                self,
                                'Configuration Saved',
                                'Port assignments have been saved to config.ini.\n\n'
                                'These ports will be pre-selected the next time you start the application.'
                            )
                        else:
                            QMessageBox.warning(
                                self,
                                'Save Failed',
                                'Could not save port assignments to config.ini.\n'
                                'You may need to manually edit the file.'
                            )
                except ImportError:
                    pass  # settings module not available, skip
            else:
                print("[DEBUG] No port changes detected, skipping save prompt")
            
            # ---- SENSOR HANDLER SELECTION ----
            # This is where the app decides which serial handler to use.
            # If CN0359 mode is enabled AND the user selected at least one
            # sensor port in the dialog, we create a CN0359Handler.
            # Otherwise, we fall back to the original DutHandler (Teensy).
            # Both handlers emit the same signals (data_received, error_occurred,
            # etc.) so the rest of this method doesn't need to know which one
            # is running.
            cn0359_sensors = selector.get_cn0359_sensors() if self.cn0359_mode else []
            if self.ionin_mode and ionin_parse_for_legacy_app is None:
                self.log_event(
                    "IONIN_ENABLED is true but ionin package is unavailable; falling back to built-in parser.",
                    color="#FFA500",
                    log_type="SYSTEM",
                )
            if self.ionin_mode and IonInLegacySessionAdapter is None:
                self.log_event(
                    "IONIN_ENABLED is true but IonIn storage adapter is unavailable; using DataManager CSV path.",
                    color="#FFA500",
                    log_type="SYSTEM",
                )
            if self.cn0359_mode and cn0359_sensors:
                self.cn0359_preflight_state = "not_run"
                self.cn0359_emulator_active = any(
                    str(cfg[1]).upper().startswith("EMULATOR") for cfg in cn0359_sensors
                )
                self.serial_handler = CN0359Handler(
                    sensor_configs=cn0359_sensors,
                    baudrate=getattr(config, 'CN0359_BAUDRATE', 115200),
                    query_interval=getattr(config, 'CN0359_POLL_INTERVAL', 10),
                )
                self.serial_handler.data_received.connect(self.handle_data)
                self.serial_handler.error_occurred.connect(self.handle_error)
                self.serial_handler.disconnected.connect(self.handle_disconnection)
                self.serial_handler.command_sent.connect(self.handle_serial_command)
                self.serial_handler.response_received.connect(self.handle_serial_response)
                self.serial_handler.start()
                self.serial_handler.pause()
                self.control_panel.update_status(
                    "CN0359 Emulator Ready (Paused)"
                    if self.cn0359_emulator_active else
                    "CN0359 Ready (Paused)",
                    """
                        QLabel {
                            background-color: #FFA500;
                            color: black;
                            font-weight: bold;
                            padding: 8px;
                            font-size: 13pt;
                        }
                    """
                )
                self.log_event(
                    f"CN0359 mode active with {len(cn0359_sensors)} configured sensor(s); run preflight before Play.",
                    color="#00CED1",
                    log_type="SYSTEM"
                )
                if self.cn0359_emulator_active:
                    self.log_event(
                        "EMULATOR MODE ACTIVE: acquisition data is simulated (not from physical DUT boards).",
                        color="#FFA500",
                        log_type="SYSTEM"
                    )
                self.control_panel.update_preflight_summary("not run", status="neutral")
            elif dut_port:
                self.serial_handler = DutHandler(
                    port=dut_port,
                    baudrate=config.BAUDRATE,
                    timeout=config.TIMEOUT,
                    query_interval=config.QUERY_INTERVAL
                )
                self.serial_handler.data_received.connect(self.handle_data)
                self.serial_handler.error_occurred.connect(self.handle_error)
                self.serial_handler.disconnected.connect(self.handle_disconnection)
                self.serial_handler.command_sent.connect(self.handle_serial_command)
                self.serial_handler.response_received.connect(self.handle_serial_response)
                self.serial_handler.start()
                
                # Pause immediately since system starts paused
                self.serial_handler.pause()
                
                # Initialize countdown tracking
                self.last_query_time = time.time()
                
                # Update status to show paused state
                self.control_panel.update_status(
                    "Paused - Press Play to Start",
                    """
                        QLabel {
                            background-color: #FFA500;
                            color: black;
                            font-weight: bold;
                            padding: 8px;
                            font-size: 13pt;
                        }
                    """
                )
                
                # Log connection event
                self.log_event(
                    f"Serial port connected: {dut_port} @ {config.BAUDRATE} baud (PAUSED)",
                    color="#FFA500",
                    log_type="SYSTEM"
                )
            
            # Setup IBP References if enabled
            if use_ibp and (ref1_port or ref2_port):
                self.setup_ibp_references_direct(ref1_port, ref2_port)
            
            # Store pump port for when pump dialog is opened
            self.pump_port = pump_port
            self.device_controller.set_pump_port(pump_port)
            if pump_port:
                self.log_event(
                    f"Syringe pump port selected: {pump_port}",
                    color="#00BFFF",
                    log_type="SYSTEM"
                )
            
            # Store chiller port for when chiller dialog is opened
            self.chiller_port = chiller_port
            self.device_controller.set_chiller_port(chiller_port)
            if chiller_port:
                self.log_event(
                    f"Chiller port selected: {chiller_port}",
                    color="#00BFFF",
                    log_type="SYSTEM"
                )
            
            # Store Tic serials for when Tic dialog is opened
            self.tic_a_serial = tic_a_serial
            self.tic_b_serial = tic_b_serial
            self.device_controller.set_tic_serials(tic_a_serial, tic_b_serial)
            if tic_a_serial:
                self.log_event(
                    f"Tic A serial number: {tic_a_serial}",
                    color="#9370DB",
                    log_type="SYSTEM"
                )
            if tic_b_serial:
                self.log_event(
                    f"Tic B serial number: {tic_b_serial}",
                    color="#9370DB",
                    log_type="SYSTEM"
                )
        else:
            # User cancelled the serial selector - close the acquisition window
            self.setup_cancelled = True
            self.log_event("Serial port selection cancelled - closing window", color="#FFA500", log_type="SYSTEM")
            # Use QTimer to close the window after the event loop processes
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self.close)
    
    def setup_ibp_references_direct(self, ref1_port, ref2_port):
        """Setup IBP reference sensors with provided ports"""
        # Setup Reference 1
        if ref1_port:
            try:
                self.ibp_ref1_handler = IBPReferenceHandler(
                    ref_id=1,
                    port=ref1_port,
                    baudrate=config.IBP_BAUDRATE,
                    timeout=config.IBP_TIMEOUT
                )
                self.ibp_ref1_handler.data_received.connect(self.handle_ibp_data)
                self.ibp_ref1_handler.error_occurred.connect(self.handle_ibp_error)
                self.ibp_ref1_handler.disconnected.connect(self.handle_ibp_disconnection)
                self.ibp_ref1_handler.serial_number_received.connect(self.handle_ibp_serial_number)
                self.ibp_ref1_handler.command_sent.connect(self.handle_ibp_command)
                self.ibp_ref1_handler.response_received.connect(self.handle_ibp_response)
                self.ibp_ref1_handler.start()
                
                self.log_event(
                    f"IBP Reference 1 connecting: {ref1_port}",
                    color="#00BFFF",
                    log_type="IBP-REF"
                )
            except Exception as e:
                self.log_event(
                    f"Failed to start IBP Reference 1: {str(e)}",
                    color="#FF0000",
                    log_type="IBP-REF-ERROR"
                )
        
        # Setup Reference 2
        if ref2_port:
            try:
                self.ibp_ref2_handler = IBPReferenceHandler(
                    ref_id=2,
                    port=ref2_port,
                    baudrate=config.IBP_BAUDRATE,
                    timeout=config.IBP_TIMEOUT
                )
                self.ibp_ref2_handler.data_received.connect(self.handle_ibp_data)
                self.ibp_ref2_handler.error_occurred.connect(self.handle_ibp_error)
                self.ibp_ref2_handler.disconnected.connect(self.handle_ibp_disconnection)
                self.ibp_ref2_handler.serial_number_received.connect(self.handle_ibp_serial_number)
                self.ibp_ref2_handler.command_sent.connect(self.handle_ibp_command)
                self.ibp_ref2_handler.response_received.connect(self.handle_ibp_response)
                self.ibp_ref2_handler.start()
                
                self.log_event(
                    f"IBP Reference 2 connecting: {ref2_port}",
                    color="#00BFFF",
                    log_type="IBP-REF"
                )
            except Exception as e:
                self.log_event(
                    f"Failed to start IBP Reference 2: {str(e)}",
                    color="#FF0000",
                    log_type="IBP-REF-ERROR"
                )
    
    # endregion
    
    # region DATA HANDLING (DUT)
    
    def handle_data(self, data):
        """Handle incoming serial data"""
        # Update last query time for countdown
        self.last_query_time = time.time()
        
        # Trigger IBP reference reads (synchronized with DUT)
        if self.ibp_ref1_handler and not self.is_paused:
            self.ibp_ref1_handler.read_data()
        if self.ibp_ref2_handler and not self.is_paused:
            self.ibp_ref2_handler.read_data()
        
        # Get current timestamp
        timestamp = datetime.now().strftime(config.TIMESTAMP_FORMAT)
        # Trim to milliseconds if using microseconds format
        if ".%f" in config.TIMESTAMP_FORMAT:
            timestamp = timestamp[:-3]
        
        # Note: Logging is handled by handle_serial_response() which logs both to UI and file
        # via log_event() with [DUT-SERIAL] tag, so no additional logging needed here
        
        # Parse and store data
        self.parse_and_update(data, timestamp)
    
    def _handler_port_label(self):
        """Return a human-readable port string for the active serial handler.

        Used in the status bar to show which port(s) are active.
        CN0359 mode shows all open sensor ports (e.g. "COM3, COM5").
        Teensy mode shows the single DUT port (e.g. "COM3").
        """
        if self.serial_handler is None:
            return "No connection"
        if self.cn0359_mode:
            # List all sensor ports that are currently open
            ports = [s.port_name for s in self.serial_handler.sensors if s.ser and s.ser.is_open]
            return ", ".join(ports) if ports else "CN0359 (no ports open)"
        return getattr(self.serial_handler, 'port', 'Unknown')

    def run_cn0359_preflight_check(self):
        """Run a one-click CN0359 startup health check for troubleshooting."""
        if not self.cn0359_mode or not isinstance(self.serial_handler, CN0359Handler):
            self.log_event(
                "CN0359 preflight skipped: app is not using CN0359 mode.",
                color="#FFA500",
                log_type="SYSTEM"
            )
            return

        was_paused = self.is_paused
        if not was_paused:
            self.pause()

        self.log_event("CN0359 preflight check started...", color="#00CED1", log_type="SYSTEM")
        snapshot = self.serial_handler.preflight_snapshot(attempts=2)

        detected = [s for s in snapshot if s["detected"]]
        parse_ok = [s for s in snapshot if s["parse_ok"]]
        missing = [s for s in snapshot if not s["detected"]]

        for s in snapshot:
            unit = s["unit_id"]
            port = s["port"]
            if s["detected"]:
                state = "PARSE_OK" if s["parse_ok"] else "NO_PARSE"
                self.log_event(
                    f"Preflight U{unit} ({port}): DETECTED, lines={s['non_empty_lines']}, {state}",
                    color="#90EE90" if s["parse_ok"] else "#FFA500",
                    log_type="CN0359-PREFLIGHT"
                )
            else:
                detail = s["error"] or "no response"
                self.log_event(
                    f"Preflight U{unit} ({port}): NO DATA ({detail})",
                    color="#FF4444",
                    log_type="CN0359-PREFLIGHT"
                )

        summary = (
            f"CN0359 preflight summary: detected {len(detected)}/{len(snapshot)}, "
            f"parse_ok {len(parse_ok)}/{len(snapshot)}, missing {len(missing)}"
        )
        self.log_event(summary, color="#00CED1", log_type="CN0359-PREFLIGHT")

        if len(missing) == 0 and len(parse_ok) == len(snapshot):
            self.cn0359_preflight_state = "pass"
            self.control_panel.update_preflight_summary(
                f"PASS ({len(parse_ok)}/{len(snapshot)})",
                status="ok",
            )
        elif len(detected) > 0:
            self.cn0359_preflight_state = "partial"
            self.control_panel.update_preflight_summary(
                f"PARTIAL ({len(detected)}/{len(snapshot)})",
                status="warn",
            )
        else:
            self.cn0359_preflight_state = "fail"
            self.control_panel.update_preflight_summary(
                f"FAIL (0/{len(snapshot)})",
                status="bad",
            )

        QMessageBox.information(
            self,
            "CN0359 Preflight Result",
            summary + (
                "\n\nMissing ports:\n" + "\n".join(f"- U{s['unit_id']} ({s['port']})" for s in missing)
                if missing else "\n\nAll configured sensors responded."
            )
        )

        if not was_paused:
            self.unpause()

    def _ensure_cn0359_preflight_before_resume(self) -> bool:
        """Gate Play in CN0359 mode until preflight is run/acknowledged."""
        if self.cn0359_preflight_state == "pass":
            return True

        run_now = QMessageBox.question(
            self,
            "CN0359 Preflight Required",
            "Run CN0359 preflight before starting acquisition?\n\n"
            "Recommended: Yes (ensures all configured sensors respond).",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if run_now == QMessageBox.Yes:
            self.run_cn0359_preflight_check()
            if self.cn0359_preflight_state == "pass":
                return True

        override = QMessageBox.warning(
            self,
            "Start Without Passing Preflight?",
            "Preflight is not in PASS state.\n\n"
            "Starting anyway may produce partial or invalid run data.\n\n"
            "Do you want to continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return override == QMessageBox.Yes

    def parse_and_update(self, data, timestamp):
        """Parse serial data and update graphs"""
        try:
            # ---- PARSER SELECTION ----
            # CN0359Handler emits data as a dict {unit_id: response_text}.
            # DutHandler emits data as a single string.
            # We check both the mode flag AND the data type to pick the
            # right parser.  Both parsers return the same dict shape, so
            # everything after this if/else works identically.
            if self.ionin_mode and ionin_parse_for_legacy_app is not None:
                parsed = ionin_parse_for_legacy_app(
                    data,
                    timestamp,
                    cn0359_mode=self.cn0359_mode,
                    max_units=getattr(config, "MAX_DUT_UNITS", 8),
                )
            elif self.cn0359_mode and isinstance(data, dict):
                parsed = CN0359Parser.parse_all_sensors(data, timestamp)
            else:
                parsed = DataParser.parse_all_measurements(data, timestamp)
            time_seconds = parsed['timestamp']
            
            units_updated = []
            refs_updated = []
            
            # Collect all measurements for consolidated CSV row
            dut_measurements = {}
            ref_measurements = {}
            
            # Process DUT units
            for unit_data in parsed['dut_units']:
                unit_id = unit_data['unit_id']
                conductivity = unit_data['conductivity']
                temperature = unit_data['temperature']
                
                # Store for consolidated CSV write
                dut_measurements[unit_id] = {
                    'conductivity': conductivity,
                    'temperature': temperature
                }
                
                # Add to data storage
                self.data_manager.add_dut_data(
                    unit_id, time_seconds, conductivity, temperature
                )
                
                # Update graphs (use RzMag for plotting)
                stored_data = self.data_manager.get_dut_data(unit_id)
                self.graph_manager.update_dut_plots(
                    unit_id,
                    stored_data['timestamps'],
                    stored_data['conductivity_rzmag'],  # Plot DUT resistance (Ohm)
                    stored_data['temperature_rzmag']    # Plot temperature magnitude
                )
                
                units_updated.append(unit_id)
            
            # Process reference devices
            for ref_data in parsed['reference_devices']:
                ref_id = ref_data['ref_id']
                conductivity = ref_data['conductivity']
                temperature = ref_data['temperature']
                
                # For reference devices, the rzmag values are already the converted values
                # conductivity rzmag = conductivity in mS/cm
                # temperature rzmag = temperature in °C
                ref_measurements[ref_id] = {
                    'conductivity_value': conductivity['rzmag'],  # mS/cm
                    'temperature_value': temperature['rzmag']      # °C
                }
                
                # Add to data storage
                self.data_manager.add_reference_data(
                    ref_id, time_seconds, conductivity, temperature
                )
                
                # Update graphs (use RzMag for plotting)
                stored_data = self.data_manager.get_reference_data(ref_id)
                self.graph_manager.update_reference_plots(
                    ref_id,
                    stored_data['timestamps'],
                    stored_data['conductivity_rzmag'],  # Plot conductivity magnitude (mS/cm)
                    stored_data['temperature_rzmag']    # Plot temperature magnitude (°C)
                )
                
                refs_updated.append(ref_id)
            
            # Add IBP reference data to ref_measurements (if available)
            if hasattr(self, 'pending_ibp_data'):
                for ibp_ref_id, ibp_data in self.pending_ibp_data.items():
                    ref_measurements[ibp_ref_id] = ibp_data
                    refs_updated.append(ibp_ref_id) if ibp_ref_id not in refs_updated else None
            
            # Write all measurements for this timestamp as one consolidated CSV row
            if dut_measurements or ref_measurements:
                if self.ionin_storage_adapter is not None:
                    self.ionin_storage_adapter.write_consolidated_row(
                        timestamp, dut_measurements, ref_measurements
                    )
                else:
                    self.data_manager.write_consolidated_row(
                        timestamp, dut_measurements, ref_measurements
                    )
                
                # Clear pending IBP data after writing to CSV
                if hasattr(self, 'pending_ibp_data'):
                    self.pending_ibp_data.clear()
            
            # Update counter label
            if units_updated or refs_updated:
                status_parts = []
                if units_updated:
                    total_dut_points = sum(
                        len(self.data_manager.get_dut_data(uid)['timestamps']) 
                        for uid in units_updated
                    )
                    status_parts.append(
                        f"DUT Units: {', '.join(map(str, units_updated))} ({total_dut_points} pts)"
                    )
                if refs_updated:
                    total_ref_points = sum(
                        len(self.data_manager.get_reference_data(rid)['timestamps']) 
                        for rid in refs_updated
                    )
                    status_parts.append(
                        f"Ref: {', '.join(map(str, refs_updated))} ({total_ref_points} pts)"
                    )
                
                self.control_panel.update_data_counter(" | ".join(status_parts))
        
        except Exception as e:
            self.log_event(
                f"Error parsing measurement data: {e}",
                color="#FF4444",
                log_type="ERROR"
            )
    
    def handle_error(self, error_msg):
        """Handle serial errors"""
        timestamp = datetime.now().strftime(config.TIMESTAMP_FORMAT)
        if ".%f" in config.TIMESTAMP_FORMAT:
            timestamp = timestamp[:-3]
        
        # Write to log file
        self.data_manager.write_to_log(timestamp, f"[ERROR] {error_msg}")
        
        # Display in system log
        self.serial_output.append(
            f'<span style="color: #888888;">[{timestamp}]</span> '
            f'<span style="color: red;">[ERROR] {error_msg}</span>'
        )
        print(f"Serial error: {error_msg}")
    
    def handle_serial_command(self, command):
        """Handle DUT serial command logging"""
        self.log_event(
            f"DUT TX: {command}",
            color="#FFD700",
            log_type="DUT-CMD"
        )
    
    def handle_serial_response(self, command, response):
        """Handle DUT serial response logging - logs exact command and response"""
        self.log_event(
            f"DUT TX: {command} | RX: {response}",
            color="#FFD700",
            log_type="DUT-SERIAL"
        )
    
    def handle_disconnection(self):
        """Handle unexpected disconnection of serial device"""
        self.log_event(
            "Serial device disconnected! Please reconnect device or restart application.",
            color="#FF0000",
            log_type="ERROR"
        )
        
        # Update status
        self.control_panel.update_status(
            "DISCONNECTED",
            """
                QLabel {
                    background-color: #FF0000;
                    color: white;
                    font-weight: bold;
                    padding: 8px;
                    font-size: 13pt;
                }
            """
        )
        
        # Disable pause button
        self.control_panel.pause_button.setEnabled(False)
        
        # Clear serial handler reference since thread has stopped
        self.serial_handler = None
        self.last_query_time = None
        
        # Update countdown to show disconnected
        self.control_panel.update_countdown(None)
        
        # Show message box to user
        QMessageBox.critical(
            self,
            "Connection Lost",
            "Serial device has been disconnected!\n\n"
            "Please:\n"
            "1. Reconnect the device\n"
            "2. Restart the application\n\n"
            "The application cannot automatically reconnect."
        )
    
    # endregion
    
    # region DATA HANDLING (IBP REFERENCE)
    
    def handle_ibp_serial_number(self, ref_id, serial_number):
        """Handle IBP sensor serial number"""
        if ref_id == 1:
            self.ibp_ref1_sn = serial_number
        else:
            self.ibp_ref2_sn = serial_number
        
        self.log_event(
            f"IBP Reference {ref_id} S/N: {serial_number}",
            color="#00FF00",
            log_type="IBP-REF"
        )
    
    def handle_ibp_command(self, ref_id, command):
        """Handle IBP command logging"""
        self.log_event(
            f"IBP Ref{ref_id} -> {command}",
            color="#00CED1",
            log_type="IBP-CMD"
        )
    
    def handle_ibp_response(self, ref_id, command, response):
        """Handle IBP response logging - logs exact command sent and response received"""
        self.log_event(
            f"IBP Ref{ref_id} TX: {command} | RX: {response}",
            color="#00CED1",
            log_type="IBP-SERIAL"
        )
    
    def handle_ibp_data(self, ref_id, conductivity, temperature):
        """Handle IBP reference sensor data"""
        timestamp = time.time()
        
        # Log to system log with full precision (no truncation)
        self.log_event(
            f"IBP Ref{ref_id}: Cond={conductivity} mS/cm, Temp={temperature} °C",
            color="#00BFFF",
            log_type="IBP-DATA"
        )
        
        # Store in data manager (for graphing)
        # Create dummy frequency/phase data since IBP returns direct values
        conductivity_data = {
            'frequency': 10000.0,  # Typical for conductivity
            'rzmag': conductivity,  # Already in mS/cm
            'rzphase': 0.0
        }
        
        temperature_data = {
            'frequency': 0.0,
            'rzmag': temperature,  # Already in °C
            'rzphase': 0.0
        }
        
        self.data_manager.add_reference_data(
            ref_id,
            timestamp,
            conductivity_data,
            temperature_data
        )
        
        # Store for CSV writing (will be written with next DUT data)
        if not hasattr(self, 'pending_ibp_data'):
            self.pending_ibp_data = {}
        
        self.pending_ibp_data[ref_id] = {
            'conductivity_value': conductivity,
            'temperature_value': temperature
        }
        
        # Update graphs
        stored_data = self.data_manager.get_reference_data(ref_id)
        self.graph_manager.update_reference_plots(
            ref_id,
            stored_data['timestamps'],
            stored_data['conductivity_rzmag'],
            stored_data['temperature_rzmag']
        )
    
    def handle_ibp_error(self, ref_id, error_msg):
        """Handle IBP sensor errors"""
        self.log_event(
            f"IBP Reference {ref_id}: {error_msg}",
            color="#FF4444",
            log_type="IBP-REF-ERROR"
        )
    
    def handle_ibp_disconnection(self, ref_id):
        """Handle IBP sensor disconnection"""
        self.log_event(
            f"IBP Reference {ref_id} disconnected!",
            color="#FF0000",
            log_type="IBP-REF-ERROR"
        )
        
        # Clear handler reference
        if ref_id == 1:
            self.ibp_ref1_handler = None
        else:
            self.ibp_ref2_handler = None
    
    # endregion
    
    # region BUTTON HANDLERS (CONTROL PANEL)
    
    def toggle_pause(self):
        """Toggle pause/play state"""
        if (
            self.is_paused
            and self.cn0359_mode
            and isinstance(self.serial_handler, CN0359Handler)
        ):
            if not self._ensure_cn0359_preflight_before_resume():
                return

        self.is_paused = not self.is_paused
        self.control_panel.set_pause_button_state(self.is_paused)
        
        # Actually pause or resume the serial handler
        if self.serial_handler:
            if self.is_paused:
                self.serial_handler.pause()
            else:
                self.serial_handler.resume()
        
        # Note: IBP handlers are synchronized with DUT via handle_data()
        # No need to explicitly pause/resume them
        
        if self.is_paused:
            self.control_panel.update_status(
                "Paused",
                """
                    QLabel {
                        background-color: #FFA500;
                        color: black;
                        font-weight: bold;
                        padding: 8px;
                        font-size: 13pt;
                    }
                """
            )
            # Log pause event
            self.log_event("System paused - serial queries stopped", color="#FFA500", log_type="SYSTEM")
        else:
            if self.serial_handler:
                self.control_panel.update_status(
                    f"{'EMULATOR ' if self.cn0359_emulator_active else ''}"
                    f"Connected: {self._handler_port_label()} @ {config.BAUDRATE} baud",
                    """
                        QLabel {
                            background-color: #90EE90;
                            color: black;
                            font-weight: bold;
                            padding: 8px;
                            font-size: 13pt;
                        }
                    """
                )
            # Log unpause event
            self.log_event("System resumed - serial queries restarted", color="#90EE90", log_type="SYSTEM")
    
    def unpause(self):
        """Unpause the system if it's currently paused"""
        if self.is_paused:
            self.is_paused = False
            self.control_panel.set_pause_button_state(self.is_paused)
            
            # Actually resume the serial handler
            if self.serial_handler:
                self.serial_handler.resume()
            
            if self.serial_handler:
                self.control_panel.update_status(
                    f"{'EMULATOR ' if self.cn0359_emulator_active else ''}"
                    f"Connected: {self._handler_port_label()} @ {config.BAUDRATE} baud",
                    """
                        QLabel {
                            background-color: #90EE90;
                            color: black;
                            font-weight: bold;
                            padding: 8px;
                            font-size: 13pt;
                        }
                    """
                )
            # Log unpause event
            self.log_event("System auto-resumed for protocol execution", color="#90EE90", log_type="SYSTEM")
    
    def pause(self):
        """Pause the system if it's currently running"""
        if not self.is_paused:
            self.is_paused = True
            self.control_panel.set_pause_button_state(self.is_paused)
            
            # Actually pause the serial handler
            if self.serial_handler:
                self.serial_handler.pause()
            
            self.control_panel.update_status(
                "Paused",
                """
                    QLabel {
                        background-color: #FFA500;
                        color: black;
                        font-weight: bold;
                        padding: 8px;
                        font-size: 13pt;
                    }
                """
            )
            # Log pause event
            self.log_event("System auto-paused after protocol completion", color="#FFA500", log_type="SYSTEM")
    
    def stop_program(self):
        """Stop active acquisition safely and keep the app open."""
        self.log_event("System stopped - acquisition halted (window remains open)", color="#FF4444", log_type="SYSTEM")

        # Stop all protocol/device operations first.
        self.stop_all_devices()

        # Pause serial streams; keep handlers alive for easy restart.
        self.pause()
        self.control_panel.update_status(
            "Stopped (Session still open)",
            """
                QLabel {
                    background-color: #FF6666;
                    color: black;
                    font-weight: bold;
                    padding: 8px;
                    font-size: 13pt;
                }
            """
        )

        # Explicitly warn when no measurement rows were captured.
        rows_written = self._rows_written()
        self.log_event(
            f"Acquisition rows written: {rows_written}",
            color="#00CED1" if rows_written > 0 else "#FFA500",
            log_type="SYSTEM",
        )
        if rows_written == 0:
            QMessageBox.warning(
                self,
                "No Data Captured",
                "This run wrote 0 measurement rows.\n\n"
                "Most common causes:\n"
                "- System stayed paused (Play not pressed)\n"
                "- No parseable sensor responses during run\n"
                "- Port selection was cancelled\n\n"
                "Check serial log and run CN0359 preflight before retrying.",
            )
    
    def add_event(self):
        """Prompt user to add an event marker with custom text"""
        text, ok = QInputDialog.getText(
            self, 
            'Add Event Marker', 
            'Enter event description:',
            text=''
        )
        
        if ok and text.strip():
            # Log the event with user's text
            self.log_event(f"EVENT: {text.strip()}", color="#FF00FF", log_type="EVENT")
            print(f"Event added: {text.strip()}")
        elif ok:
            # User clicked OK but didn't enter text
            QMessageBox.warning(self, "No Text", "Please enter a description for the event.")
        # If cancelled (ok=False), do nothing
    
    def create_new_data_file(self):
        """Create new timestamped data files"""
        if self.data_manager.create_new_files():
            if self.ionin_mode and IonInLegacySessionAdapter is not None:
                self._init_ionin_storage_adapter()
            self.log_event(
                f"New data files created: {os.path.basename(self.data_manager.csv_file_path)}, "
                f"{os.path.basename(self.data_manager.log_file_path)}",
                color="#FFFF00",
                log_type="FILE"
            )
            QMessageBox.information(
                self, 
                "New Data Files Created",
                f"New data files created:\n\n"
                f"{os.path.basename(self.data_manager.csv_file_path)}\n"
                f"{os.path.basename(self.data_manager.log_file_path)}"
            )
        else:
            self.log_event("Failed to create new data files", color="#FF0000", log_type="ERROR")
            QMessageBox.critical(
                self, 
                "Error", 
                "Failed to create new files"
            )
    
    def clear_data(self):
        """Clear all data and graphs"""
        self.log_event("All data and graphs cleared", color="#FF4444", log_type="SYSTEM")
        print("Clear Data button clicked")
        self.data_manager.clear_all_data()
        self.graph_manager.clear_all_plots()
        # Don't clear the log itself - just note that data was cleared
    
    def open_save_location(self):
        """Open the save location directory in file explorer"""
        if self.data_manager.save_directory:
            abs_path = os.path.abspath(self.data_manager.save_directory)
            
            if os.path.exists(abs_path):
                system = platform.system()
                try:
                    if system == "Windows":
                        os.startfile(abs_path)
                    elif system == "Darwin":  # macOS
                        subprocess.Popen(["open", abs_path])
                    else:  # Linux
                        subprocess.Popen(["xdg-open", abs_path])
                except Exception as e:
                    QMessageBox.warning(
                        self, "Error", 
                        f"Could not open directory: {str(e)}"
                    )
            else:
                QMessageBox.warning(
                    self, "Directory Not Found",
                    f"Save directory does not exist:\n{abs_path}\n\n"
                    f"Files may not have been created yet."
                )
        else:
            QMessageBox.warning(self, "No Save Location", "No save directory is set.")
    
    # endregion
    
    # region DEVICE CONTROL BUTTONS
    
    def control_syringe_pump(self):
        """Open Syringe Pump control dialog"""
        self.log_event("Opening Syringe Pump controller", color="#FFA500", log_type="CONTROL")
        
        # Create and show syringe pump controller dialog
        pump_dialog = SyringePumpDialog(self, port=self.pump_port)
        pump_dialog.exec()
    
    def control_tic(self):
        """Open Dual Tic stepper controller dialog"""
        self.log_event("Opening Dual Tic controller", color="#9370DB", log_type="CONTROL")
        
        # Get serial numbers for both TICs
        serial_number_a = (
            self.tic_a_serial if hasattr(self, 'tic_a_serial') and self.tic_a_serial
            else (config.TIC_A_SERIAL_NUMBER if hasattr(config, 'TIC_A_SERIAL_NUMBER') else None)
        )
        serial_number_b = (
            self.tic_b_serial if hasattr(self, 'tic_b_serial') and self.tic_b_serial
            else (config.TIC_B_SERIAL_NUMBER if hasattr(config, 'TIC_B_SERIAL_NUMBER') else None)
        )
        
        # Create and show Dual Tic controller dialog
        tic_dialog = TicDialog(self, serial_number_a=serial_number_a, serial_number_b=serial_number_b)
        tic_dialog.exec()
    
    def control_chiller(self):
        """Open chiller control dialog"""
        self.log_event("Opening chiller control", color="#3498DB", log_type="CONTROL")
        
        # Create and show chiller control dialog
        chiller_dialog = ChillerDialog(self, port=self.chiller_port)
        chiller_dialog.exec()
    
    def run_protocol(self):
        """Open protocol control dialog"""
        self.log_event("Opening protocol control", color="#00FF00", log_type="PROTOCOL")
        
        # Create and show protocol control dialog (non-modal)
        # Reuse existing dialog if already open, or create new one
        if self.protocol_dialog is None or not self.protocol_dialog.isVisible():
            self.protocol_dialog = ProtocolDialog(self)
            self.protocol_dialog.show()
        else:
            # Bring existing dialog to front
            self.protocol_dialog.raise_()
            self.protocol_dialog.activateWindow()
    
    # endregion
    
    # region PROTOCOL DEVICE CONTROL
    
    def apply_pump_settings(self, settings):
        """Apply syringe pump settings from protocol - delegated to device_controller"""
        self.device_controller.apply_pump_settings(settings)
    
    def apply_tic_a_settings(self, settings):
        """Apply TIC A stepper settings from protocol - delegated to device_controller"""
        self.device_controller.apply_tic_settings(settings, tic_id='A')
    
    def apply_tic_b_settings(self, settings):
        """Apply TIC B stepper settings from protocol - delegated to device_controller"""
        self.device_controller.apply_tic_settings(settings, tic_id='B')
    
    def apply_chiller_settings(self, settings):
        """Apply chiller settings from protocol - delegated to device_controller"""
        self.device_controller.apply_chiller_settings(settings)
    
    # endregion
    
    # region UTILITY METHODS
    
    def log_event(self, message, color="#00ff00", log_type="INFO"):
        """
        Log a system event to the system log with timestamp
        
        Args:
            message: The message to log
            color: HTML color for the message (default green)
            log_type: Type of log entry (INFO, ERROR, SYSTEM, etc.)
        """
        timestamp = datetime.now().strftime(config.TIMESTAMP_FORMAT)
        # Trim to milliseconds if using microseconds format
        if ".%f" in config.TIMESTAMP_FORMAT:
            timestamp = timestamp[:-3]
        
        # Format the log entry
        log_entry = (
            f'<span style="color: #888888;">[{timestamp}]</span> '
            f'<span style="color: {color};">[{log_type}]</span> {message}'
        )
        
        # Add to text box
        self.serial_output.append(log_entry)
        
        # Auto-scroll and limit lines
        cursor = self.serial_output.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.serial_output.setTextCursor(cursor)
        
        document = self.serial_output.document()
        if document.lineCount() > config.MAX_OUTPUT_LINES:
            cursor = self.serial_output.textCursor()
            cursor.movePosition(QTextCursor.Start)
            cursor.movePosition(QTextCursor.Down, QTextCursor.KeepAnchor, 
                              document.lineCount() - config.MAX_OUTPUT_LINES)
            cursor.removeSelectedText()
        
        # Also write to log file
        self.data_manager.write_to_log(timestamp, f"[{log_type}] {message}")
    
    def update_countdown_display(self):
        """Update the countdown timer display"""
        if not self.serial_handler or self.is_paused:
            # Show paused or no connection
            self.control_panel.update_countdown(None)
            return
        
        if self.last_query_time is None:
            # No query yet
            self.control_panel.update_countdown(None)
            return
        
        # Calculate time until next query
        elapsed = time.time() - self.last_query_time
        time_until_next = config.QUERY_INTERVAL - elapsed
        
        # Update display
        self.control_panel.update_countdown(time_until_next)
    
    def stop_all_devices(self):
        """
        Stop all connected devices and put them in a safe stopped state
        Called when program is closing or when user requests stop all
        """
        self.log_event("Stopping all devices...", color="#FF6600", log_type="SYSTEM")
        
        # Update device controller with current device information
        self.device_controller.set_pump_port(self.pump_port)
        self.device_controller.set_chiller_port(self.chiller_port)
        self.device_controller.set_tic_serials(self.tic_a_serial, self.tic_b_serial)
        
        # Call device controller to stop all devices
        self.device_controller.stop_all_devices()
        
        self.log_event("All devices stopped", color="#00FF00", log_type="SYSTEM")
        
        # Small delay to ensure all log writes complete
        import time
        time.sleep(0.1)
    
    # endregion
    
    # region EVENT HANDLERS
    
    def closeEvent(self, event):
        """Handle window close event"""
        # Show shutdown overlay
        self._show_shutdown_overlay()
        
        # Stop all devices first (this logs to files)
        self.stop_all_devices()
        
        # Stop serial handlers
        if self.serial_handler:
            self.serial_handler.stop()
        if self.ibp_ref1_handler:
            self.ibp_ref1_handler.stop()
        if self.ibp_ref2_handler:
            self.ibp_ref2_handler.stop()

        if self.ionin_storage_adapter is not None:
            self.ionin_storage_adapter.close()
        
        # Close data files LAST (after all logging is complete)
        self.data_manager.close_files()
        
        # Keep overlay visible briefly before closing
        QApplication.processEvents()
        
        event.accept()
    
    # endregion

    def _ionin_csv_path(self):
        """Return sidecar CSV path used by IonIn storage adapter."""
        if not self.data_manager or not self.data_manager.csv_file_path:
            return None
        base, ext = os.path.splitext(self.data_manager.csv_file_path)
        return f"{base}_ionin{ext}"

    def _init_ionin_storage_adapter(self):
        """Initialize/reinitialize optional IonIn storage adapter."""
        ionin_csv_path = self._ionin_csv_path()
        if not ionin_csv_path:
            return
        if self.ionin_storage_adapter is not None:
            self.ionin_storage_adapter.close()
        self.ionin_storage_adapter = IonInLegacySessionAdapter(
            ionin_csv_path,
            max_dut_units=getattr(config, "MAX_DUT_UNITS", 8),
            max_points=getattr(config, "MAX_GRAPH_POINTS", 1000),
        )
        self.log_event(
            f"IonIn storage enabled: {os.path.basename(ionin_csv_path)}",
            color="#00CED1",
            log_type="SYSTEM",
        )

    def _rows_written(self):
        """Get rows written from active writer path."""
        if self.ionin_storage_adapter is not None:
            return int(self.ionin_storage_adapter.writer.rows_written)
        return self.data_manager.get_rows_written() if self.data_manager else 0