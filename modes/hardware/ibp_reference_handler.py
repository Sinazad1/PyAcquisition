"""
IBP Reference Sensor Handler
Handles communication with IBP HDU-CDTP reference sensors
Implements IBP conductivity and temperature reading

Doc status: done, MK, 01/30/2026
"""
from PySide6.QtCore import QThread, Signal
import serial
import time


class IBPReferenceHandler(QThread):
    """Thread-based handler for IBP reference sensor"""
    data_received = Signal(int, float, float)  # ref_id, conductivity, temperature
    error_occurred = Signal(int, str)  # ref_id, error_message
    disconnected = Signal(int)  # ref_id
    serial_number_received = Signal(int, str)  # ref_id, serial_number
    command_sent = Signal(int, str)  # ref_id, command - NEW for logging
    response_received = Signal(int, str, str)  # ref_id, command, response - NEW for detailed logging
    
    def __init__(self, ref_id, port, baudrate=115200, timeout=2.0):
        """
        Initialize the IBP reference sensor handler thread.
        
        Sets up serial communication for IBP reference sensor data acquisition.
        
        Args:
            ref_id (int): Reference sensor identifier (1 or 2).
            port (str): COM port for IBP reference communication.
            baudrate (int, optional): Baud rate for serial communication. Defaults to 115200.
            timeout (float, optional): Timeout for serial operations in seconds. Defaults to 2.0.
        """
        super().__init__()
        self.ref_id = ref_id
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_connection = None
        self.running = False
        self.paused = False
        self.serial_number = None
        
    def run(self):
        """Main thread execution"""
        try:
            self.serial_connection = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE
            )
            self.running = True
            
            # Small delay for device to be ready
            time.sleep(0.1)
            
            # Read serial number on startup
            sn = self.send_command("SYSSNR")
            if sn and sn != "99":
                self.serial_number = sn
                self.serial_number_received.emit(self.ref_id, sn)
            else:
                self.error_occurred.emit(self.ref_id, "Failed to read serial number")
            
            # Main loop - just keep thread alive
            # Reading will be triggered externally via read_data()
            while self.running:
                time.sleep(0.1)
                    
        except serial.SerialException as e:
            self.error_occurred.emit(self.ref_id, f"Failed to open port {self.port}: {str(e)}")
        except Exception as e:
            self.error_occurred.emit(self.ref_id, f"Unexpected initialization error: {str(e)}")
        finally:
            self.close_connection()
    
    def read_data(self):
        """
        Read one set of data from the sensor
        Called externally when synchronized reading is needed
        """
        if not self.running:
            return
        
        try:
            # Emit signal that we're sending VALAR command
            self.command_sent.emit(self.ref_id, "VALAR")
            
            # Read conductivity and temperature
            response = self.send_command("VALAR")
            
            if response and response != "99":
                # Parse response: "conductivityHere/IGNORE/123.123" (3 values)
                try:
                    parts = response.split('/')
                    if len(parts) == 3:
                        conductivity = float(parts[0].strip())  # mS/cm
                        # parts[1] is ignored (intermediate value not used)
                        temperature = float(parts[2].strip())   # °C
                        
                        self.data_received.emit(
                            self.ref_id,
                            conductivity,
                            temperature
                        )
                    else:
                        self.error_occurred.emit(
                            self.ref_id,
                            f"Invalid response format: {response}"
                        )
                except ValueError as e:
                    self.error_occurred.emit(
                        self.ref_id,
                        f"Failed to parse values: {str(e)}"
                    )
        
        except serial.SerialException as e:
            self.error_occurred.emit(self.ref_id, f"Serial error: {str(e)}")
            self.disconnected.emit(self.ref_id)
            self.running = False
        except Exception as e:
            self.error_occurred.emit(self.ref_id, f"Unexpected error: {str(e)}")
    
    def send_command(self, command):
        """
        Send ASCII command to IBP sensor
        
        Args:
            command: Command string (e.g., "SYSSNR", "VALAR")
            
        Returns:
            Response string or None if error
        """
        if not self.serial_connection or not self.serial_connection.is_open:
            return None
        
        try:
            # Clear input buffer
            self.serial_connection.reset_input_buffer()
            
            # Send command with CR termination
            full_command = (command + '\r').encode('ascii')
            self.serial_connection.write(full_command)
            self.serial_connection.flush()
            
            # Read response until CR
            response = b''
            start_time = time.time()
            timeout = 2.0
            
            while time.time() - start_time < timeout:
                if self.serial_connection.in_waiting > 0:
                    byte = self.serial_connection.read(1)
                    
                    # Check for CR termination
                    if byte == b'\r':
                        break
                    
                    response += byte
                
                time.sleep(0.01)
            
            if response:
                decoded_response = response.decode('ascii').strip()
                # Emit detailed log: command sent and exact response received
                self.response_received.emit(self.ref_id, command, decoded_response)
                return decoded_response
            else:
                # Log when no response is received
                self.response_received.emit(self.ref_id, command, "<No Response>")
                return None
                
        except Exception as e:
            self.error_occurred.emit(self.ref_id, f"Command error: {str(e)}")
            self.response_received.emit(self.ref_id, command, f"<Error: {str(e)}>")
            return None
    
    def stop(self):
        """Stop the thread"""
        self.running = False
        self.wait()
    
    def pause(self):
        """Pause reading"""
        self.paused = True
    
    def resume(self):
        """Resume reading"""
        self.paused = False
    
    def close_connection(self):
        """Close serial connection"""
        if self.serial_connection and self.serial_connection.is_open:
            try:
                self.serial_connection.close()
            except Exception as e:
                print(f"Error closing IBP sensor port: {e}")
    
    def get_serial_number(self):
        """Get the serial number of this sensor"""
        return self.serial_number