"""
Chiller Handler Module
Handles communication with DYNEO DD-200F (Julabo) chiller
Uses serial communication with specific protocol

Doc status: done, MK, 01/30/2026
"""
from PySide6.QtCore import QThread, Signal
import serial
import time


class ChillerThread(QThread):
    """Thread for chiller serial communication"""
    temperature_received = Signal(float)  # Current temperature
    status_received = Signal(bool)  # Running status (True=running, False=stopped)
    setpoint_confirmed = Signal(float)  # Setpoint confirmation
    pump_speed_confirmed = Signal(int)  # Pump speed confirmation
    error_occurred = Signal(str)
    connection_status = Signal(bool, str)  # status, message
    command_log = Signal(str, str)  # command, response (for logging all communications)
    
    def __init__(self, port, baudrate=4800):
        """
        Initialize the chiller handler thread.
        
        Sets up serial communication and control for the chiller device.
        
        Args:
            port (str): COM port for chiller communication.
            baudrate (int, optional): Baud rate for serial communication. Defaults to 4800.
        """
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.serial_connection = None
        self.running = False
        self._stop_requested = False
        
    def run(self):
        """Initialize connection and verify device"""
        try:
            self.serial_connection = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=2.0,
                parity=serial.PARITY_EVEN,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.SEVENBITS
            )
            self.running = True
            
            # Small delay for device to be ready
            time.sleep(0.2)
            
            # Test connection by reading temperature
            temp = self.read_temperature()
            if temp is not None:
                self.connection_status.emit(True, f"Connected to {self.port}")
                self.temperature_received.emit(temp)
            else:
                self.error_occurred.emit("No response from chiller")
                self.connection_status.emit(False, "Chiller not responding")
                self.running = False
                
        except serial.SerialException as e:
            self.error_occurred.emit(f"Failed to open port {self.port}: {str(e)}")
            self.connection_status.emit(False, str(e))
        except Exception as e:
            self.error_occurred.emit(f"Unexpected error: {str(e)}")
            self.connection_status.emit(False, str(e))
    
    def send_command(self, command):
        """
        Send command to chiller
        Commands must end with carriage return [\r]
        Response terminated with \n [ASCII 10]
        
        Args:
            command: Command string (e.g., "in_pv_00", "out_mode_05 1")
            
        Returns:
            Response string or None if error
        """
        if not self.serial_connection or not self.serial_connection.is_open:
            return None
            
        try:
            payloads = [
                (command + '\r').encode('ascii'),
                (command + '\r\n').encode('ascii'),
            ]

            for payload in payloads:
                self.serial_connection.reset_input_buffer()
                self.serial_connection.reset_output_buffer()
                self.serial_connection.write(payload)
                self.serial_connection.flush()

                # First try canonical newline response.
                response = self.serial_connection.read_until(b'\n', size=100)
                if not response:
                    # Some firmware variants terminate with CR only.
                    response = self.serial_connection.read_until(b'\r', size=100)
                if not response and self.serial_connection.in_waiting > 0:
                    response = self.serial_connection.read(self.serial_connection.in_waiting)

                if not response:
                    continue

                decoded = response.decode('ascii', errors='ignore').strip('\r\n \t\x00')
                if decoded:
                    self.command_log.emit(f"TX: {command}", f"RX: {decoded}")
                    return decoded

            self.command_log.emit(f"TX: {command}", "RX: <No Response>")
            return None
                
        except serial.SerialException as e:
            self.error_occurred.emit(f"Serial error: {str(e)}")
            self.command_log.emit(f"TX: {command}", f"RX: <Error: {str(e)}>")
            return None
        except Exception as e:
            self.error_occurred.emit(f"Command error: {str(e)}")
            self.command_log.emit(f"TX: {command}", f"RX: <Error: {str(e)}>")
            return None
    
    def read_temperature(self):
        """
        Read current temperature from chiller
        Command: in_pv_00
        
        Returns:
            Temperature as float or None if error
        """
        response = self.send_command("in_pv_00")
        if response:
            try:
                # Response format typically: "25.50" or similar
                temp = float(response)
                return temp
            except ValueError:
                self.error_occurred.emit(f"Invalid temperature response: {response}")
                return None
        return None
    
    def start_chiller(self):
        """
        Start the chiller
        Command: out_mode_05 1
        
        Returns:
            True if successful, False otherwise
        """
        response = self.send_command("out_mode_05 1")
        if response is not None:
            self.status_received.emit(True)
            return True
        return False
    
    def stop_chiller(self):
        """
        Stop the chiller
        Command: out_mode_05 0
        
        Returns:
            True if successful, False otherwise
        """
        response = self.send_command("out_mode_05 0")
        if response is not None:
            self.status_received.emit(False)
            return True
        return False
    
    def set_temperature(self, temperature):
        """
        Set target temperature
        Command: out_sp_00 xxx.xx
        
        Args:
            temperature: Target temperature as float
            
        Returns:
            True if successful, False otherwise
        """
        # Format to 2 decimal places
        temp_str = f"{temperature:.2f}"
        response = self.send_command(f"out_sp_00 {temp_str}")
        
        if response is not None:
            self.setpoint_confirmed.emit(temperature)
            return True
        return False
    
    def set_pump_speed(self, speed_percent):
        """
        Set pump capacity (speed) as percentage
        Command: out_sp_27 xxx
        
        Args:
            speed_percent: Pump speed 0-100%
            
        Returns:
            True if successful, False otherwise
        """
        # Clamp to 0-100
        speed = max(0, min(100, int(speed_percent)))
        response = self.send_command(f"out_sp_27 {speed}")
        
        if response is not None:
            self.pump_speed_confirmed.emit(speed)
            return True
        return False
    
    def query_status(self):
        """
        Query current status (temperature)
        Called periodically to update display
        """
        if not self.running:
            return
        
        temp = self.read_temperature()
        if temp is not None:
            self.temperature_received.emit(temp)
    
    def stop(self):
        """Stop the thread"""
        self._stop_requested = True
        self.running = False
        
        # Close serial connection if it exists
        if self.serial_connection:
            try:
                if self.serial_connection.is_open:
                    self.serial_connection.close()
                    time.sleep(0.2)  # Give OS time to release the port
            except:
                pass
            finally:
                # Set to None to ensure it's released
                self.serial_connection = None
        
        self.quit()
        
        # Wait for thread to finish if it's still running
        if self.isRunning():
            self.wait(2000)
