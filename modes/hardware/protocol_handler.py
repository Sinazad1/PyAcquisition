"""
Protocol Handler Module
Manages loading and executing multi-step protocols for automated testing
Controls syringe pump, Tic stepper, and chiller with timed steps

Doc status: done, MK, 01/30/2026
"""
from PySide6.QtCore import QObject, Signal, QTimer
from datetime import datetime, timedelta
import json
import os
try:
    from ionin.runtime import TimedProtocolRuntime, TimedProtocolStep
except Exception:
    TimedProtocolRuntime = None
    TimedProtocolStep = None
try:
    from ionin.protocols import normalize_and_validate_timed_protocol, protocol_checksum
except Exception:
    normalize_and_validate_timed_protocol = None
    protocol_checksum = None


class ProtocolStep:
    """Represents a single protocol step"""
    
    def __init__(self, step_number, duration_minutes, pump_settings=None, 
                 tic_a_settings=None, tic_b_settings=None, chiller_settings=None, description=""):
        """
        Initialize a protocol step.
        
        Creates a single step in a calibration protocol sequence with device settings
        and duration.
        
        Args:
            step_number (int): Step number in the protocol sequence.
            duration_minutes (float): Duration of this step in minutes.
            pump_settings (dict, optional): Syringe pump configuration. Defaults to None.
            tic_a_settings (dict, optional): TIC A stepper controller configuration. Defaults to None.
            tic_b_settings (dict, optional): TIC B stepper controller configuration. Defaults to None.
            chiller_settings (dict, optional): Chiller configuration. Defaults to None.
            description (str, optional): Human-readable step description. Defaults to "".
        """
        self.step_number = step_number
        self.duration_minutes = duration_minutes
        self.pump_settings = pump_settings or {}
        self.tic_a_settings = tic_a_settings or {}
        self.tic_b_settings = tic_b_settings or {}
        self.chiller_settings = chiller_settings or {}
        self.description = description
        
    def to_dict(self):
        """Convert to dictionary for saving"""
        return {
            'step': self.step_number,
            'duration_minutes': self.duration_minutes,
            'pump': self.pump_settings,
            'tic_a': self.tic_a_settings,
            'tic_b': self.tic_b_settings,
            'chiller': self.chiller_settings,
            'description': self.description
        }
    
    @classmethod
    def from_dict(cls, data):
        """Create from dictionary"""
        return cls(
            step_number=data.get('step', 0),
            duration_minutes=data.get('duration_minutes', 0),
            pump_settings=data.get('pump', {}),
            tic_a_settings=data.get('tic_a', data.get('tic', {})),  # Fallback to 'tic' for backward compatibility
            tic_b_settings=data.get('tic_b', {}),
            chiller_settings=data.get('chiller', {}),
            description=data.get('description', "")
        )
    
    def __str__(self):
        """String representation"""
        parts = [f"Step {self.step_number}: {self.duration_minutes} min"]
        if self.description:
            parts.append(f"- {self.description}")
        return " ".join(parts)

class ProtocolHandler(QObject):
    """Handles protocol execution"""
    
    # Signals
    protocol_starting = Signal()  # Emitted when protocol begins
    step_started = Signal(int, object)  # step_number, ProtocolStep
    step_completed = Signal(int)  # step_number
    protocol_completed = Signal()
    protocol_aborted = Signal()
    devices_stopped = Signal()  # Emitted after devices are stopped on abort
    time_remaining = Signal(int)  # seconds remaining in current step
    error_occurred = Signal(str)
    
    def __init__(self):
        """
        Initialize the protocol handler.
        
        Sets up protocol execution management, signal connections, and device
        coordination for running calibration protocol sequences.
        """
        super().__init__()
        
        self.protocol_steps = []
        self.current_step_index = -1
        self.is_running = False
        self.is_paused = False
        
        # Protocol events log file
        self.protocol_events_file = None
        self.protocol_events_path = None
        self.protocol_metadata_path = None
        self.protocol_metadata = None
        
        # CSV events tracking
        self.csv_events_path = None
        self.step_timestamps = []
        self.step_labels = []
        
        # Timer for countdown
        self.step_timer = QTimer()
        self.step_timer.timeout.connect(self._on_timer_tick)
        
        # Step timing
        self.step_start_time = None
        self.step_duration_seconds = 0
        self.time_elapsed_seconds = 0
        self.ionin_timed_runtime = None
        
    def load_protocol(self, filepath):
        """
        Load protocol from JSON file
        
        Args:
            filepath: Path to protocol JSON file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)

            if normalize_and_validate_timed_protocol is not None:
                data = normalize_and_validate_timed_protocol(raw_data)
            else:
                data = raw_data

            checksum_value = (
                protocol_checksum(data)
                if protocol_checksum is not None
                else None
            )
            self.protocol_metadata = {
                "protocol_name": str(data.get("protocol_name", os.path.basename(filepath).replace(".json", ""))),
                "protocol_version": str(data.get("protocol_version", "0.0.0")),
                "protocol_checksum": checksum_value,
                "source_file": os.path.abspath(filepath),
            }
            
            # Clear existing protocol
            self.protocol_steps = []
            
            # Load steps
            steps_data = data.get('steps', [])
            for step_data in steps_data:
                step = ProtocolStep.from_dict(step_data)
                self.protocol_steps.append(step)
            
            # Sort by step number
            self.protocol_steps.sort(key=lambda s: s.step_number)
            
            return True
            
        except FileNotFoundError:
            self.error_occurred.emit(f"Protocol file not found: {filepath}")
            return False
        except json.JSONDecodeError as e:
            self.error_occurred.emit(f"Invalid JSON in protocol file: {str(e)}")
            return False
        except Exception as e:
            self.error_occurred.emit(f"Error loading protocol: {str(e)}")
            return False
    
    def save_protocol(self, filepath):
        """
        Save protocol to JSON file
        
        Args:
            filepath: Path to save protocol JSON file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            data = {
                'protocol_name': os.path.basename(filepath).replace('.json', ''),
                'created': datetime.now().isoformat(),
                'steps': [step.to_dict() for step in self.protocol_steps]
            }
            
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
            
            return True
            
        except Exception as e:
            self.error_occurred.emit(f"Error saving protocol: {str(e)}")
            return False
    
    def add_step(self, step):
        """Add a step to the protocol"""
        self.protocol_steps.append(step)
        self.protocol_steps.sort(key=lambda s: s.step_number)
    
    def clear_protocol(self):
        """Clear all protocol steps"""
        self.protocol_steps = []
        self.current_step_index = -1
    
    def get_step_count(self):
        """Get total number of steps"""
        return len(self.protocol_steps)
    
    def _init_protocol_events_log(self, save_directory=None, measurement_timestamp=None):
        """
        Initialize protocol events log file
        
        Args:
            save_directory: Directory to save the log file (defaults to current directory)
            measurement_timestamp: Timestamp from measurement file to use (YYYYMMDD_HHMMSS format)
                                  If None, generates new timestamp
        """
        try:
            # Close existing log file if open
            if self.protocol_events_file and not self.protocol_events_file.closed:
                self.protocol_events_file.close()
            
            # Determine save directory
            if save_directory is None:
                save_directory = "."
            
            # Expand special paths and convert to absolute
            save_directory = os.path.expanduser(save_directory)
            save_directory = os.path.abspath(save_directory)
            
            # Create directory if it doesn't exist
            os.makedirs(save_directory, exist_ok=True)
            
            # Use provided measurement timestamp or generate new one
            if measurement_timestamp:
                timestamp = measurement_timestamp
            else:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Check if event file already exists with this timestamp
            potential_events_path = os.path.join(save_directory, f"events_{timestamp}.txt")
            if os.path.exists(potential_events_path):
                # Event file exists, need to signal for new measurement file creation
                return False, timestamp  # Return False to indicate files need recreation
            
            self.protocol_events_path = potential_events_path
            self.csv_events_path = os.path.join(save_directory, f"events_{timestamp}.csv")
            self.protocol_metadata_path = os.path.join(save_directory, f"protocol_metadata_{timestamp}.json")
            
            # Reset CSV tracking
            self.step_timestamps = []
            self.step_labels = []
            
            # Open file and write header
            self.protocol_events_file = open(self.protocol_events_path, 'w', encoding='utf-8')
            self.protocol_events_file.write(f"Protocol Events Log - Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            if self.protocol_metadata:
                self.protocol_events_file.write(
                    f"Protocol: {self.protocol_metadata.get('protocol_name')} "
                    f"v{self.protocol_metadata.get('protocol_version')} "
                    f"(checksum={self.protocol_metadata.get('protocol_checksum') or 'n/a'})\n"
                )
            self.protocol_events_file.write("=" * 80 + "\n\n")
            self.protocol_events_file.flush()
            
            return True, timestamp
        except Exception as e:
            self.error_occurred.emit(f"Failed to create protocol events log: {str(e)}")
            return False, None

    def _write_protocol_metadata_artifact(self):
        """Persist protocol metadata for run traceability."""
        if not self.protocol_metadata_path:
            return
        payload = dict(self.protocol_metadata or {})
        payload["generated_at"] = datetime.now().isoformat()
        payload["events_file"] = self.protocol_events_path
        payload["events_csv"] = self.csv_events_path
        try:
            with open(self.protocol_metadata_path, 'w', encoding='utf-8') as fh:
                json.dump(payload, fh, indent=2)
        except Exception as e:
            self.error_occurred.emit(f"Failed to save protocol metadata: {str(e)}")
    
    def _log_protocol_event(self, event_message):
        """
        Log an event to the protocol events file
        
        Args:
            event_message: Message to log
        """
        if self.protocol_events_file and not self.protocol_events_file.closed:
            try:
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                self.protocol_events_file.write(f"[{timestamp}] {event_message}\n")
                self.protocol_events_file.flush()
            except Exception as e:
                print(f"Error writing to protocol events log: {e}")
    
    def _save_csv_events(self):
        """
        Save protocol events to CSV file in the format:
        Row 1: Timestamps (YYYY-MM-DD HH:MM:SS..mmm)
        Row 2: Step labels (step 1, step 2, etc.)
        """
        if not self.csv_events_path or not self.step_timestamps:
            return
        
        try:
            with open(self.csv_events_path, 'w', encoding='utf-8') as f:
                # Write timestamps row
                f.write(','.join(self.step_timestamps) + '\n')
                # Write step labels row
                f.write(','.join(self.step_labels) + '\n')
        except Exception as e:
            print(f"Error writing CSV events file: {e}")
            self.error_occurred.emit(f"Failed to save CSV events: {str(e)}")
    
    def get_current_step(self):
        """Get current protocol step"""
        if 0 <= self.current_step_index < len(self.protocol_steps):
            return self.protocol_steps[self.current_step_index]
        return None
    
    def start_protocol(self, save_directory=None, measurement_timestamp=None):
        """
        Start protocol execution from beginning
        
        Args:
            save_directory: Directory to save protocol events log (optional)
            measurement_timestamp: Timestamp from measurement file (YYYYMMDD_HHMMSS format)
                                  If None, generates new timestamp
                                  
        Returns:
            tuple: (success: bool, needs_new_files: bool, timestamp: str or None)
                  success: True if protocol started successfully
                  needs_new_files: True if new measurement files should be created
                  timestamp: The timestamp that was attempted (for new file creation)
        """
        if not self.protocol_steps:
            self.error_occurred.emit("No protocol loaded")
            return False, False, None
        
        # Initialize protocol events log with measurement timestamp
        success, timestamp = self._init_protocol_events_log(save_directory, measurement_timestamp)
        
        # If event file already exists, signal that new measurement files are needed
        if not success and timestamp:
            return False, True, timestamp  # Signal to create new files with new timestamp
        elif not success:
            return False, False, None  # Error occurred
        
        self.current_step_index = 0
        self.is_running = True
        self.is_paused = False

        if TimedProtocolRuntime is not None and TimedProtocolStep is not None:
            timed_steps = []
            for step in self.protocol_steps:
                timed_steps.append(
                    TimedProtocolStep(
                        step_number=int(step.step_number),
                        duration_seconds=int(round(step.duration_minutes * 60)),
                        description=step.description or "",
                        actions={
                            "pump": dict(step.pump_settings or {}),
                            "tic_a": dict(step.tic_a_settings or {}),
                            "tic_b": dict(step.tic_b_settings or {}),
                            "chiller": dict(step.chiller_settings or {}),
                        },
                    )
                )
            self.ionin_timed_runtime = TimedProtocolRuntime(timed_steps)
            self.ionin_timed_runtime.start()
        
        # Emit protocol starting signal
        self.protocol_starting.emit()
        
        # Log protocol start
        self._log_protocol_event(f"Protocol starting - {len(self.protocol_steps)} steps")
        if self.protocol_metadata:
            self._log_protocol_event(
                f"Protocol metadata: name={self.protocol_metadata.get('protocol_name')} "
                f"version={self.protocol_metadata.get('protocol_version')} "
                f"checksum={self.protocol_metadata.get('protocol_checksum') or 'n/a'}"
            )
        self._write_protocol_metadata_artifact()
        
        # Start first step
        self._start_current_step()
        return True, False, timestamp
    
    def pause_protocol(self): # REMOVED functionality -MK
        """Pause protocol execution"""
        if self.is_running and not self.is_paused:
            self.is_paused = True
            self.step_timer.stop()
            if self.ionin_timed_runtime is not None:
                self.ionin_timed_runtime.pause()
            self._log_protocol_event("Protocol paused")
    
    def resume_protocol(self): # REMOVED functionality -MK
        """Resume protocol execution"""
        if self.is_running and self.is_paused:
            self.is_paused = False
            self.step_timer.start(1000)  # 1 second updates
            if self.ionin_timed_runtime is not None:
                self.ionin_timed_runtime.resume()
            self._log_protocol_event("Protocol resumed")
    
    def abort_protocol(self):
        """Abort protocol execution"""
        # Get current step info before resetting
        current_step = self.get_current_step()
        step_info = f" (was on step {current_step.step_number}/{len(self.protocol_steps)})" if current_step else ""
        
        self.is_running = False
        self.is_paused = False
        self.step_timer.stop()
        self.current_step_index = -1
        if self.ionin_timed_runtime is not None:
            self.ionin_timed_runtime.abort()
            self.ionin_timed_runtime = None
        
        # Log abort with step information
        self._log_protocol_event(f"Protocol aborted{step_info}")
        
        # Save CSV events file
        self._save_csv_events()
        
        # Close protocol events log file
        if self.protocol_events_file and not self.protocol_events_file.closed:
            self.protocol_events_file.close()
        
        self.protocol_aborted.emit()
    
    def _start_current_step(self):
        """Start the current step"""
        step = self.get_current_step()
        if not step:
            return
        
        # Record step start time for CSV with format: YYYY-MM-DD HH:MM:SS..mmm
        step_start = datetime.now()
        timestamp_str = step_start.strftime("%Y-%m-%d %H:%M:%S") + f"..{step_start.microsecond // 1000:03d}"
        self.step_timestamps.append(timestamp_str)
        self.step_labels.append(f"step {step.step_number}")
        
        # Reset step timing
        self.step_start_time = step_start
        if self.ionin_timed_runtime is not None:
            self.step_duration_seconds = self.ionin_timed_runtime.step_duration_seconds
            self.time_elapsed_seconds = self.ionin_timed_runtime.time_elapsed_seconds
        else:
            self.step_duration_seconds = step.duration_minutes * 60
            self.time_elapsed_seconds = 0
        
        # Build settings string for logging
        settings_parts = []
        
        # Pump settings
        if step.pump_settings:
            pump_str_parts = []
            if 'direction' in step.pump_settings:
                pump_str_parts.append(f"Dir={step.pump_settings['direction']}")
            if 'rate' in step.pump_settings:
                pump_str_parts.append(f"Rate={step.pump_settings['rate']}")
            if 'volume' in step.pump_settings:
                pump_str_parts.append(f"Vol={step.pump_settings['volume']}")
            if 'run' in step.pump_settings:
                pump_str_parts.append(f"Run={step.pump_settings['run']}")
            if pump_str_parts:
                settings_parts.append(f"Pump[{', '.join(pump_str_parts)}]")
        
        # TIC A settings
        if step.tic_a_settings:
            tic_a_str_parts = []
            if 'velocity' in step.tic_a_settings:
                tic_a_str_parts.append(f"Vel={step.tic_a_settings['velocity']}")
            if 'position' in step.tic_a_settings:
                tic_a_str_parts.append(f"Pos={step.tic_a_settings['position']}")
            if 'acceleration' in step.tic_a_settings:
                tic_a_str_parts.append(f"Accel={step.tic_a_settings['acceleration']}")
            if tic_a_str_parts:
                settings_parts.append(f"TIC_A[{', '.join(tic_a_str_parts)}]")
        
        # TIC B settings
        if step.tic_b_settings:
            tic_b_str_parts = []
            if 'velocity' in step.tic_b_settings:
                tic_b_str_parts.append(f"Vel={step.tic_b_settings['velocity']}")
            if 'position' in step.tic_b_settings:
                tic_b_str_parts.append(f"Pos={step.tic_b_settings['position']}")
            if 'acceleration' in step.tic_b_settings:
                tic_b_str_parts.append(f"Accel={step.tic_b_settings['acceleration']}")
            if tic_b_str_parts:
                settings_parts.append(f"TIC_B[{', '.join(tic_b_str_parts)}]")
        
        # Chiller settings
        if step.chiller_settings:
            chiller_str_parts = []
            if 'temperature' in step.chiller_settings:
                chiller_str_parts.append(f"Temp={step.chiller_settings['temperature']}°C")
            if 'pump_speed' in step.chiller_settings:
                chiller_str_parts.append(f"PumpSpeed={step.chiller_settings['pump_speed']}%")
            if 'start' in step.chiller_settings:
                chiller_str_parts.append(f"Start={step.chiller_settings['start']}")
            if chiller_str_parts:
                settings_parts.append(f"Chiller[{', '.join(chiller_str_parts)}]")
        
        # Build final log message
        settings_str = " | ".join(settings_parts) if settings_parts else "No settings"
        description_str = f" - {step.description}" if step.description else ""
        log_message = f"Step {step.step_number} started - Duration: {step.duration_minutes} min{description_str} - Settings: {settings_str}"
        
        # Log step start
        self._log_protocol_event(log_message)
        
        # Emit step started signal
        self.step_started.emit(step.step_number, step)
        
        # Start timer (1 second intervals)
        self.step_timer.start(1000)
    
    def _on_timer_tick(self):
        """Handle timer tick (every second)"""
        if not self.is_running or self.is_paused:
            return

        if self.ionin_timed_runtime is not None:
            transition = self.ionin_timed_runtime.tick(1)
            self.current_step_index = self.ionin_timed_runtime.current_step_index
            self.step_duration_seconds = self.ionin_timed_runtime.step_duration_seconds
            self.time_elapsed_seconds = self.ionin_timed_runtime.time_elapsed_seconds

            remaining = transition["time_remaining"]
            self.time_remaining.emit(remaining)

            completed_idx = transition.get("step_completed_index")
            if completed_idx is not None and 0 <= completed_idx < len(self.protocol_steps):
                completed_step = self.protocol_steps[completed_idx]
                self._log_protocol_event(f"Step {completed_step.step_number} completed")
                self.step_completed.emit(completed_step.step_number)

            if transition.get("protocol_completed"):
                self.is_running = False
                self.step_timer.stop()
                self._log_protocol_event("Protocol completed successfully")
                self._save_csv_events()
                if self.protocol_events_file and not self.protocol_events_file.closed:
                    self.protocol_events_file.close()
                self.protocol_completed.emit()
                self.ionin_timed_runtime = None
                return

            if transition.get("next_step_index") is not None:
                self._start_current_step()
            return

        self.time_elapsed_seconds += 1

        # Calculate remaining time
        remaining = self.step_duration_seconds - self.time_elapsed_seconds

        # Emit time remaining
        self.time_remaining.emit(remaining)

        # Check if step is complete
        if remaining <= 0:
            self._complete_current_step()
    
    def _complete_current_step(self):
        """Complete the current step and move to next"""
        step = self.get_current_step()
        if step:
            # Log step completion
            self._log_protocol_event(f"Step {step.step_number} completed")
            self.step_completed.emit(step.step_number)
        
        # Move to next step
        self.current_step_index += 1
        
        if self.current_step_index < len(self.protocol_steps):
            # Start next step
            self._start_current_step()
        else:
            # Protocol complete
            self.is_running = False
            self.step_timer.stop()
            
            # Log protocol completion
            self._log_protocol_event("Protocol completed successfully")
            
            # Save CSV events file
            self._save_csv_events()
            
            # Close protocol events log file
            if self.protocol_events_file and not self.protocol_events_file.closed:
                self.protocol_events_file.close()
            
            self.protocol_completed.emit()
    
    def get_protocol_summary(self):
        """Get summary of loaded protocol"""
        if not self.protocol_steps:
            return "No protocol loaded"
        
        total_minutes = sum(step.duration_minutes for step in self.protocol_steps)
        hours = total_minutes // 60
        minutes = total_minutes % 60
        
        summary = f"Protocol: {len(self.protocol_steps)} steps, "
        summary += f"Total duration: {hours}h {minutes}m\n\n"
        
        for step in self.protocol_steps:
            summary += f"{step}\n"
        
        return summary