"""
Tic Controller Handler Module
Handles communication with Pololu Tic 36v4 stepper motor controller
Uses subprocess calls to ticcmd utility

Doc status: done, MK, 01/30/2026
"""
from PySide6.QtCore import QThread, Signal, QTimer
import subprocess
import json

class TicThread(QThread):
    """Thread for Tic controller communication via ticcmd"""
    status_received = Signal(dict)  # Status data as dict
    velocity_confirmed = Signal(int)  # Velocity confirmation
    position_received = Signal(int)  # Current position
    error_occurred = Signal(str)
    connection_status = Signal(bool, str)  # status, message
    command_log = Signal(str, str)  # command, response (for logging all communications)
    
    def __init__(self, serial_number):
        """
        Initialize the TIC stepper controller handler thread.
        
        Sets up USB communication and control for TIC stepper motor controller.
        
        Args:
            serial_number (str): Serial number of the TIC device.
        """
        super().__init__()
        self.serial_number = serial_number
        self.running = False
        self._stop_requested = False
        self.current_velocity = 0
        
    def run(self):
        """Initialize connection and verify device"""
        try:
            # Verify Tic is accessible
            result = self.get_status()
            
            if result:
                self.running = True
                self.connection_status.emit(True, f"Connected to Tic {self.serial_number}")
                
                # Stop all motion at start 
                #self.set_velocity(0) - should be unneeded, MK
                
                # Emit initial status
                self.status_received.emit(result)
            else:
                self.error_occurred.emit(f"Tic {self.serial_number} not found or not responding")
                self.connection_status.emit(False, "Tic not accessible")
                self.running = False
                
        except Exception as e:
            self.error_occurred.emit(f"Initialization error: {str(e)}")
            self.connection_status.emit(False, str(e))
    
    def get_status(self):
        """
        Get status from Tic using ticcmd
        Command: ticcmd -d <serial> --status
        
        Returns:
            Dictionary with status information or None if error
        """
        try:
            result = subprocess.run(
                ['ticcmd', '-d', self.serial_number, '--status'],
                capture_output=True,
                text=True,
                check=True,
                timeout=5
            )
            
            # Log the command and a summary of the response
            self.command_log.emit(
                f"TX: ticcmd --status", 
                f"RX: Status OK ({len(result.stdout)} chars)"
            )
            
            # Parse the output - ticcmd returns key-value pairs
            status_dict = self._parse_status_output(result.stdout)
            return status_dict
            
        except subprocess.TimeoutExpired:
            self.error_occurred.emit("Tic status command timeout")
            self.command_log.emit("TX: ticcmd --status", "RX: <Timeout>")
            return None
        except subprocess.CalledProcessError as e:
            self.error_occurred.emit(f"Tic command error: {e.stderr}")
            self.command_log.emit("TX: ticcmd --status", f"RX: <Error: {e.stderr}>")
            return None
        except FileNotFoundError:
            self.error_occurred.emit("ticcmd not found - install Pololu Tic software")
            self.command_log.emit("TX: ticcmd --status", "RX: <ticcmd not found>")
            return None
        except Exception as e:
            self.error_occurred.emit(f"Status error: {str(e)}")
            self.command_log.emit("TX: ticcmd --status", f"RX: <Error: {str(e)}>")
            return None
    
    def _parse_status_output(self, output):
        """Parse ticcmd status output into dictionary"""
        status = {}
        
        for line in output.split('\n'):
            line = line.strip()
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()
                
                # Store common status fields
                if key == 'Current position':
                    try:
                        status['position'] = int(value)
                    except ValueError:
                        pass
                elif key == 'Target velocity':
                    try:
                        status['target_velocity'] = int(value)
                    except ValueError:
                        pass
                elif key == 'Current velocity':
                    try:
                        status['current_velocity'] = int(value)
                    except ValueError:
                        pass
                elif key == 'Energized':
                    status['energized'] = value.lower() == 'yes'
                elif key == 'Position uncertain':
                    status['position_uncertain'] = value.lower() == 'yes'
                elif key == 'VIN voltage':
                    try:
                        # Format is typically "VIN voltage: 12.34 V"
                        status['vin_voltage'] = float(value.split()[0])
                    except (ValueError, IndexError):
                        pass
                elif key == 'Operation state':
                    status['operation_state'] = value
                
                # Store all fields for reference
                status[key] = value
        
        return status
    
    def set_velocity(self, velocity):
        """
        Set target velocity
        Command: ticcmd -d <serial> --velocity <velocity>
        
        Args:
            velocity: Target velocity in units/10000 seconds (integer)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            result = subprocess.run(
                ['ticcmd', '-d', self.serial_number, '--velocity', str(int(velocity))],
                capture_output=True,
                text=True,
                check=True,
                timeout=5
            )
            
            # Log the command with TX/RX format
            self.command_log.emit(f"TX: ticcmd --velocity {velocity}", "RX: Success")
            
            self.current_velocity = velocity
            self.velocity_confirmed.emit(velocity)
            return True
            
        except subprocess.TimeoutExpired:
            self.error_occurred.emit("Velocity command timeout")
            self.command_log.emit(f"TX: ticcmd --velocity {velocity}", "RX: <Timeout>")
            return False
        except subprocess.CalledProcessError as e:
            self.error_occurred.emit(f"Velocity command error: {e.stderr}")
            self.command_log.emit(f"TX: ticcmd --velocity {velocity}", f"RX: <Error: {e.stderr}>")
            return False
        except Exception as e:
            self.error_occurred.emit(f"Velocity error: {str(e)}")
            self.command_log.emit(f"TX: ticcmd --velocity {velocity}", f"RX: <Error: {str(e)}>")
            return False
    
    def deenergize(self):
        """
        Deenergize the motor
        Command: ticcmd -d <serial> --deenergize
        
        Returns:
            True if successful, False otherwise
        """
        try:
            result = subprocess.run(
                ['ticcmd', '-d', self.serial_number, '--deenergize'],
                capture_output=True,
                text=True,
                check=True,
                timeout=5
            )
            # Log the command with TX/RX format
            self.command_log.emit("TX: ticcmd --deenergize", "RX: Success")
            return True
            
        except subprocess.CalledProcessError as e:
            self.error_occurred.emit(f"Deenergize error: {e.stderr}")
            self.command_log.emit("TX: ticcmd --deenergize", f"RX: <Error: {e.stderr}>")
            return False
        except Exception as e:
            self.error_occurred.emit(f"Deenergize error: {str(e)}")
            self.command_log.emit("TX: ticcmd --deenergize", f"RX: <Error: {str(e)}>")
            return False
    
    def energize(self):
        """
        Energize the motor
        Command: ticcmd -d <serial> --energize
        
        Returns:
            True if successful, False otherwise
        """
        try:
            result = subprocess.run(
                ['ticcmd', '-d', self.serial_number, '--energize'],
                capture_output=True,
                text=True,
                check=True,
                timeout=5
            )
            # Log the command with TX/RX format
            self.command_log.emit("TX: ticcmd --energize", "RX: Success")
            return True
            
        except subprocess.CalledProcessError as e:
            self.error_occurred.emit(f"Energize error: {e.stderr}")
            self.command_log.emit("TX: ticcmd --energize", f"RX: <Error: {e.stderr}>")
            return False
        except Exception as e:
            self.error_occurred.emit(f"Energize error: {str(e)}")
            self.command_log.emit("TX: ticcmd --energize", f"RX: <Error: {str(e)}>")
            return False
    
    def halt(self):
        """
        Halt motor (emergency stop)
        Command: ticcmd -d <serial> --halt-and-hold
        
        Returns:
            True if successful, False otherwise
        """
        try:
            result = subprocess.run(
                ['ticcmd', '-d', self.serial_number, '--halt-and-hold'],
                capture_output=True,
                text=True,
                check=True,
                timeout=5
            )
            # Log the command with TX/RX format
            self.command_log.emit("TX: ticcmd --halt-and-hold", "RX: Success")
            self.current_velocity = 0
            return True
            
        except subprocess.CalledProcessError as e:
            self.error_occurred.emit(f"Halt error: {e.stderr}")
            self.command_log.emit("TX: ticcmd --halt-and-hold", f"RX: <Error: {e.stderr}>")
            return False
        except Exception as e:
            self.error_occurred.emit(f"Halt error: {str(e)}")
            self.command_log.emit("TX: ticcmd --halt-and-hold", f"RX: <Error: {str(e)}>")
            return False
    
    def resume(self):
        """
        Resume from halt
        Command: ticcmd -d <serial> --resume
        
        Returns:
            True if successful, False otherwise
        """
        try:
            result = subprocess.run(
                ['ticcmd', '-d', self.serial_number, '--resume'],
                capture_output=True,
                text=True,
                check=True,
                timeout=5
            )
            # Log the command
            self.command_log.emit("ticcmd --resume", "Success")
            return True
            
        except subprocess.CalledProcessError as e:
            self.error_occurred.emit(f"Resume error: {e.stderr}")
            return False
        except Exception as e:
            self.error_occurred.emit(f"Resume error: {str(e)}")
            return False
    
    def reset_command_timeout(self):
        """
        Reset command timeout
        Command: ticcmd -d <serial> --reset-command-timeout
        
        Returns:
            True if successful, False otherwise
        """
        try:
            result = subprocess.run(
                ['ticcmd', '-d', self.serial_number, '--reset-command-timeout'],
                capture_output=True,
                text=True,
                check=True,
                timeout=5
            )
            return True
            
        except subprocess.CalledProcessError as e:
            self.error_occurred.emit(f"Reset timeout error: {e.stderr}")
            return False
        except Exception as e:
            self.error_occurred.emit(f"Reset timeout error: {str(e)}")
            return False
    
    def query_status(self):
        """
        Query current status
        Called periodically to update display
        """
        if not self.running:
            return
        
        status = self.get_status()
        if status:
            self.status_received.emit(status)
            
            # Emit position if available
            if 'position' in status:
                self.position_received.emit(status['position'])
    
    def stop(self):
        """Stop the thread"""
        self._stop_requested = True
        self.running = False
        
        # Stop motor before closing
        try:
            self.set_velocity(0)
        except:
            pass
        
        self.quit()

def check_ticcmd_installed():
    """
    Check if ticcmd is installed and accessible
    Uses --full command to verify installation
    
    Returns:
        (installed: bool, version: str or None)
    """
    try:
        result = subprocess.run(
            ['ticcmd', '--full'],
            capture_output=True,
            text=True,
            timeout=5
        )
        # If command runs without error, ticcmd is installed
        # Try to get version for confirmation
        try:
            version_result = subprocess.run(
                ['ticcmd', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            version = version_result.stdout.strip()
        except:
            version = "Pololu Tic (version unknown)"
        
        return True, version
    except FileNotFoundError:
        return False, None
    except subprocess.TimeoutExpired:
        # Timeout means it's installed but taking too long
        return True, "Pololu Tic (timeout on version check)"
    except Exception:
        return False, None

def list_tic_devices():
    """
    List all connected Tic devices
    Command: ticcmd --list
    
    Returns:
        List of dictionaries with device info
    """
    try:
        result = subprocess.run(
            ['ticcmd', '--list'],
            capture_output=True,
            text=True,
            check=True,
            timeout=5
        )
        
        devices = []
        for line in result.stdout.split('\n'):
            if line.strip():
                # Format is typically: "serial_number, name"
                parts = line.split(',')
                if len(parts) >= 1:
                    serial = parts[0].strip()
                    name = parts[1].strip() if len(parts) > 1 else "Unknown"
                    devices.append({
                        'serial': serial,
                        'name': name
                    })
        
        return devices
        
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return []

