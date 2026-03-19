"""
Syringe Pump Controller Module
Handles communication and control interface for syringe pump
Uses serial communication with specific command protocol

Doc status: done, MK, 01/30/2026
"""
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
                              QLabel, QPushButton, QLineEdit, QComboBox,
                              QGroupBox, QTextEdit, QMessageBox)
from PySide6.QtCore import Qt, QThread, Signal
import serial
import serial.tools.list_ports
import time

# Import configuration settings
try:
    from modes.utils.config import SYRINGE_PUMP_PORT
except ImportError:
    SYRINGE_PUMP_PORT = None

class SyringePumpThread(QThread):
    """Thread for syringe pump serial communication"""
    message_received = Signal(str)
    error_occurred = Signal(str)
    connection_status = Signal(bool, str)  # status, message
    debug_message = Signal(str)  # For raw byte debugging
    command_log = Signal(str, str)  # command, response (for logging all communications)
    
    def __init__(self, port, baudrate=19200, debug=False):
        """
        Initialize the syringe pump handler thread.
        
        Sets up serial communication and control for syringe pump operations.
        
        Args:
            port (str): COM port for syringe pump communication.
            baudrate (int, optional): Baud rate for serial communication. Defaults to 19200.
            debug (bool, optional): Enable debug logging. Defaults to False.
        """
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.serial_connection = None
        self.running = False
        self.debug = debug
        
    def run(self):
        """Initialize connection and verify device"""
        try:
            self.serial_connection = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=2.0,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS
            )
            self.running = True
            
            # Small delay for device to be ready
            time.sleep(0.1)
            
            # Send VER command to identify device
            response = self.send_command("VER")
            if response:
                self.message_received.emit(f"Device identified: {response}")
                self.connection_status.emit(True, f"Connected to {self.port}")
                
                # Don't send STP - let the pump continue whatever it was doing
                # User can manually stop if needed
            else:
                self.error_occurred.emit("No response from device")
                self.connection_status.emit(False, "Device not responding")
                self.running = False
                
        except serial.SerialException as e:
            self.error_occurred.emit(f"Failed to open port {self.port}: {str(e)}")
            self.connection_status.emit(False, str(e))
        except Exception as e:
            self.error_occurred.emit(f"Unexpected error: {str(e)}")
            self.connection_status.emit(False, str(e))
    
    def send_command(self, command):
        """
        Send command to syringe pump with proper formatting
        Commands are wrapped with STX, end with CR, and terminate with ETX
        
        Args:
            command: Command string (e.g., "VER", "STP", "RUN")
            
        Returns:
            Response string or None if error
        """
        if not self.serial_connection or not self.serial_connection.is_open:
            return None
            
        try:
            stx = b'\x02'
            etx = b'\x03'

            def _parse_raw_response(raw_bytes):
                """Parse both framed (STX/ETX) and plain ASCII responses."""
                if not raw_bytes:
                    return b''
                if stx in raw_bytes and etx in raw_bytes:
                    start = raw_bytes.rfind(stx) + 1
                    end = raw_bytes.find(etx, start)
                    if end > start:
                        return raw_bytes[start:end].replace(b'\r', b'').replace(b'\n', b'')
                return raw_bytes.replace(b'\r', b'').replace(b'\n', b'').strip()

            command_bytes = command.encode('ascii')
            payloads = [
                command_bytes + b'\r',                 # common plain format
                stx + command_bytes + b'\r' + etx,     # framed format
                command_bytes + b'\r\n',               # tolerant fallback
            ]

            for payload in payloads:
                if self.debug:
                    self.debug_message.emit(f"Sending: {payload.hex()} ({payload})")

                self.serial_connection.reset_input_buffer()
                self.serial_connection.reset_output_buffer()
                self.serial_connection.write(payload)
                self.serial_connection.flush()

                raw_response = b''
                start_time = time.time()
                timeout = 2.0

                while time.time() - start_time < timeout:
                    waiting = self.serial_connection.in_waiting
                    if waiting > 0:
                        raw_response += self.serial_connection.read(waiting)
                        if b'\n' in raw_response or etx in raw_response:
                            break
                    time.sleep(0.01)

                parsed = _parse_raw_response(raw_response)

                if self.debug:
                    self.debug_message.emit(f"Received raw: {raw_response.hex()} ({raw_response})")
                    self.debug_message.emit(f"Parsed response: {parsed}")

                if not parsed:
                    continue

                try:
                    decoded = parsed.decode('ascii').strip()
                except UnicodeDecodeError:
                    try:
                        decoded = parsed.decode('latin-1').strip()
                    except Exception:
                        hex_resp = parsed.hex()
                        self.command_log.emit(f"TX: {command}", f"RX: HEX: {hex_resp}")
                        return hex_resp

                if decoded:
                    status_info = self.decode_status(decoded)
                    self.command_log.emit(f"TX: {command}", f"RX: {decoded} [{status_info}]")
                    return decoded

            self.command_log.emit(f"TX: {command}", "RX: <No Response>")
            return None
                
        except Exception as e:
            self.error_occurred.emit(f"Command error: {str(e)}")
            self.command_log.emit(f"TX: {command}", f"RX: <Error: {str(e)}>")
            import traceback
            traceback.print_exc()
            return None
    
    def decode_status(self, response):
        """
        Decode pump status response (e.g., "0S?", "IS?", etc.)
        
        Status byte format:
        - Bit 0 (1): Stopped
        - Bit 1 (2): Infusing  
        - Bit 2 (4): Withdrawing
        - Bit 3 (8): Paused
        - Bit 4 (16): In target volume mode
        - Bit 5 (32): Alarm triggered
        
        Returns decoded status string
        """
        if not response or len(response) < 1:
            return "Unknown"
        
        try:
            # First character is the status byte (as ASCII character)
            status_char = response[0]
            
            # Common status codes
            if status_char == '0':
                return "Stopped (Ready)"
            elif status_char == 'I':
                return "Infusing"
            elif status_char == 'W':
                return "Withdrawing"
            elif status_char == 'X':
                return "Paused (Infusing)"
            elif status_char == 'Y':
                return "Paused (Withdrawing)"
            elif status_char == 'T':
                return "Target reached"
            elif status_char == 'A':
                return "ALARM - Stopped"
            elif status_char == '*':
                return "ALARM - Infusing"
            elif status_char == '>':
                return "ALARM - Withdrawing"
            elif status_char == 'S':
                return "Stalled"
            else:
                # Try to interpret as hex status byte
                try:
                    status_byte = int(status_char, 16) if status_char.isdigit() or status_char in 'ABCDEF' else ord(status_char)
                    parts = []
                    if status_byte & 1:
                        parts.append("Stopped")
                    if status_byte & 2:
                        parts.append("Infusing")
                    if status_byte & 4:
                        parts.append("Withdrawing")
                    if status_byte & 8:
                        parts.append("Paused")
                    if status_byte & 32:
                        parts.append("ALARM")
                    return " | ".join(parts) if parts else f"Status: {status_char}"
                except:
                    return f"Status: {status_char}"
        except:
            return response
    
    def stop(self):
        """Stop the thread and close connection"""
        self.running = False
        
        # Close serial connection if it exists
        # Don't send STP command - let the pump continue running
        if self.serial_connection:
            try:
                if self.serial_connection.is_open:
                    # Just close the port without stopping the pump
                    self.serial_connection.close()
                    time.sleep(0.2)  # Give OS time to release the port
                    
            except Exception as e:
                print(f"Error closing syringe pump connection: {e}")
            finally:
                # Set to None to ensure it's released
                self.serial_connection = None
        
        # Wait for thread to finish if it's still running
        if self.isRunning():
            self.wait(2000)
