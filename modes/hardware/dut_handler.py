"""
Serial Communication Handler
Handles continuous reading from serial port in a separate thread
Updated to handle longer messages from multiple units

Doc status: done, MK, 01/30/2026
"""
from PySide6.QtCore import QThread, Signal
import serial
import time

# Import timeout settings from config
try:
    from modes.utils.config import READ_TIMEOUT_MAX, READ_TIMEOUT_IDLE
except ImportError:
    # Default values if config not available
    READ_TIMEOUT_MAX = 5.0
    READ_TIMEOUT_IDLE = 0.5

class DutHandler(QThread):
    """Thread-based serial port handler"""
    data_received = Signal(str)
    error_occurred = Signal(str)
    disconnected = Signal()  # New signal for connection loss
    command_sent = Signal(str)  # Signal for command sent (the query character)
    response_received = Signal(str, str)  # Signal for full response: (command, response)
    
    def __init__(self, port, baudrate=9600, timeout=1, query_interval=0.1):
        """
        Initialize the serial handler thread.
        
        Sets up serial communication for DUT data acquisition.
        
        Args:
            port (str): COM port for DUT communication.
            baudrate (int, optional): Baud rate for serial communication. Defaults to 9600.
            timeout (int, optional): Timeout for serial operations in seconds. Defaults to 1.
            query_interval (float, optional): Interval between device queries in seconds.
                Defaults to 0.1.
        """
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.query_interval = query_interval  # Interval in seconds between 'b' commands
        self.serial_connection = None
        self.running = False
        self.paused = False  # New pause flag
        
    def run(self):
        """Main thread execution - continuously read from serial port"""
        try:
            self.serial_connection = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout
            )
            self.running = True
            last_query_time = 0
            
            while self.running:
                try:
                    current_time = time.time()
                    
                    # Only send 'b' command if not paused
                    if not self.paused and current_time - last_query_time >= self.query_interval:
                        # Log the command being sent
                        self.command_sent.emit('b')
                        
                        self.serial_connection.write(b'b')
                        self.serial_connection.flush()  # Ensure data is sent
                        last_query_time = current_time
                        
                        # Wait a bit for the device to respond
                        time.sleep(0.05)
                        
                        # Now try to read the response
                        data = b''
                        start_time = time.time()
                        last_data_time = time.time()
                        
                        # Read until we find '*' or timeout
                        # Timeout values from config.py
                        max_read_time = READ_TIMEOUT_MAX  # From config: maximum time for complete message
                        idle_timeout = READ_TIMEOUT_IDLE   # From config: timeout when no data arriving
                        
                        while self.running and not self.paused:
                            if self.serial_connection.in_waiting > 0:
                                byte = self.serial_connection.read(1)
                                data += byte
                                last_data_time = time.time()  # Reset idle timer
                                
                                # Check if we've received the termination character
                                if byte == b'*':
                                    break
                            else:
                                # No data available, sleep longer to prevent busy-waiting
                                time.sleep(0.01)  # 10ms instead of 1ms
                            
                            # Calculate elapsed time
                            elapsed = time.time() - start_time
                            
                            # Overall timeout protection (5 seconds max)
                            if elapsed > max_read_time:
                                if len(data) > 0:
                                    self.error_occurred.emit(
                                        f"Read timeout - no termination character received after {max_read_time}s. "
                                        f"Received {len(data)} bytes."
                                    )
                                break
                            
                            # Idle timeout - if no data received for idle_timeout seconds
                            idle_time = time.time() - last_data_time
                            if len(data) > 0 and idle_time > idle_timeout:
                                self.error_occurred.emit(
                                    f"Idle timeout - no data received for {idle_timeout}s. "
                                    f"Received {len(data)} bytes, missing termination character '*'."
                                )
                                break
                        
                        # Process the received data
                        if data:
                            try:
                                # Remove the termination character and decode
                                decoded_data = data.rstrip(b'*').decode('utf-8').strip()
                                if decoded_data:
                                    # Log the full response received
                                    self.response_received.emit('b', decoded_data)
                                    self.data_received.emit(decoded_data)
                            except UnicodeDecodeError:
                                # Try latin-1 if utf-8 fails
                                try:
                                    decoded_data = data.rstrip(b'*').decode('latin-1').strip()
                                    if decoded_data:
                                        # Log the full response received
                                        self.response_received.emit('b', decoded_data)
                                        self.data_received.emit(decoded_data)
                                except Exception as e:
                                    self.error_occurred.emit(f"Decode error: {str(e)}")
                    else:
                        # Small sleep to prevent busy waiting when not querying
                        time.sleep(0.001)
                        
                except serial.SerialException as e:
                    self.error_occurred.emit(f"Serial error: {str(e)}")
                    self.disconnected.emit()  # Notify main window of disconnection
                    self.running = False
                    break
                except Exception as e:
                    self.error_occurred.emit(f"Unexpected error: {str(e)}")
                    
        except serial.SerialException as e:
            self.error_occurred.emit(f"Failed to open port {self.port}: {str(e)}")
        except Exception as e:
            self.error_occurred.emit(f"Unexpected error during initialization: {str(e)}")
        finally:
            self.close_connection()
            
    def stop(self):
        """Stop the serial reading thread"""
        self.running = False
        self.wait()  # Wait for thread to finish
    
    def pause(self):
        """Pause serial reading (stop querying device)"""
        self.paused = True
    
    def resume(self):
        """Resume serial reading (start querying device again)"""
        self.paused = False
        
    def close_connection(self):
        """Close the serial connection"""
        if self.serial_connection and self.serial_connection.is_open:
            try:
                self.serial_connection.close()
            except Exception as e:
                print(f"Error closing serial port: {e}")
                
    def write_data(self, data):
        """Write data to the serial port"""
        if self.serial_connection and self.serial_connection.is_open:
            try:
                if isinstance(data, str):
                    data = data.encode('utf-8')
                self.serial_connection.write(data)
                return True
            except Exception as e:
                self.error_occurred.emit(f"Write error: {str(e)}")
                return False
        return False
