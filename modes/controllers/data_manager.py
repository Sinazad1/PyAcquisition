"""
Data Manager Module (within Acquisition Mode)
Handles all data storage, CSV writing, and log file operations
Now stores complete measurement data including frequency and phase

Doc status: done, MK, 01/30/2026
"""
import csv
import os
from datetime import datetime
from PySide6.QtWidgets import QMessageBox, QFileDialog

# Import configuration settings
try:
    from modes.utils.config import (TIMESTAMP_FORMAT, SAVE_DIRECTORY, MAX_GRAPH_POINTS, MAX_DUT_UNITS)
except ImportError:
    TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S.%f"
    SAVE_DIRECTORY = "./data"
    MAX_GRAPH_POINTS = 1000
    MAX_DUT_UNITS = 8

class DataManager:
    """Manages data storage, CSV files, and log files for acquisition mode"""
    
    def __init__(self, parent=None):
        """
        Initialize the data manager.
        
        Sets up data structures for storing and managing acquisition data from
        multiple DUT units and reference sensors. Initializes CSV and log file
        handling.
        
        Args:
            parent (QWidget, optional): Parent widget (AcquisitionWindow).
                Defaults to None.
        """
        self.parent = parent
        self.max_dut_units = max(1, int(MAX_DUT_UNITS))
        
        # File paths and handles
        self.save_directory = None
        self.csv_file_path = None
        self.log_file_path = None
        self.csv_file = None
        self.csv_writer = None
        self.log_file = None
        self.rows_written = 0
        
        # Data structure for DUT devices (up to MAX_DUT_UNITS units)
        # Each unit tracks: timestamps, conductivity (freq, mag, phase), temperature (freq, mag, phase)
        self.unit_data = {
            unit_id: {
                'timestamps': [],
                'conductivity_freq': [],
                'conductivity_rzmag': [],
                'conductivity_rzphase': [],
                'conductivity_s_cm': [],
                'temperature_freq': [],
                'temperature_rzmag': [],
                'temperature_rzphase': []
            }
            for unit_id in range(1, self.max_dut_units + 1)
        }
        
        # Data structure for reference devices (2 devices)
        self.reference_data = {
            ref_id: {
                'timestamps': [],
                'conductivity_freq': [],
                'conductivity_rzmag': [],
                'conductivity_rzphase': [],
                'temperature_freq': [],
                'temperature_rzmag': [],
                'temperature_rzphase': []
            }
            for ref_id in range(1, 3)
        }
        
        # Setup save files
        self.setup_save_files()
    
    def setup_save_files(self):
        """Setup save files using directory from config"""
        # Use save directory from config, or prompt if None
        if SAVE_DIRECTORY is None:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Information)
            msg.setText("Select Save Location")
            msg.setInformativeText("Choose a directory to save measurement data (CSV) and log files.")
            msg.setWindowTitle("Save Location")
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec()
            
            self.save_directory = QFileDialog.getExistingDirectory(
                self.parent,
                "Select Save Directory",
                os.path.expanduser("~"),
                QFileDialog.ShowDirsOnly
            )
            
            if not self.save_directory:
                self.save_directory = "."
        else:
            self.save_directory = SAVE_DIRECTORY
        
        # Expand special paths and convert to absolute
        self.save_directory = os.path.expanduser(self.save_directory)
        self.save_directory = os.path.abspath(self.save_directory)
        
        # Create directory if it doesn't exist
        try:
            os.makedirs(self.save_directory, exist_ok=True)
            print(f"Save directory: {self.save_directory}")
        except Exception as e:
            if self.parent:
                QMessageBox.critical(self.parent, "Error", f"Could not create save directory: {str(e)}")
            self.save_directory = os.getcwd()
        
        # Create timestamped filenames
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.csv_file_path = os.path.join(self.save_directory, f"measurements_{timestamp}.csv")
        self.log_file_path = os.path.join(self.save_directory, f"serial_log_{timestamp}.txt")
        
        # Initialize CSV/log files with deterministic schema and encoding.
        try:
            self._open_output_files()
            
            print(f"CSV file: {self.csv_file_path}")
            print(f"Log file: {self.log_file_path}")
        except Exception as e:
            if self.parent:
                QMessageBox.critical(self.parent, "Error", f"Failed to create save files: {str(e)}")
    
    def write_to_log(self, timestamp, data):
        """Write timestamped data to log file"""
        if self.log_file and not self.log_file.closed:
            try:
                self.log_file.write(f"[{timestamp}] {data}\n")
                self.log_file.flush()
            except Exception as e:
                print(f"Error writing to log file: {e}")
    
    def write_consolidated_row(self, timestamp, dut_measurements, ref_measurements):
        """
        Write all measurements for a timestamp as a single consolidated row
        
        Args:
            timestamp: ISO format timestamp string
            dut_measurements: dict mapping unit_id (1-7) to {'conductivity': {...}, 'temperature': {...}}
            ref_measurements: dict mapping ref_id (1-2) to {'conductivity_value': float, 'temperature_value': float}
                             where conductivity_value is in mS/cm and temperature_value is in °C
        """
        if self.csv_writer and self.csv_file:
            try:
                # Use the provided measurement timestamp for consistent logging/CSV timing.
                iso_timestamp = timestamp
                
                # Build the row
                row = [iso_timestamp]
                
                # Add DUT units (1..MAX_DUT_UNITS) - full measurement data
                for unit_id in range(1, self.max_dut_units + 1):
                    if unit_id in dut_measurements:
                        data = dut_measurements[unit_id]
                        # Add conductivity data
                        row.extend([
                            data['conductivity']['frequency'],
                            data['conductivity']['rzmag'],
                            data['conductivity']['rzphase'],
                            data['conductivity'].get('conductivity_s_cm', '')
                        ])
                        # Add temperature data (or empty if None)
                        if data['temperature'] is not None:
                            row.extend([
                                data['temperature']['frequency'],
                                data['temperature']['rzmag'],
                                data['temperature']['rzphase']
                            ])
                        else:
                            # Empty cells if no valid temperature data
                            row.extend(['', '', ''])
                    else:
                        # Empty cells if no data for this unit
                        row.extend(['', '', '', '', '', '', ''])
                
                # Add Reference devices (1-2) - simplified: just conductivity and temperature
                for ref_id in range(1, 3):
                    if ref_id in ref_measurements:
                        data = ref_measurements[ref_id]
                        row.extend([
                            data['conductivity_value'],  # mS/cm
                            data['temperature_value']     # °C
                        ])
                    else:
                        # Empty cells if no data for this reference
                        row.extend(['', ''])
                
                self.csv_writer.writerow(row)
                self.csv_file.flush()
                self.rows_written += 1
            except Exception as e:
                print(f"Error writing to CSV file: {e}")
    
    def add_dut_data(self, unit_id, timestamp, conductivity_data, temperature_data):
        """
        Add data point for a DUT unit
        
        Args:
            unit_id: Unit ID (1..MAX_DUT_UNITS)
            timestamp: Unix timestamp (seconds)
            conductivity_data: dict with 'frequency', 'rzmag', 'rzphase'
            temperature_data: dict with 'frequency', 'rzmag', 'rzphase' or None if no valid temp data
        """
        if 1 <= unit_id <= self.max_dut_units:
            self.unit_data[unit_id]['timestamps'].append(timestamp)
            self.unit_data[unit_id]['conductivity_freq'].append(conductivity_data['frequency'])
            self.unit_data[unit_id]['conductivity_rzmag'].append(conductivity_data['rzmag'])
            self.unit_data[unit_id]['conductivity_rzphase'].append(conductivity_data['rzphase'])
            self.unit_data[unit_id]['conductivity_s_cm'].append(
                conductivity_data.get('conductivity_s_cm', float('nan'))
            )
            
            # Handle None temperature data (when measurement is invalid/missing)
            if temperature_data is not None:
                self.unit_data[unit_id]['temperature_freq'].append(temperature_data['frequency'])
                self.unit_data[unit_id]['temperature_rzmag'].append(temperature_data['rzmag'])
                self.unit_data[unit_id]['temperature_rzphase'].append(temperature_data['rzphase'])
            else:
                # Use NaN or 0 for missing temperature data
                self.unit_data[unit_id]['temperature_freq'].append(0.0)
                self.unit_data[unit_id]['temperature_rzmag'].append(float('nan'))
                self.unit_data[unit_id]['temperature_rzphase'].append(float('nan'))
            
            # Keep only last MAX_GRAPH_POINTS
            if len(self.unit_data[unit_id]['timestamps']) > MAX_GRAPH_POINTS:
                for key in self.unit_data[unit_id]:
                    self.unit_data[unit_id][key] = self.unit_data[unit_id][key][-MAX_GRAPH_POINTS:]
    
    def add_reference_data(self, ref_id, timestamp, conductivity_data, temperature_data):
        """
        Add data point for a reference device
        
        Args:
            ref_id: Reference ID (1-2)
            timestamp: Unix timestamp (seconds)
            conductivity_data: dict with 'frequency', 'rzmag', 'rzphase'
            temperature_data: dict with 'frequency', 'rzmag', 'rzphase' or None if no valid temp data
        """
        if 1 <= ref_id <= 2:
            self.reference_data[ref_id]['timestamps'].append(timestamp)
            self.reference_data[ref_id]['conductivity_freq'].append(conductivity_data['frequency'])
            self.reference_data[ref_id]['conductivity_rzmag'].append(conductivity_data['rzmag'])
            self.reference_data[ref_id]['conductivity_rzphase'].append(conductivity_data['rzphase'])
            
            # Handle None temperature data (when measurement is invalid/missing)
            if temperature_data is not None:
                self.reference_data[ref_id]['temperature_freq'].append(temperature_data['frequency'])
                self.reference_data[ref_id]['temperature_rzmag'].append(temperature_data['rzmag'])
                self.reference_data[ref_id]['temperature_rzphase'].append(temperature_data['rzphase'])
            else:
                # Use NaN or 0 for missing temperature data
                self.reference_data[ref_id]['temperature_freq'].append(0.0)
                self.reference_data[ref_id]['temperature_rzmag'].append(float('nan'))
                self.reference_data[ref_id]['temperature_rzphase'].append(float('nan'))
            
            # Keep only last MAX_GRAPH_POINTS
            if len(self.reference_data[ref_id]['timestamps']) > MAX_GRAPH_POINTS:
                for key in self.reference_data[ref_id]:
                    self.reference_data[ref_id][key] = self.reference_data[ref_id][key][-MAX_GRAPH_POINTS:]
    
    def get_dut_data(self, unit_id):
        """Get all data for a specific DUT unit"""
        if 1 <= unit_id <= self.max_dut_units:
            return self.unit_data[unit_id]
        return None
    
    def get_reference_data(self, ref_id):
        """Get all data for a specific reference device"""
        if 1 <= ref_id <= 2:
            return self.reference_data[ref_id]
        return None
    
    def clear_all_data(self):
        """Clear all stored data"""
        for unit_id in range(1, self.max_dut_units + 1):
            for key in self.unit_data[unit_id]:
                self.unit_data[unit_id][key].clear()
        
        for ref_id in range(1, 3):
            for key in self.reference_data[ref_id]:
                self.reference_data[ref_id][key].clear()
    
    def get_measurement_timestamp(self):
        """
        Extract timestamp from current measurement file path
        
        Returns:
            str: Timestamp in format YYYYMMDD_HHMMSS, or None if not available
        """
        if self.csv_file_path:
            # Extract timestamp from filename like "measurements_20260128_203052.csv"
            import re
            match = re.search(r'measurements_(\d{8}_\d{6})\.csv', self.csv_file_path)
            if match:
                return match.group(1)
        return None
    
    def create_new_files(self):
        """Create new timestamped data files"""
        # Close current files
        if self.csv_file:
            try:
                self.csv_file.close()
                print(f"Closed previous CSV file: {self.csv_file_path}")
            except Exception as e:
                print(f"Error closing previous CSV file: {e}")
        
        if self.log_file:
            try:
                self.log_file.write(f"\n--- File closed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
                self.log_file.close()
                print(f"Closed previous log file: {self.log_file_path}")
            except Exception as e:
                print(f"Error closing previous log file: {e}")
        
        # Create new timestamped filenames
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.csv_file_path = os.path.join(self.save_directory, f"measurements_{timestamp}.csv")
        self.log_file_path = os.path.join(self.save_directory, f"serial_log_{timestamp}.txt")
        
        # Initialize new CSV/log files with deterministic schema and encoding.
        try:
            self._open_output_files()
            
            print(f"New CSV file: {self.csv_file_path}")
            print(f"New log file: {self.log_file_path}")
            
            return True
        except Exception as e:
            print(f"Error creating new files: {e}")
            return False

    def _build_csv_header(self):
        """Build a stable consolidated CSV header."""
        header = ['Timestamp']

        for unit_id in range(1, self.max_dut_units + 1):
            header.extend([
                f'DUT{unit_id}_Cond_Freq_Hz',
                f'DUT{unit_id}_Cond_RzMag_Ohm',
                f'DUT{unit_id}_Cond_RzPhase_Deg',
                f'DUT{unit_id}_Cond_Value_S_cm',
                f'DUT{unit_id}_Temp_Freq_Hz',
                f'DUT{unit_id}_Temp_RzMag_Ohm',
                f'DUT{unit_id}_Temp_RzPhase_Deg'
            ])

        for ref_id in range(1, 3):
            header.extend([
                f'Ref{ref_id}_Conductivity_mS_cm',
                f'Ref{ref_id}_Temperature_degC'
            ])
        return header

    def _open_output_files(self):
        """Open CSV/log files and write standardized headers."""
        self.rows_written = 0
        self.csv_file = open(self.csv_file_path, 'w', newline='', encoding='utf-8')
        self.csv_writer = csv.writer(self.csv_file)
        self.csv_writer.writerow(self._build_csv_header())
        self.csv_file.flush()

        self.log_file = open(self.log_file_path, 'w', encoding='utf-8')
        self.log_file.write(f"Serial Data Log - Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        self.log_file.write("=" * 80 + "\n\n")
        self.log_file.flush()
    
    def close_files(self):
        """Close all open file handles"""
        # region optional cloudHook
        # potential spot to add cloud hook, once upload file once it's complete. 
        # end region

        if self.csv_file:
            try:
                self.csv_file.close()
                print(f"CSV file saved: {self.csv_file_path}")
            except Exception as e:
                print(f"Error closing CSV file: {e}")
        
        if self.log_file:
            try:
                self.log_file.write(f"\n\nLog ended at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                self.log_file.close()
                print(f"Log file saved: {self.log_file_path}")
            except Exception as e:
                print(f"Error closing log file: {e}")

    def get_rows_written(self):
        """Return number of measurement rows written (excluding header)."""
        return int(self.rows_written)
