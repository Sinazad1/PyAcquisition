"""
Analysis Mode
Provides UI for analyzing previously collected data files and generating/approving a coefficients file 

Doc status: done, MK, 01/30/2026
"""
import matplotlib
matplotlib.use('Agg') 

from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QPushButton, QLabel, QFileDialog, QTextEdit,
                               QGroupBox, QLineEdit, QMessageBox, QDialog)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPixmap
import os

from modes.utils.version import VERSION_STRING
from modes.utils import settings

# Try to import scientific libraries
try:
    import numpy as np
    import pandas as pd
    from matplotlib.backends.backend_pdf import PdfPages
    import matplotlib.pyplot as plt
    from io import BytesIO
    SCIENTIFIC_LIBS_AVAILABLE = True
except ImportError as e:
    SCIENTIFIC_LIBS_AVAILABLE = False
    IMPORT_ERROR_MSG = str(e)

# Import analysis functions from the analysis module
ANALYSIS_AVAILABLE = False
ANALYSIS_IMPORT_ERROR = ""
if SCIENTIFIC_LIBS_AVAILABLE:
    try:
        from modes.analysis import (
            read_conductivity_data,
            plot_experiment,
            gen_fit_array_from_plateaus,
            temperature_fit,
            fit_dual_range_aly_model_2,
            predict_linear
        )
        ANALYSIS_AVAILABLE = True
    except ImportError as e:
        ANALYSIS_IMPORT_ERROR = str(e)

class AnalysisWindow(QMainWindow):
    """Main window for analysis mode"""
    
    # region INITIALIZATION
    
    def __init__(self):
        """
        Initialize the analysis window.
        
        Sets up the UI for conductivity calibration analysis, including file
        selection, parameter configuration, and result visualization. Initializes
        logging and plot storage for sensor calibration data.
        """
        super().__init__()
        self.file1_path = None
        self.file2_path = None
        self.event_file1_path = None
        self.event_file2_path = None
        self.sensor_plots = {}  # Store plots for each sensor
        self.max_dut_units = max(1, int(getattr(settings, "MAX_DUT_UNITS", 6)))
        
        # Initialize log file variables (log file created when analysis runs)
        self.log_file = None
        self.log_file_path = None
        self.analysis_timestamp = None
        
        self.init_ui()
        
    def setup_log_file(self):
        """Setup log file for analysis mode"""
        from datetime import datetime
        
        # Determine save directory - use same pattern as acquisition mode
        save_directory = settings.SAVE_DIRECTORY if hasattr(settings, 'SAVE_DIRECTORY') and settings.SAVE_DIRECTORY else "."
        save_directory = os.path.expanduser(save_directory)
        save_directory = os.path.abspath(save_directory)
        
        # Create directory if it doesn't exist
        try:
            os.makedirs(save_directory, exist_ok=True)
        except Exception as e:
            print(f"Could not create save directory: {str(e)}")
            save_directory = os.getcwd()
        
        # Create timestamped log filename and store timestamp for output files
        self.analysis_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file_path = os.path.join(save_directory, f"analysis_log_{self.analysis_timestamp}.txt")
        
        # Initialize log file
        try:
            self.log_file = open(self.log_file_path, 'w', encoding='utf-8')
            self.log_file.write(f"Analysis Mode Log - Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            self.log_file.write("=" * 80 + "\n\n")
            self.log_file.flush()
            print(f"Analysis log file: {self.log_file_path}")
        except Exception as e:
            print(f"Failed to create analysis log file: {str(e)}")
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
            self.log_file.write(f"\nAnalysis Mode Log - Ended at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            self.log_file.write("=" * 80 + "\n")
            self.log_file.close()
            print(f"Analysis log file closed: {self.log_file_path}")
    
    def log_and_display(self, message):
        """Write message to both log file and output display"""
        self.write_to_log(message)
        self.output_text.append(message)

    # endregion
    
    # region UI INITIALIZATION

        
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("alyPyAcquisition - Analysis Mode")
        self.setMinimumSize(800, 600)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title = QLabel("alyPyAcquisition - Data Analysis")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)
        
        # Description
        description = QLabel(
            "Measurements mode: Select one or two measurements files (second file optional).\n"
            "Legacy mode: Select two separate DUT files from different acquisition runs.\n"
            "Event files will be automatically detected in the same directory."
        )
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(description)
        
        # File selection group
        file_group = QGroupBox("File Selection")
        file_layout = QVBoxLayout()
        file_layout.setSpacing(15)
        
        # Mode selection (Measurements vs Legacy DUT)
        mode_layout = QHBoxLayout()
        mode_label = QLabel("File Mode:")
        mode_label.setMinimumWidth(100)
        mode_layout.addWidget(mode_label)
        
        self.mode_measurements_btn = QPushButton("Measurements (Default)")
        self.mode_measurements_btn.setCheckable(True)
        self.mode_measurements_btn.setChecked(True)
        self.mode_measurements_btn.setMinimumWidth(180)
        self.mode_measurements_btn.setStyleSheet("""
            QPushButton:checked {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
            }
        """)
        self.mode_measurements_btn.clicked.connect(self.set_measurements_mode)
        mode_layout.addWidget(self.mode_measurements_btn)
        
        self.mode_legacy_btn = QPushButton("Legacy (DUT/IPB)")
        self.mode_legacy_btn.setCheckable(True)
        self.mode_legacy_btn.setMinimumWidth(180)
        self.mode_legacy_btn.clicked.connect(self.set_legacy_mode)
        mode_layout.addWidget(self.mode_legacy_btn)
        
        mode_layout.addStretch()
        file_layout.addLayout(mode_layout)
        
        # Set default mode
        self.file_mode = "measurements"  # "measurements" or "legacy"
                
        # Model selection - now showing configured model from config.ini
        model_layout = QHBoxLayout()
        model_label = QLabel("Analysis Model:")
        model_label.setMinimumWidth(100)
        model_layout.addWidget(model_label)
        
        self.model_display = QLabel(settings.ANALYSIS_MODEL)
        self.model_display.setStyleSheet("""
            QLabel {
                padding: 5px 10px;
                background-color: #f0f0f0;
                border: 1px solid #cccccc;
                border-radius: 3px;
                font-weight: bold;
                color: #000000;
            }
        """)

        model_layout.addWidget(self.model_display)
        model_layout.addStretch()
        
        file_layout.addLayout(model_layout)
        
        # File 1 selection
        file1_layout = QHBoxLayout()
        self.file1_label = QLabel("File 1:")
        self.file1_label.setMinimumWidth(100)
        file1_layout.addWidget(self.file1_label)
        
        self.file1_edit = QLineEdit()
        self.file1_edit.setReadOnly(True)
        self.file1_edit.setPlaceholderText("No file selected")
        file1_layout.addWidget(self.file1_edit)
        
        self.file1_btn = QPushButton("Browse...")
        self.file1_btn.setMinimumWidth(100)
        self.file1_btn.clicked.connect(lambda: self.select_file(1))
        file1_layout.addWidget(self.file1_btn)
        
        file_layout.addLayout(file1_layout)
        
        # File 2 selection
        self.file2_layout = QHBoxLayout()
        self.file2_label = QLabel("File 2:")
        self.file2_label.setMinimumWidth(100)
        self.file2_layout.addWidget(self.file2_label)
        
        self.file2_edit = QLineEdit()
        self.file2_edit.setReadOnly(True)
        self.file2_edit.setPlaceholderText("No file selected")
        self.file2_layout.addWidget(self.file2_edit)
        
        self.file2_btn = QPushButton("Browse...")
        self.file2_btn.setMinimumWidth(100)
        self.file2_btn.clicked.connect(lambda: self.select_file(2))
        self.file2_layout.addWidget(self.file2_btn)
        
        file_layout.addLayout(self.file2_layout)
        
        # Update labels and visibility based on initial mode
        self.update_file_labels()
                
        file_group.setLayout(file_layout)
        main_layout.addWidget(file_group)
        
        # Analysis output area
        output_group = QGroupBox("Analysis Output")
        output_layout = QVBoxLayout()
        
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setPlaceholderText(
            "Analysis results will appear here...\n\n"
            "This is a placeholder for the analysis functionality.\n"
            "Future implementation will include:\n"
            "  • Data comparison between files\n"
            "  • Statistical analysis\n"
            "  • Graphical visualization\n"
            "  • Export capabilities"
        )
        output_layout.addWidget(self.output_text)
        
        output_group.setLayout(output_layout)
        main_layout.addWidget(output_group)
        
        # Action buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        # Clear button
        self.clear_btn = QPushButton("Clear Files")
        self.clear_btn.setMinimumWidth(120)
        self.clear_btn.clicked.connect(self.clear_files)
        button_layout.addWidget(self.clear_btn)

        # Quick validation button for operator pre-checks.
        self.checklist_btn = QPushButton("8-Sensor Checklist")
        self.checklist_btn.setMinimumWidth(140)
        self.checklist_btn.clicked.connect(self.run_analysis_checklist)
        self.checklist_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                padding: 8px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
            QPushButton:pressed {
                background-color: #EF6C00;
            }
        """)
        button_layout.addWidget(self.checklist_btn)
        
        # Run analysis button (placeholder)
        self.analyze_btn = QPushButton("Run Analysis")
        self.analyze_btn.setMinimumWidth(120)
        self.analyze_btn.clicked.connect(self.run_analysis)
        self.analyze_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                padding: 8px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0b7dda;
            }
            QPushButton:pressed {
                background-color: #0970c9;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        button_layout.addWidget(self.analyze_btn)
        
        # Exit button
        self.exit_btn = QPushButton("Exit")
        self.exit_btn.setMinimumWidth(120)
        self.exit_btn.clicked.connect(self.close)
        self.exit_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                padding: 8px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
            QPushButton:pressed {
                background-color: #c41606;
            }
        """)
        button_layout.addWidget(self.exit_btn)
        
        main_layout.addLayout(button_layout)
        
        # Status bar with version info
        self.statusBar().showMessage(f"Ready - Select files to begin analysis | {VERSION_STRING}")
        
        # Add version label in bottom right corner
        self.version_label = QLabel(VERSION_STRING)
        self.version_label.setStyleSheet("""
            QLabel {
                color: #888888;
                font-size: 9pt;
                padding: 2px 5px;
            }
        """)
        self.statusBar().addPermanentWidget(self.version_label)
    
    # endregion
    
    # region FILE HANDLING
    
    def auto_detect_event_file(self, dut_file_path):
        """Auto-detect the event file based on DUT filename"""
        if not dut_file_path:
            return None
        
        # Get directory and base filename
        directory = os.path.dirname(dut_file_path)
        basename = os.path.basename(dut_file_path)
        
        # Try different naming patterns
        # Pattern 1: Replace _DUT.csv with _events.csv
        event_file1 = basename.replace("_DUT.csv", "_events.csv")
        event_path1 = os.path.join(directory, event_file1)
        if os.path.exists(event_path1):
            return event_path1
        
        # Pattern 2: Just add _events before .csv
        if basename.endswith(".csv"):
            event_file2 = basename.replace(".csv", "_events.csv")
            event_path2 = os.path.join(directory, event_file2)
            if os.path.exists(event_path2):
                return event_path2
        
        # Pattern 3: Look for file with same timestamp prefix
        # e.g., 2025_10_09_17_19_17_DUT.csv -> 2025_10_09_17_19_17_events.csv
        # Extract timestamp portion (everything before _DUT or first _ after date)
        parts = basename.split("_DUT")
        if len(parts) > 1:
            base_prefix = parts[0]
            event_file3 = f"{base_prefix}_events.csv"
            event_path3 = os.path.join(directory, event_file3)
            if os.path.exists(event_path3):
                return event_path3
        
        return None
    
    def set_measurements_mode(self):
        """Switch to measurements mode"""
        self.file_mode = "measurements"
        self.mode_measurements_btn.setChecked(True)
        self.mode_legacy_btn.setChecked(False)
        self.update_file_labels()
        self.clear_files()
        self.statusBar().showMessage("Switched to Measurements mode - Select one or two measurements_*.csv files")
    
    def set_legacy_mode(self):
        """Switch to legacy DUT/IPB mode"""
        self.file_mode = "legacy"
        self.mode_measurements_btn.setChecked(False)
        self.mode_legacy_btn.setChecked(True)
        self.update_file_labels()
        self.clear_files()
        self.statusBar().showMessage("Switched to Legacy mode - Select two *_DUT.csv files")
    
    def update_file_labels(self):
        """Update file selection labels and visibility based on current mode"""
        if self.file_mode == "measurements":
            self.file1_label.setText("Measurements File 1:")
            self.file2_label.setText("Measurements File 2 (Optional):")
            # Show File 2 in measurements mode (now optional)
            self.file2_label.show()
            self.file2_edit.show()
            self.file2_btn.show()
        else:
            self.file1_label.setText("DUT File 1:")
            self.file2_label.setText("DUT File 2:")
            # Show File 2 in legacy mode
            self.file2_label.show()
            self.file2_edit.show()
            self.file2_btn.show()
    
    def auto_detect_event_file_measurements(self, measurements_file_path):
        """
        Auto-detect the event file for measurements mode
        Looks for events_YYYYMMDD_HHMMSS.csv matching measurements_YYYYMMDD_HHMMSS.csv
        """
        directory = os.path.dirname(measurements_file_path)
        basename = os.path.basename(measurements_file_path)
        
        # Replace measurements_ prefix with events_
        if basename.startswith("measurements_"):
            event_filename = basename.replace("measurements_", "events_")
            event_path = os.path.join(directory, event_filename)
            if os.path.exists(event_path):
                return event_path
        
        return None
        
    def select_file(self, file_number):
        """Open file dialog to select a data file"""
        # Start in current working directory
        start_dir = os.getcwd()
        
        # Adjust dialog title and filter based on mode
        if self.file_mode == "measurements":
            title = f"Select Measurements File {file_number}"
            file_filter = "Measurements Files (measurements_*.csv);;CSV Files (*.csv);;All Files (*.*)"
        else:
            title = f"Select DUT Data File {file_number}"
            file_filter = "DUT Files (*_DUT.csv);;CSV Files (*.csv);;All Files (*.*)"
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            title,
            start_dir,
            file_filter
        )
        
        if file_path:
            # Log file selection
            self.write_to_log(f"File {file_number} selected: {file_path}")
            
            # Auto-detect the corresponding event file based on mode
            if self.file_mode == "measurements":
                event_file = self.auto_detect_event_file_measurements(file_path)
                file_type_name = "Measurements"
            else:
                event_file = self.auto_detect_event_file(file_path)
                file_type_name = "DUT"
            
            # In measurements mode, handle both file1 and file2 (file2 optional)
            if self.file_mode == "measurements":
                if file_number == 1:
                    self.file1_path = file_path
                    self.file1_edit.setText(file_path)
                    
                    if event_file:
                        self.event_file1_path = event_file
                        self.statusBar().showMessage(
                            f"{file_type_name} File 1 selected: {os.path.basename(file_path)} | "
                            f"Event file auto-detected: {os.path.basename(event_file)}"
                        )
                    else:
                        self.event_file1_path = None
                        self.statusBar().showMessage(
                            f"{file_type_name} File 1 selected: {os.path.basename(file_path)} | "
                            f"WARNING: Event file not found!"
                        )
                else:
                    self.file2_path = file_path
                    self.file2_edit.setText(file_path)
                    
                    if event_file:
                        self.event_file2_path = event_file
                        self.statusBar().showMessage(
                            f"{file_type_name} File 2 selected: {os.path.basename(file_path)} | "
                            f"Event file auto-detected: {os.path.basename(event_file)}"
                        )
                    else:
                        self.event_file2_path = None
                        self.statusBar().showMessage(
                            f"{file_type_name} File 2 selected: {os.path.basename(file_path)} | "
                            f"WARNING: Event file not found!"
                        )
            else:
                # Legacy mode - handle file1 and file2 separately
                if file_number == 1:
                    self.file1_path = file_path
                    self.file1_edit.setText(file_path)
                    
                    if event_file:
                        self.event_file1_path = event_file
                        self.statusBar().showMessage(
                            f"{file_type_name} File 1 selected: {os.path.basename(file_path)} | "
                            f"Event file auto-detected: {os.path.basename(event_file)}"
                        )
                    else:
                        self.event_file1_path = None
                        self.statusBar().showMessage(
                            f"{file_type_name} File 1 selected: {os.path.basename(file_path)} | "
                            f"WARNING: Event file not found!"
                        )
                else:
                    self.file2_path = file_path
                    self.file2_edit.setText(file_path)
                    
                    if event_file:
                        self.event_file2_path = event_file
                        self.statusBar().showMessage(
                            f"{file_type_name} File 2 selected: {os.path.basename(file_path)} | "
                            f"Event file auto-detected: {os.path.basename(event_file)}"
                        )
                    else:
                        self.event_file2_path = None
                        self.statusBar().showMessage(
                            f"{file_type_name} File 2 selected: {os.path.basename(file_path)} | "
                            f"WARNING: Event file not found!"
                        )
                
    def split_measurements_file(self, measurements_path, output_dir):
        """
        Split a measurements CSV into separate DUT and IPB reference files
        for compatibility with existing analysis functions.
        
        Args:
            measurements_path: Path to measurements_*.csv file
            output_dir: Directory to write temporary split files
            
        Returns:
            tuple: (dut_file_path, ipb_file_path)
        """
        import pandas as pd
        
        # Read the measurements file
        df = pd.read_csv(measurements_path)
        
        # Extract base filename for output
        basename = os.path.basename(measurements_path).replace("measurements_", "").replace(".csv", "")
        
        # Create DUT file with timestamp and DUT columns
        dut_columns = ['Timestamp']
        # Add all DUT columns based on configured unit count.
        for dut_num in range(1, self.max_dut_units + 1):
            dut_columns.extend([
                f'DUT{dut_num}_Cond_Freq_Hz',
                f'DUT{dut_num}_Cond_RzMag_Ohm',
                f'DUT{dut_num}_Cond_RzPhase_Deg',
                f'DUT{dut_num}_Temp_Freq_Hz',
                f'DUT{dut_num}_Temp_RzMag_Ohm',
                f'DUT{dut_num}_Temp_RzPhase_Deg'
            ])
        
        dut_df = df[dut_columns].copy()
        
        # Rename Timestamp column to TIMECODE for compatibility
        dut_df = dut_df.rename(columns={'Timestamp': 'TIMECODE'})
        
        # Rename DUT columns to match expected format (ConImpedance1, TempImpedance1, etc.)
        column_mapping = {}
        for dut_num in range(1, self.max_dut_units + 1):
            column_mapping[f'DUT{dut_num}_Cond_RzMag_Ohm'] = f'ConImpedance{dut_num}'
            column_mapping[f'DUT{dut_num}_Temp_RzMag_Ohm'] = f'TempImpedance{dut_num}'
        
        dut_df = dut_df.rename(columns=column_mapping)
        
        # Write DUT file
        dut_file_path = os.path.join(output_dir, f"{basename}_DUT.csv")
        dut_df.to_csv(dut_file_path, index=False)
        
        # Create IPB reference file (no header, just data)
        # Format: Sample_number, Ref1_Cond, Ref2_Cond, Ref1_Temp, Ref2_Temp
        ipb_df = pd.DataFrame({
            0: range(len(df)),  # Sample number
            1: df['Ref1_Conductivity_mS_cm'],
            2: df['Ref2_Conductivity_mS_cm'],
            3: df['Ref1_Temperature_degC'],
            4: df['Ref2_Temperature_degC']
        })
        
        # Write IPB file (no header)
        ipb_file_path = os.path.join(output_dir, f"{basename}IPB.csv")
        ipb_df.to_csv(ipb_file_path, index=False, header=False)
        
        return dut_file_path, ipb_file_path
    
    def clear_files(self):
        """Clear all selected files"""
        self.file1_path = None
        self.file2_path = None
        self.event_file1_path = None
        self.event_file2_path = None
        self.file1_edit.clear()
        self.file2_edit.clear()
        self.output_text.clear()
        self.statusBar().showMessage("Files cleared - Ready to select new files")
    
    # endregion
    
    # region ANALYSIS PROCESSING

    def run_analysis_checklist(self, show_dialog=True):
        """Validate analysis prerequisites before long-running fit work."""
        results = []
        failures = []

        def add_ok(msg):
            results.append(f"[OK] {msg}")

        def add_fail(msg):
            line = f"[MISSING] {msg}"
            results.append(line)
            failures.append(line)

        # Basic file checks.
        if self.file1_path and os.path.exists(self.file1_path):
            add_ok(f"File 1 present: {os.path.basename(self.file1_path)}")
        else:
            add_fail("File 1 is not selected or does not exist.")

        if self.file_mode == "legacy":
            if self.file2_path and os.path.exists(self.file2_path):
                add_ok(f"File 2 present: {os.path.basename(self.file2_path)}")
            else:
                add_fail("Legacy mode requires File 2.")

        if self.event_file1_path and os.path.exists(self.event_file1_path):
            add_ok(f"Event file 1 present: {os.path.basename(self.event_file1_path)}")
        else:
            add_fail("Event file 1 not found.")

        if self.file_mode == "legacy":
            if self.event_file2_path and os.path.exists(self.event_file2_path):
                add_ok(f"Event file 2 present: {os.path.basename(self.event_file2_path)}")
            else:
                add_fail("Legacy mode requires Event file 2.")

        # Measurements-mode schema check for configured DUT count.
        if self.file_mode == "measurements" and self.file1_path and os.path.exists(self.file1_path):
            if not SCIENTIFIC_LIBS_AVAILABLE:
                add_fail("Scientific libraries missing (numpy/pandas/matplotlib/scipy).")
            else:
                try:
                    preview_df = pd.read_csv(self.file1_path, nrows=1)
                    required = ["Timestamp"]
                    for dut_num in range(1, self.max_dut_units + 1):
                        required.extend([
                            f"DUT{dut_num}_Cond_Freq_Hz",
                            f"DUT{dut_num}_Cond_RzMag_Ohm",
                            f"DUT{dut_num}_Cond_RzPhase_Deg",
                            f"DUT{dut_num}_Temp_Freq_Hz",
                            f"DUT{dut_num}_Temp_RzMag_Ohm",
                            f"DUT{dut_num}_Temp_RzPhase_Deg",
                        ])
                    required.extend([
                        "Ref1_Conductivity_mS_cm",
                        "Ref2_Conductivity_mS_cm",
                        "Ref1_Temperature_degC",
                        "Ref2_Temperature_degC",
                    ])
                    missing_cols = [col for col in required if col not in preview_df.columns]
                    if missing_cols:
                        add_fail(
                            f"Measurements schema missing {len(missing_cols)} columns "
                            f"(example: {missing_cols[:3]})."
                        )
                    else:
                        add_ok(
                            f"Measurements schema includes DUT1..DUT{self.max_dut_units} columns."
                        )
                except Exception as e:
                    add_fail(f"Could not read measurements file header: {e}")

        report = "\n".join(results) if results else "No checks were run."
        self.output_text.append("")
        self.output_text.append("=" * 60)
        self.output_text.append("ANALYSIS CHECKLIST")
        self.output_text.append("=" * 60)
        self.output_text.append(report)
        self.output_text.append("")

        if failures:
            self.statusBar().showMessage("Checklist failed - fix missing items before analysis")
            if show_dialog:
                fix_hints = (
                    "\n\nQuick fixes:\n"
                    "1) Re-select the newest measurements_*.csv file.\n"
                    "2) Ensure matching events_*.csv is in the same folder.\n"
                    "3) For measurements mode, confirm DUT1..DUT"
                    f"{self.max_dut_units} columns are present."
                )
                QMessageBox.warning(
                    self,
                    "Checklist Failed",
                    "Please fix the following before running analysis:\n\n"
                    + "\n".join(failures)
                    + fix_hints
                )
            return False

        self.statusBar().showMessage("Checklist passed - ready to run analysis")
        if show_dialog:
            QMessageBox.information(
                self,
                "Checklist Passed",
                f"All checks passed for DUT1..DUT{self.max_dut_units}. Ready to run analysis."
            )
        return True
        
    def run_analysis(self): # can be optimized, but works and is verified -MK
        """Run the analysis on selected files"""
        if not self.run_analysis_checklist(show_dialog=False):
            QMessageBox.warning(
                self,
                "Checklist Required",
                "Checklist failed. Click '8-Sensor Checklist' to view missing items.\n\n"
                "Tip: most failures are missing events_*.csv or incomplete DUT columns."
            )
            return

        # Setup log file now (only when analysis is actually run)
        if self.log_file is None:
            self.setup_log_file()
        
        # Log analysis start
        self.write_to_log("="*80)
        self.write_to_log("STARTING ANALYSIS")
        self.write_to_log(f"Mode: {self.file_mode}")
        self.write_to_log(f"Analysis Model: {settings.ANALYSIS_MODEL}")
        if self.file1_path:
            self.write_to_log(f"File 1: {self.file1_path}")
        if self.file2_path:
            self.write_to_log(f"File 2: {self.file2_path}")
        self.write_to_log("="*80)
        
        # Clear previous plots
        self.sensor_plots = {}
        
        # Check if scientific libraries are available
        if not SCIENTIFIC_LIBS_AVAILABLE:
            QMessageBox.critical(
                self,
                "Missing Dependencies",
                "Required scientific computing libraries are not installed.\n\n"
                f"Error: {IMPORT_ERROR_MSG}\n\n"
                "Please install the required packages:\n\n"
                "pip install numpy pandas matplotlib scikit-learn scipy\n\n"
                "Or install all requirements:\n"
                "pip install -r requirements.txt"
            )
            return
        
        # Check if analysis library is available
        if not ANALYSIS_AVAILABLE:
            error_msg = "The analysis module could not be imported.\n\n"
            if not SCIENTIFIC_LIBS_AVAILABLE:
                error_msg += f"Scientific libraries missing: {IMPORT_ERROR_MSG}\n\n"
                error_msg += "Please install: numpy, pandas, matplotlib, scikit-learn, scipy"
            else:
                error_msg += f"Analysis import error: {ANALYSIS_IMPORT_ERROR}\n\n"
                error_msg += "Please ensure the analysis module is properly installed."
            
            QMessageBox.critical(
                self,
                "Analysis Module Not Available",
                error_msg
            )
            return
            
        # Check if files are selected
        if not self.file1_path:
            file_name = "Measurements File" if self.file_mode == "measurements" else "DUT File 1"
            QMessageBox.warning(
                self,
                "No File Selected",
                f"Please select {file_name} before running analysis."
            )
            return
        
        # In legacy mode, we need file 2
        if self.file_mode == "legacy":
            if not self.file2_path:
                QMessageBox.warning(
                    self,
                    "No File Selected",
                    "Please select DUT File 2 before running analysis."
                )
                return
        
        # Check event files
        if not self.event_file1_path:
            if self.file_mode == "measurements":
                QMessageBox.warning(
                    self,
                    "Event File Not Found",
                    f"Could not auto-detect event file for:\n{os.path.basename(self.file1_path)}\n\n"
                    f"Expected file: events_{os.path.basename(self.file1_path).replace('measurements_', '')}\n\n"
                    "Please ensure the event file is in the same directory as the measurements file."
                )
            else:
                QMessageBox.warning(
                    self,
                    "No File Selected",
                    "Event File 1 was not auto-detected. Please ensure it exists in the same directory."
                )
            return
        
        # In legacy mode, we need event file 2
        if self.file_mode == "legacy":
            if not self.event_file2_path:
                QMessageBox.warning(
                    self,
                    "No File Selected",
                    "Please select Event File 2 before running analysis."
                )
                return
        
        # Process files based on mode
        try:
            if self.file_mode == "measurements":
                # Create temporary directory for split files
                import tempfile
                import shutil
                temp_dir = tempfile.mkdtemp(prefix="analysis_temp_")
                
                # Split measurements file into DUT and IPB format
                self.log_and_display("Processing measurements file...")
                self.log_and_display(f"Splitting file: {os.path.basename(self.file1_path)}")
                dut_file1, ipb_file1 = self.split_measurements_file(self.file1_path, temp_dir)
                
                # VALIDATE DATA BEFORE PROCEEDING
                # Check if we have sufficient data points for analysis
                try:
                    # Read the DUT file to check data points
                    dut_df = pd.read_csv(dut_file1)
                    num_data_points = len(dut_df)
                    
                    # Minimum required: Need at least 6 steps with 5 points each = 30 points minimum
                    # Being conservative, let's require at least 50 points for reliable analysis
                    MIN_REQUIRED_POINTS = 50
                    
                    if num_data_points < MIN_REQUIRED_POINTS:
                        # Clean up temp directory
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        
                        QMessageBox.warning(
                            self,
                            "Insufficient Data",
                            f"The measurement file does not contain enough data points for analysis.\n\n"
                            f"Data points found: {num_data_points}\n"
                            f"Minimum required: {MIN_REQUIRED_POINTS}\n\n"
                            f"This typically means the protocol did not run long enough to collect\n"
                            f"sufficient data. Each protocol step should have multiple measurements.\n\n"
                            f"Please run a longer protocol or increase the data collection time."
                        )
                        self.log_and_display(f"ERROR: Insufficient data - {num_data_points} points (need {MIN_REQUIRED_POINTS})")
                        self.statusBar().showMessage("Analysis aborted - insufficient data")
                        return
                    
                    self.log_and_display(f"Data validation passed: {num_data_points} data points available")
                    
                except Exception as e:
                    # Clean up temp directory
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    raise Exception(f"Error validating data: {str(e)}")
                
                # Copy event file to temp directory
                event_filename = os.path.basename(self.event_file1_path)
                temp_event_path = os.path.join(temp_dir, event_filename)
                shutil.copy2(self.event_file1_path, temp_event_path)
                
                # In measurements mode, use the same file for both runs
                # This allows the analysis to work with a single acquisition
                dut_file2 = dut_file1
                ipb_file2 = ipb_file1
                
                # Set paths for analysis
                pwd1 = temp_dir + "/"
                pwd2 = temp_dir + "/"
                data_file1 = os.path.basename(dut_file1)
                data_file2 = os.path.basename(dut_file2)
                ref_file1 = os.path.basename(ipb_file1)
                ref_file2 = os.path.basename(ipb_file2)
                
                # Use same event file for both (now copied to temp dir)
                event_file1 = event_filename
                event_file2 = event_file1
                
            else:
                # Legacy mode - use DUT files directly
                pwd1 = os.path.dirname(self.file1_path) + "/"
                pwd2 = os.path.dirname(self.file2_path) + "/"
                
                data_file1 = os.path.basename(self.file1_path)
                data_file2 = os.path.basename(self.file2_path)
                
                # VALIDATE DATA BEFORE PROCEEDING
                # Check if we have sufficient data points for analysis
                try:
                    dut_df1 = pd.read_csv(self.file1_path)
                    dut_df2 = pd.read_csv(self.file2_path)
                    num_data_points_1 = len(dut_df1)
                    num_data_points_2 = len(dut_df2)
                    total_points = num_data_points_1 + num_data_points_2
                    
                    MIN_REQUIRED_POINTS = 50
                    
                    if total_points < MIN_REQUIRED_POINTS:
                        QMessageBox.warning(
                            self,
                            "Insufficient Data",
                            f"The DUT files do not contain enough data points for analysis.\n\n"
                            f"File 1 points: {num_data_points_1}\n"
                            f"File 2 points: {num_data_points_2}\n"
                            f"Total points: {total_points}\n"
                            f"Minimum required: {MIN_REQUIRED_POINTS}\n\n"
                            f"Please ensure your protocol runs long enough to collect sufficient data."
                        )
                        self.log_and_display(f"ERROR: Insufficient data - {total_points} points (need {MIN_REQUIRED_POINTS})")
                        self.statusBar().showMessage("Analysis aborted - insufficient data")
                        return
                    
                    self.log_and_display(f"Data validation passed: {total_points} total data points available")
                    
                except Exception as e:
                    raise Exception(f"Error validating data: {str(e)}")
                
                # Event files
                event_file1 = os.path.basename(self.event_file1_path)
                event_file2 = os.path.basename(self.event_file2_path)
                
                # Try to find reference files (IPB files)
                ref_file1 = data_file1.replace("_DUT.csv", "IPB.csv")
                ref_file2 = data_file2.replace("_DUT.csv", "IPB.csv")
                
                # Check if reference files exist
                if not os.path.exists(pwd1 + ref_file1):
                    raise FileNotFoundError(f"Reference file not found: {ref_file1}")
                if not os.path.exists(pwd2 + ref_file2):
                    raise FileNotFoundError(f"Reference file not found: {ref_file2}")
        
        except Exception as e:
            QMessageBox.critical(
                self,
                "File Processing Error",
                f"Error processing files: {str(e)}"
            )
            return
        
        # Extract timestamp from filename for output naming
        # This section has been moved into the mode-specific blocks above
        
        # Clear output
        self.output_text.clear()
        self.log_and_display("=" * 60)
        self.log_and_display("CONDUCTIVITY SENSOR CALIBRATION ANALYSIS")
        self.log_and_display(f"ALL SENSORS (1-{self.max_dut_units})")
        self.log_and_display("=" * 60)
        self.log_and_display("")
        
        if self.file_mode == "measurements":
            self.log_and_display(f"Mode: Measurements (single file analysis)")
            self.log_and_display(f"Measurements File: {os.path.basename(self.file1_path)}")
            self.log_and_display(f"Event File: {os.path.basename(self.event_file1_path)}")
        else:
            self.log_and_display(f"Mode: Legacy (separate DUT/IPB files)")
            self.log_and_display(f"DUT File 1: {os.path.basename(self.file1_path)}")
            self.log_and_display(f"DUT File 2: {os.path.basename(self.file2_path)}")
            self.log_and_display(f"Event File 1: {os.path.basename(self.event_file1_path)}")
            self.log_and_display(f"Event File 2: {os.path.basename(self.event_file2_path)}")
        
        self.log_and_display(f"Selected Model: {settings.ANALYSIS_MODEL}")
        self.log_and_display("")
        self.log_and_display(f"Running analysis for all {self.max_dut_units} sensors...")
        self.statusBar().showMessage("Analysis in progress...")
        
        try:
            # Use the same timestamp as the log file for output files
            analysis_timestamp = self.analysis_timestamp
            
            # Event file basenames were already set in the mode-specific blocks above
            # Create PDF output with timestamp-based naming
            output_dir = os.path.dirname(self.file1_path)
            pdf_filename = os.path.join(output_dir, f"{analysis_timestamp}_analysis.pdf")
            coef_filename = os.path.join(output_dir, f"{analysis_timestamp}_coefficients.txt")
            
            self.log_and_display(f"Creating PDF report: {pdf_filename}")
            self.log_and_display(f"Creating coefficients file: {coef_filename}")
            self.log_and_display("")
            
            # Storage for all sensor results
            all_results = []
            skipped_sensors = []
            
            # Get selected model once at the beginning
            selected_model = settings.ANALYSIS_MODEL
            
            # Open PDF and text file
            with PdfPages(pdf_filename) as pdf_pages, open(coef_filename, 'w', encoding='utf-8') as coef_file:
                # Write header to coefficient file
                coef_file.write("=" * 80 + "\n")
                coef_file.write(f"CONDUCTIVITY SENSOR CALIBRATION COEFFICIENTS\n")
                coef_file.write(f"Analysis Date: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                coef_file.write("=" * 80 + "\n\n")
                coef_file.write(f"DUT File 1: {data_file1}\n")
                coef_file.write(f"DUT File 2: {data_file2}\n")
                coef_file.write(f"Model: {settings.ANALYSIS_MODEL}\n")
                coef_file.write("\n" + "=" * 80 + "\n\n")
                
                # Loop through all configured DUT sensors.
                for sensor_id in range(1, self.max_dut_units + 1):
                    con_impedance_col = f'ConImpedance{sensor_id}'
                    temp_impedance_col = f'TempImpedance{sensor_id}'
                    sensor_label = f"Sensor {sensor_id}"
                    sensor_id_display = f"J{sensor_id}"  # Display as J1, J2, etc.
                    
                    self.log_and_display("=" * 60)
                    self.log_and_display(f"PROCESSING SENSOR {sensor_id}")
                    self.log_and_display("=" * 60)
                    self.statusBar().showMessage(
                        f"Analyzing Sensor {sensor_id}/{self.max_dut_units}..."
                    )
                    
                    try:
                        # Read data from both experiments
                        self.log_and_display(f"Loading data for Sensor {sensor_id}...")
                        d_impedance_1, pt1000_imp_1, ref_con_1_1, ref_con_2_1, ref_temp_1_1, ref_temp_2_1, ref_temp_avg_1, step_idx_1 = read_conductivity_data(
                            pwd1, data_file1, ref_file1, event_file1, 
                            con_impedance_col, temp_impedance_col
                        )
                        
                        d_impedance_2, pt1000_imp_2, ref_con_1_2, ref_con_2_2, ref_temp_1_2, ref_temp_2_2, ref_temp_avg_2, step_idx_2 = read_conductivity_data(
                            pwd2, data_file2, ref_file2, event_file2,
                            con_impedance_col, temp_impedance_col
                        )
                        
                        # Combine data from both experiments
                        d_impedance = np.concatenate([d_impedance_1, d_impedance_2])
                        pt1000_imp = np.concatenate([pt1000_imp_1, pt1000_imp_2])
                        ref_con_1 = np.concatenate([ref_con_1_1, ref_con_1_2])
                        ref_con_2 = np.concatenate([ref_con_2_1, ref_con_2_2])
                        ref_temp_1 = np.concatenate([ref_temp_1_1, ref_temp_1_2])
                        ref_temp_2 = np.concatenate([ref_temp_2_1, ref_temp_2_2])
                        ref_temp_avg = np.concatenate([ref_temp_avg_1, ref_temp_avg_2])
                        
                        # Adjust step indices for second experiment
                        step_idx_2_adjusted = [idx + len(d_impedance_1) for idx in step_idx_2]
                        step_idx = step_idx_1 + step_idx_2_adjusted
                        
                        # Create experiment labels (1 for first experiment, 2 for second)
                        step_lbl = np.array([1]*len(step_idx_1) + [2]*len(step_idx_2))
                        
                        # Skip sensors with non-finite or non-physical data before fitting.
                        finite_mask = (
                            np.isfinite(d_impedance)
                            & np.isfinite(pt1000_imp)
                            & np.isfinite(ref_con_1)
                            & np.isfinite(ref_con_2)
                            & np.isfinite(ref_temp_1)
                            & np.isfinite(ref_temp_2)
                            & np.isfinite(ref_temp_avg)
                        )
                        positive_mask = (d_impedance > 0) & (pt1000_imp > 0)
                        valid_mask = finite_mask & positive_mask
                        valid_points = int(np.sum(valid_mask))
                        total_points = int(len(d_impedance))
                        invalid_points = total_points - valid_points
                        min_points_required = 40

                        if invalid_points > 0 or valid_points < min_points_required:
                            skip_reason = (
                                f"Insufficient valid points ({valid_points}/{total_points}); "
                                f"invalid or non-physical points={invalid_points}"
                            )
                            self.log_and_display(
                                f"SKIP Sensor {sensor_id}: {skip_reason}"
                            )
                            coef_file.write(
                                f"SKIP: Sensor {sensor_id} analysis skipped\n"
                            )
                            coef_file.write(f"      {skip_reason}\n\n")
                            coef_file.write("=" * 80 + "\n\n")
                            skipped_sensors.append((sensor_id_display, skip_reason))
                            continue

                        # Plot experimental data
                        self.log_and_display("Plotting experimental data...")
                        plot_experiment(ref_con_1, ref_con_2, ref_temp_1, ref_temp_2, 
                                      d_impedance, pt1000_imp, sensor_label, pdf_pages)
                        
                        # Generate fit arrays
                        self.log_and_display("Extracting plateau data for fitting...")
                        d_plateau_fit, ref_plateau_fit, temp_fit, ref_temp_mean_fit, ref1_fit, ref2_fit, ref_temp1_fit, ref_temp2_fit = gen_fit_array_from_plateaus(
                            d_impedance, ref_con_1, ref_con_2, pt1000_imp, 
                            ref_temp_1, ref_temp_2, step_idx
                        )
                        
                        # Expand step labels to match plateau data
                        step_lbl_expanded = np.repeat(step_lbl, 5)
                        
                        # Temperature fit
                        self.log_and_display("Running temperature calibration...")
                        model_t, temp_percent_error, temp_mae, temp_max_err, temp_std_err = temperature_fit(
                            temp_fit, ref_temp_mean_fit, sensor_label, pdf_pages
                        )
                        
                        # Convert temperature to actual temperature values
                        sensor_temperature = predict_linear(temp_fit.reshape(-1, 1), model_t.coef_, model_t.intercept_)
                        
                        # Store results for this sensor
                        sensor_results = {
                            'sensor_id': sensor_id_display,
                            'sensor_label': sensor_label,
                            'temp_scale': model_t.coef_[0],
                            'temp_offset': model_t.intercept_,
                            'temp_mae': temp_mae,
                            'temp_max_err': temp_max_err,
                            'temp_std_err': temp_std_err
                        }
                        
                        # Write temperature results to coefficient file
                        coef_file.write(f"SENSOR {sensor_id}\n")
                        coef_file.write("-" * 80 + "\n\n")
                        coef_file.write("TEMPERATURE CALIBRATION:\n")
                        coef_file.write(f"  Scale: {model_t.coef_[0]:.10f}\n")
                        coef_file.write(f"  Offset: {model_t.intercept_:.10f}\n")
                        coef_file.write(f"  Mean Absolute Error: {temp_mae:.4f}%\n")
                        coef_file.write(f"  Max Error: {temp_max_err:.4f}%\n")
                        coef_file.write(f"  Std Dev Error: {temp_std_err:.4f}%\n\n")
                        
                        # Run Dual-Range Aly Model 2 (ONLY MODEL AVAILABLE)
                        # Note: Model selection logic retained for future extensibility
                        # but currently only Dual-Range Aly Model 2 is implemented -MK, 01/30/2026
                        self.log_and_display("Running Dual-Range Aly Model 2...")
                        constrain_low = settings.CONSTRAIN_LOW_RANGE
                        self.log_and_display(f"  Low range constraint: {'Enabled (eta=1, zeta=0)' if constrain_low else 'Disabled'}")
                        
                        result = fit_dual_range_aly_model_2(
                            d_plateau_fit, sensor_temperature, ref_plateau_fit,
                            sensor_label, step_lbl_expanded, pdf_pages,
                            constrain_low_range=constrain_low
                        )
                        
                        (K_high, alpha_high, eta_high, zeta_high,
                         K_low, alpha_low, eta_low, zeta_low,
                         K_global, alpha_global, eta_global, zeta_global,
                         mean_err_high, abs_mean_err_high, std_err_high, max_err_high,
                         mean_err_low, abs_mean_err_low, std_err_low, max_err_low,
                         mean_err_global, abs_mean_err_global, std_err_global, max_err_global,
                         mean_err_comb, abs_mean_err_comb, std_err_comb, max_err_comb,
                         _, _, plot_img) = result
                        
                        # Store plot data for this sensor
                        self.sensor_plots[sensor_id_display] = plot_img
                        
                        # Store results
                        sensor_results['dual_K_high'] = K_high
                        sensor_results['dual_alpha_high'] = alpha_high
                        sensor_results['dual_eta_high'] = eta_high
                        sensor_results['dual_zeta_high'] = zeta_high
                        sensor_results['dual_mae_high'] = abs_mean_err_high
                        
                        sensor_results['dual_K_low'] = K_low
                        sensor_results['dual_alpha_low'] = alpha_low
                        sensor_results['dual_eta_low'] = eta_low
                        sensor_results['dual_zeta_low'] = zeta_low
                        sensor_results['dual_mae_low'] = abs_mean_err_low
                        
                        sensor_results['dual_K_global'] = K_global
                        sensor_results['dual_alpha_global'] = alpha_global
                        sensor_results['dual_eta_global'] = eta_global
                        sensor_results['dual_zeta_global'] = zeta_global
                        sensor_results['dual_mae_global'] = abs_mean_err_global
                        
                        sensor_results['dual_mae_combined'] = abs_mean_err_comb
                        
                        # Write to coefficient file
                        coef_file.write("DUAL-RANGE ALY MODEL 2:\n")
                        coef_file.write("-" * 80 + "\n")
                        coef_file.write("HIGH RANGE (C > 0.002 S/cm):\n")
                        coef_file.write(f"  K: {K_high:.10f}\n")
                        coef_file.write(f"  Alpha: {alpha_high:.10f}\n")
                        coef_file.write(f"  Eta: {eta_high:.10f}\n")
                        coef_file.write(f"  Zeta: {zeta_high:.10f}\n")
                        coef_file.write(f"  Mean Absolute Error: {abs_mean_err_high:.4f}%\n")
                        coef_file.write(f"  Std Dev Error: {std_err_high:.4f}%\n")
                        coef_file.write(f"  Max Absolute Error: {max_err_high:.4f}%\n\n")
                        
                        coef_file.write("LOW RANGE (C <= 0.002 S/cm):\n")
                        if constrain_low:
                            coef_file.write("  (Constrained model: eta=1, zeta=0)\n")
                        coef_file.write(f"  K: {K_low:.10f}\n")
                        coef_file.write(f"  Alpha: {alpha_low:.10f}\n")
                        coef_file.write(f"  Eta: {eta_low:.10f}\n")
                        coef_file.write(f"  Zeta: {zeta_low:.10f}\n")
                        coef_file.write(f"  Mean Absolute Error: {abs_mean_err_low:.4f}%\n")
                        coef_file.write(f"  Std Dev Error: {std_err_low:.4f}%\n")
                        coef_file.write(f"  Max Absolute Error: {max_err_low:.4f}%\n\n")
                        
                        coef_file.write("GLOBAL MODEL (All Data - For Prospective Discrimination):\n")
                        coef_file.write(f"  K: {K_global:.10f}\n")
                        coef_file.write(f"  Alpha: {alpha_global:.10f}\n")
                        coef_file.write(f"  Eta: {eta_global:.10f}\n")
                        coef_file.write(f"  Zeta: {zeta_global:.10f}\n")
                        coef_file.write(f"  Mean Absolute Error: {abs_mean_err_global:.4f}%\n")
                        coef_file.write(f"  Std Dev Error: {std_err_global:.4f}%\n")
                        coef_file.write(f"  Max Absolute Error: {max_err_global:.4f}%\n\n")
                        
                        coef_file.write("COMBINED MODEL PERFORMANCE (Range-Specific Models):\n")
                        coef_file.write(f"  Mean Absolute Error: {abs_mean_err_comb:.4f}%\n")
                        coef_file.write(f"  Std Dev Error: {std_err_comb:.4f}%\n")
                        coef_file.write(f"  Max Absolute Error: {max_err_comb:.4f}%\n\n")
                        
                        all_results.append(sensor_results)
                        coef_file.write("\n" + "=" * 80 + "\n\n")
                        
                        self.log_and_display(f"Sensor {sensor_id} analysis complete!")
                        self.log_and_display("")
                        
                    except Exception as e:
                        error_msg = str(e)
                        
                        # Check if this is a LAPACK/BLAS error (common with insufficient data)
                        if "DLASCLS" in error_msg or "illegal value" in error_msg.lower():
                            error_msg = (
                                f"Numerical analysis error - likely insufficient data points.\n"
                                f"Sensor {sensor_id} may not have enough valid measurements.\n"
                                f"Original error: {error_msg}"
                            )
                        
                        self.log_and_display(f"ERROR analyzing Sensor {sensor_id}: {error_msg}")
                        self.log_and_display("")
                        coef_file.write(f"ERROR: Sensor {sensor_id} analysis failed\n")
                        coef_file.write(f"       {error_msg}\n\n")
                        coef_file.write("=" * 80 + "\n\n")
                        continue
                
                # Write summary table to coefficient file
                coef_file.write("\n" + "=" * 80 + "\n")
                coef_file.write("SUMMARY TABLE - ALL SENSORS\n")
                coef_file.write("=" * 80 + "\n\n")
                
                if selected_model == "All Models" or selected_model == "Standard Model":
                    coef_file.write("STANDARD MODEL SUMMARY:\n")
                    coef_file.write("-" * 80 + "\n")
                    coef_file.write(f"{'Sensor':<10} {'K':>15} {'Alpha':>15} {'MAE (%)':>15}\n")
                    coef_file.write("-" * 80 + "\n")
                    for res in all_results:
                        if 'std_K' in res:
                            coef_file.write(f"{res['sensor_id']:<10} {res['std_K']:>15.10f} {res['std_alpha']:>15.10f} {res['std_mae']:>15.4f}\n")
                    coef_file.write("\n")
                
                if selected_model == "All Models" or selected_model == "Standard Model 2 (4-parameter)":
                    coef_file.write("STANDARD MODEL 2 SUMMARY:\n")
                    coef_file.write("-" * 80 + "\n")
                    coef_file.write(f"{'Sensor':<10} {'K':>12} {'Alpha':>12} {'Eta':>12} {'Zeta':>12} {'MAE (%)':>12}\n")
                    coef_file.write("-" * 80 + "\n")
                    for res in all_results:
                        if 'std2_K' in res:
                            coef_file.write(f"{res['sensor_id']:<10} {res['std2_K']:>12.6f} {res['std2_alpha']:>12.6f} {res['std2_eta']:>12.6f} {res['std2_zeta']:>12.6f} {res['std2_mae']:>12.4f}\n")
                    coef_file.write("\n")
                
                if selected_model == "Dual-Range Aly Model 2":
                    coef_file.write("DUAL-RANGE ALY MODEL 2 SUMMARY:\n")
                    coef_file.write("=" * 80 + "\n")
                    coef_file.write("HIGH RANGE (C > 0.002 S/cm):\n")
                    coef_file.write("-" * 80 + "\n")
                    coef_file.write(f"{'Sensor':<10} {'K':>12} {'Alpha':>12} {'Eta':>12} {'Zeta':>12} {'MAE (%)':>12}\n")
                    coef_file.write("-" * 80 + "\n")
                    for res in all_results:
                        if 'dual_K_high' in res:
                            coef_file.write(f"{res['sensor_id']:<10} {res['dual_K_high']:>12.6f} {res['dual_alpha_high']:>12.6f} {res['dual_eta_high']:>12.6f} {res['dual_zeta_high']:>12.6f} {res['dual_mae_high']:>12.4f}\n")
                    coef_file.write("\n")
                    
                    coef_file.write("LOW RANGE (C <= 0.002 S/cm):\n")
                    coef_file.write("-" * 80 + "\n")
                    coef_file.write(f"{'Sensor':<10} {'K':>12} {'Alpha':>12} {'Eta':>12} {'Zeta':>12} {'MAE (%)':>12}\n")
                    coef_file.write("-" * 80 + "\n")
                    for res in all_results:
                        if 'dual_K_low' in res:
                            coef_file.write(f"{res['sensor_id']:<10} {res['dual_K_low']:>12.6f} {res['dual_alpha_low']:>12.6f} {res['dual_eta_low']:>12.6f} {res['dual_zeta_low']:>12.6f} {res['dual_mae_low']:>12.4f}\n")
                    coef_file.write("\n")
                    
                    coef_file.write("GLOBAL MODEL (All Data - For Prospective Discrimination):\n")
                    coef_file.write("-" * 80 + "\n")
                    coef_file.write(f"{'Sensor':<10} {'K':>12} {'Alpha':>12} {'Eta':>12} {'Zeta':>12} {'MAE (%)':>12}\n")
                    coef_file.write("-" * 80 + "\n")
                    for res in all_results:
                        if 'dual_K_global' in res:
                            coef_file.write(f"{res['sensor_id']:<10} {res['dual_K_global']:>12.6f} {res['dual_alpha_global']:>12.6f} {res['dual_eta_global']:>12.6f} {res['dual_zeta_global']:>12.6f} {res['dual_mae_global']:>12.4f}\n")
                    coef_file.write("\n")
                    
                    coef_file.write("COMBINED MODEL PERFORMANCE (Range-Specific Models):\n")
                    coef_file.write("-" * 80 + "\n")
                    coef_file.write(f"{'Sensor':<10} {'Combined MAE (%)':>20}\n")
                    coef_file.write("-" * 80 + "\n")
                    for res in all_results:
                        if 'dual_mae_combined' in res:
                            coef_file.write(f"{res['sensor_id']:<10} {res['dual_mae_combined']:>20.4f}\n")
                    coef_file.write("\n")
                
                coef_file.write("=" * 80 + "\n")
                coef_file.write("END OF REPORT\n")
                coef_file.write("=" * 80 + "\n")
            
            # Determine final run verdict for operator-friendly reporting.
            if len(all_results) == self.max_dut_units and not skipped_sensors:
                run_verdict = "PASS"
            elif len(all_results) == 0:
                run_verdict = "FAIL"
            else:
                run_verdict = "PARTIAL"

            # Display final summary in output panel
            self.log_and_display("")
            self.log_and_display("=" * 60)
            self.log_and_display("ANALYSIS COMPLETE - ALL SENSORS")
            self.log_and_display("=" * 60)
            self.log_and_display(f"Result: {run_verdict}")
            self.log_and_display(
                f"Sensors analyzed: {len(all_results)}/{self.max_dut_units}"
            )
            if skipped_sensors:
                self.log_and_display(
                    f"Sensors skipped (invalid data): {len(skipped_sensors)}"
                )
                for sensor_id_display, reason in skipped_sensors:
                    self.log_and_display(f"  - {sensor_id_display}: {reason}")
            self.log_and_display(f"PDF report: {pdf_filename}")
            self.log_and_display(f"Coefficients file: {coef_filename}")
            self.log_and_display("")
            
            # Store for later use in acceptance dialog
            self.all_sensor_results = all_results
            self.coef_filename = coef_filename

            # region optional cloudHook
            # potential spot to add cloud hook, once analysis is complete. 
            # end region
            
            # Show summary table in output
            if selected_model == "All Models" or selected_model == "Standard Model":
                self.log_and_display("STANDARD MODEL SUMMARY:")
                self.log_and_display(f"{'Sensor':<10} {'K':>15} {'Alpha':>15} {'MAE (%)':>15}")
                self.log_and_display("-" * 60)
                for res in all_results:
                    if 'std_K' in res:
                        self.log_and_display(f"{res['sensor_id']:<10} {res['std_K']:>15.6f} {res['std_alpha']:>15.6f} {res['std_mae']:>15.4f}")
                self.log_and_display("")
            
            if selected_model == "Dual-Range Aly Model 2":
                self.log_and_display("DUAL-RANGE ALY MODEL 2 - COMBINED PERFORMANCE:")
                self.log_and_display(f"{'Sensor':<10} {'Combined MAE (%)':>20}")
                self.log_and_display("-" * 60)
                for res in all_results:
                    if 'dual_mae_combined' in res:
                        self.log_and_display(f"{res['sensor_id']:<10} {res['dual_mae_combined']:>20.4f}")
                self.log_and_display("")
            
            # Display plots in UI if we captured them (Standard Model 2 or Dual-Range)
            if self.sensor_plots:
                self.display_sensor_plots()
            
            self.statusBar().showMessage(
                f"Analysis complete - {run_verdict} "
                f"({len(all_results)}/{self.max_dut_units} analyzed)"
            )
            
            QMessageBox.information(
                self,
                "Analysis Complete",
                f"Calibration analysis completed for all sensors.\n\n"
                f"Result: {run_verdict}\n"
                f"PDF report: {os.path.basename(pdf_filename)}\n"
                f"Coefficients: {os.path.basename(coef_filename)}\n\n"
                f"Successfully analyzed {len(all_results)}/{self.max_dut_units} sensors.\n"
                f"Skipped due to invalid data: {len(skipped_sensors)}\n"
                f"Review the output panel and files for detailed results."
            )
            
        except Exception as e:
            self.log_and_display("")
            self.log_and_display("=" * 60)
            self.log_and_display("ERROR")
            self.log_and_display("=" * 60)
            self.log_and_display(f"An error occurred during analysis:")
            self.log_and_display(str(e))
            
            self.statusBar().showMessage("Analysis failed!")
            
            QMessageBox.critical(
                self,
                "Analysis Error",
                f"An error occurred during analysis:\n\n{str(e)}"
            )
        
        finally:
            # Cleanup temporary files if in measurements mode
            if self.file_mode == "measurements" and 'temp_dir' in locals():
                try:
                    import shutil
                    shutil.rmtree(temp_dir)
                except Exception as cleanup_error:
                    print(f"Warning: Could not clean up temporary directory: {cleanup_error}")
        
    # endregion
    
    # region DISPLAY AND REVIEW
    
    def display_sensor_plots(self):
        """Display sensor plots one at a time for review and acceptance"""
        if not self.sensor_plots:
            return
        
        # Dictionary to store acceptance status
        self.calibration_acceptance = {}
        
        # Get all results for coefficient display
        all_results = self.all_sensor_results if hasattr(self, 'all_sensor_results') else []
        
        # Sort sensor IDs
        sensor_ids = sorted(self.sensor_plots.keys())
        
        # Show each sensor sequentially
        for sensor_id in sensor_ids:
            plot_data = self.sensor_plots[sensor_id]
            
            # Find the coefficients for this sensor
            coefficients = {}
            for result in all_results:
                if result.get('sensor_id') == sensor_id:
                    coefficients = result
                    break
            
            # Show review dialog
            dialog = SensorCalibrationReviewDialog(sensor_id, plot_data, coefficients, self)
            dialog.exec()
            
            # Store acceptance status
            self.calibration_acceptance[sensor_id] = dialog.accepted
        
        # Update coefficients file with acceptance status
        self.update_coefficients_with_acceptance()
        
        # Show summary
        self.show_acceptance_summary()
    
    def update_coefficients_with_acceptance(self):
        """Update the coefficients file with acceptance status"""
        if not hasattr(self, 'coef_filename') or not self.calibration_acceptance:
            return
        
        try:
            # Read current file
            with open(self.coef_filename, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Add acceptance section at the end
            with open(self.coef_filename, 'a', encoding='utf-8') as f:
                f.write("\n" + "=" * 80 + "\n")
                f.write("CALIBRATION ACCEPTANCE STATUS\n")
                f.write("=" * 80 + "\n\n")
                
                for sensor_id in sorted(self.calibration_acceptance.keys()):
                    accepted = self.calibration_acceptance[sensor_id]
                    status = "ACCEPTED" if accepted else "REJECTED"
                    f.write(f"{sensor_id}: {status}\n")
                
                f.write("\n" + "=" * 80 + "\n")
                
            self.log_and_display("")
            self.log_and_display("Calibration acceptance status saved to coefficients file")
            
        except Exception as e:
            self.log_and_display(f"Error updating coefficients file: {str(e)}")
    
    def show_acceptance_summary(self):
        """Show summary of acceptance decisions"""
        if not self.calibration_acceptance:
            return
        
        accepted_count = sum(1 for v in self.calibration_acceptance.values() if v)
        rejected_count = sum(1 for v in self.calibration_acceptance.values() if not v)
        
        summary = f"\n{'=' * 60}\n"
        summary += "CALIBRATION ACCEPTANCE SUMMARY\n"
        summary += f"{'=' * 60}\n\n"
        
        for sensor_id in sorted(self.calibration_acceptance.keys()):
            accepted = self.calibration_acceptance[sensor_id]
            status = "ACCEPTED" if accepted else "REJECTED"
            summary += f"{sensor_id}: {status}\n"
        
        summary += f"\nTotal Accepted: {accepted_count}\n"
        summary += f"Total Rejected: {rejected_count}\n"
        summary += f"{'=' * 60}\n"
        
        self.log_and_display(summary)
        
        # Show message box summary
        msg = QMessageBox(self)
        msg.setWindowTitle("Calibration Review Complete")
        msg.setText(f"Calibration review completed for all sensors.\n\n"
                   f"Accepted: {accepted_count}\n"
                   f"Rejected: {rejected_count}\n\n"
                   f"Results saved to coefficients file.")
        msg.setIcon(QMessageBox.Information)
        msg.exec()
    
    # endregion
    
    # region EVENT HANDLERS
         
    def closeEvent(self, event):
        """Handle window close event"""
        self.close_log_file()
        event.accept()
    
    # endregion

class SensorCalibrationReviewDialog(QDialog):
    """Dialog to review and accept/reject calibration for a single sensor"""
    
    def __init__(self, sensor_id, plot_data, coefficients, parent=None):
        """
        Initialize the sensor calibration review dialog.
        
        Creates a dialog for reviewing calibration results of a single sensor,
        displaying plots and coefficients with accept/reject options.
        
        Args:
            sensor_id (str): Identifier for the sensor being reviewed.
            plot_data (bytes): PNG image data of calibration plots.
            coefficients (dict): Dictionary containing calibration coefficients.
            parent (QWidget, optional): Parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.sensor_id = sensor_id
        self.plot_data = plot_data
        self.coefficients = coefficients
        self.accepted = None  # Will be True (accept) or False (reject)
        self.init_ui()
        
    def init_ui(self):
        """Initialize the dialog UI"""
        self.setWindowTitle(f"Calibration Review - {self.sensor_id}")
        self.setMinimumSize(900, 800)
        
        # Main layout
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Sensor label (top left)
        sensor_label = QLabel(self.sensor_id)
        sensor_label_font = QFont()
        sensor_label_font.setPointSize(16)
        sensor_label_font.setBold(True)
        sensor_label.setFont(sensor_label_font)
        layout.addWidget(sensor_label)
        
        # Plot area
        plot_label = QLabel()
        pixmap = QPixmap()
        pixmap.loadFromData(self.plot_data)
        scaled_pixmap = pixmap.scaled(850, 500, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        plot_label.setPixmap(scaled_pixmap)
        plot_label.setAlignment(Qt.AlignCenter)
        plot_label.setStyleSheet("""
            QLabel {
                border: 2px solid #cccccc;
                background-color: white;
                padding: 10px;
            }
        """)
        layout.addWidget(plot_label)
        
        # Coefficients section
        coef_label = QLabel("Output")
        coef_label_font = QFont()
        coef_label_font.setPointSize(12)
        coef_label_font.setBold(True)
        coef_label.setFont(coef_label_font)
        coef_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(coef_label)
        
        # Coefficients display
        coef_text = QTextEdit()
        coef_text.setReadOnly(True)
        coef_text.setMaximumHeight(150)
        coef_text.setStyleSheet("""
            QTextEdit {
                background-color: #000000;
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 10px;
                font-family: monospace;
                color: #ffffff;
            }
        """)
        
        # Format coefficients - Only Dual-Range Aly Model 2 is available
        coef_content = ""
        
        if 'temp_scale' in self.coefficients:
            coef_content += "TEMPERATURE CALIBRATION:\n"
            coef_content += f"  Scale:  {self.coefficients['temp_scale']:.10f}\n"
            coef_content += f"  Offset: {self.coefficients['temp_offset']:.10f}\n"
            coef_content += f"\n  Mean Absolute Error: {self.coefficients['temp_mae']:.4f}%\n"
        
        if 'dual_K_high' in self.coefficients:
            if coef_content:
                coef_content += "\n"
            coef_content += "DUAL-RANGE ALY MODEL 2:\n"
            coef_content += "HIGH RANGE (C > 0.002 S/cm):\n"
            coef_content += f"  K:     {self.coefficients['dual_K_high']:.10f} "
            coef_content += f"  Alpha: {self.coefficients['dual_alpha_high']:.10f} "
            coef_content += f"  Eta:   {self.coefficients['dual_eta_high']:.10f} "
            coef_content += f"  Zeta:  {self.coefficients['dual_zeta_high']:.10f} "
            coef_content += f"\n  Mean Absolute Error: {self.coefficients['dual_mae_high']:.4f}%\n"
            
            coef_content += "\nLOW RANGE (C <= 0.002 S/cm):\n"
            coef_content += f"  K:     {self.coefficients['dual_K_low']:.10f} "
            coef_content += f"  Alpha: {self.coefficients['dual_alpha_low']:.10f} "
            coef_content += f"  Eta:   {self.coefficients['dual_eta_low']:.10f} "
            coef_content += f"  Zeta:  {self.coefficients['dual_zeta_low']:.10f} "
            coef_content += f"\n  Mean Absolute Error: {self.coefficients['dual_mae_low']:.4f}%\n"
            
            coef_content += "\nCOMBINED PERFORMANCE:\n"
            coef_content += f"  Mean Absolute Error: {self.coefficients['dual_mae_combined']:.4f}%\n"
        
        coef_text.setText(coef_content)
        layout.addWidget(coef_text)
        
        # Accept/Reject buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        accept_btn = QPushButton("ACCEPT")
        accept_btn.setMinimumSize(200, 80)
        accept_btn.clicked.connect(self.on_accept)
        accept_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-size: 16px;
                font-weight: bold;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        """)
        button_layout.addWidget(accept_btn)
        
        button_layout.addSpacing(50)
        
        reject_btn = QPushButton("REJECT")
        reject_btn.setMinimumSize(200, 80)
        reject_btn.clicked.connect(self.on_reject)
        reject_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-size: 16px;
                font-weight: bold;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
            QPushButton:pressed {
                background-color: #c41606;
            }
        """)
        button_layout.addWidget(reject_btn)
        
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
    def on_accept(self):
        """Handle accept button click"""
        self.accepted = True
        self.accept()
        
    def on_reject(self):
        """Handle reject button click"""
        self.accepted = False
        self.accept()
