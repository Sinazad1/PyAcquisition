"""
Device Controller (within Acquisition Mode)
Handles all peripheral device control (pump, Tic, chiller)
Extracted from AcquisitionWindow for better separation of concerns

Doc status: done, MK, 01/30/2026
Patch in for pump rate units, MK 02/03/2026
"""
import time

# Import device settings from config
try:
    from modes.utils.config import (PUMP_BAUDRATE, PUMP_TIMEOUT, PUMP_RATE_UNITS,
                                     CHILLER_BAUDRATE, CHILLER_TIMEOUT, TIC_TIMEOUT)
except ImportError:
    # Fallback defaults if config import fails
    PUMP_BAUDRATE = 19200
    PUMP_TIMEOUT = 2.0
    PUMP_RATE_UNITS = 'MM'  # Default to mL/min
    CHILLER_BAUDRATE = 4800
    CHILLER_TIMEOUT = 2.0
    TIC_TIMEOUT = 5

# Import UI constants for colors
from modes.utils.ui_constants import (COLOR_INFO, COLOR_SUCCESS, COLOR_WARNING, COLOR_ERROR,
                          COLOR_PUMP, COLOR_TIC, COLOR_CHILLER)

class DeviceController:
    """
    Controls all peripheral devices
    Provides unified interface for (syringe pump, chiller, tic a, tic b) operations 
    for acquisition mode
    """
    
    def __init__(self, parent_window):
        """
        Initialize device controller
        
        Args:
            parent_window: Reference to acquisition window for logging
        """
        self.parent = parent_window
        
        # Device ports/serials (set by parent)
        self.pump_port = None
        self.chiller_port = None
        self.tic_a_serial = None
        self.tic_b_serial = None
        
        # Persistent TIC threads for protocol execution
        self.tic_threads = {'A': None, 'B': None}
    
    def set_pump_port(self, port):
        """Set syringe pump port"""
        self.pump_port = port
    
    def set_chiller_port(self, port):
        """Set chiller port"""
        self.chiller_port = port
    
    def set_tic_serials(self, tic_a_serial, tic_b_serial):
        """Set Tic serial numbers for both TICs"""
        self.tic_a_serial = tic_a_serial
        self.tic_b_serial = tic_b_serial
    
    def apply_pump_settings(self, settings):
        """
        Apply syringe pump settings from protocol
        
        Args:
            settings: Dictionary of pump settings
        """
        try:
            from modes.hardware.syringe_pump_handler import SyringePumpThread
            
            if not self.pump_port:
                self._log_warning("Pump not configured - skipping pump settings")
                return
            
            # Create temporary pump thread
            pump_thread = SyringePumpThread(self.pump_port, baudrate=PUMP_BAUDRATE)
            
            # Connect command logging
            pump_thread.command_log.connect(self._log_pump_command)
            
            pump_thread.start()
            pump_thread.wait(500)  # Wait for connection
            
            # Apply settings
            if 'diameter' in settings:
                pump_thread.send_command(f"DIA {settings['diameter']}")
                time.sleep(0.1)
            
            if 'direction' in settings:
                pump_thread.send_command(f"DIR {settings['direction']}")
                time.sleep(0.1)
            
            if 'rate' in settings:
                pump_thread.send_command(f"RAT {settings['rate']} {PUMP_RATE_UNITS}") 
                time.sleep(0.1)
            
            if 'volume' in settings:
                pump_thread.send_command(f"VOL {settings['volume']}")
                time.sleep(0.1)
            
            if settings.get('run', False):
                pump_thread.send_command("RUN")
                # Map rate units for display
                rate_units_map = {
                    'MM': 'mL/min',
                    'MH': 'mL/hr',
                    'UM': 'µL/min',
                    'UH': 'µL/hr'
                }
                rate_units_display = rate_units_map.get(PUMP_RATE_UNITS, PUMP_RATE_UNITS)
                self._log_success(
                    f"Pump started: {settings.get('direction', 'INF')} "
                    f"{settings.get('volume', 0)}mL @ {settings.get('rate', 0)}{rate_units_display}",
                    "PUMP"
                )
            else:
                pump_thread.send_command("STP")
                self._log_error("Pump stopped", "PUMP")
            
            # Clean up
            pump_thread.stop()
            pump_thread.wait(500)
            
        except Exception as e:
            self._log_error(f"Error applying pump settings: {str(e)}", "PUMP-ERROR")
    
    def apply_tic_settings(self, settings, tic_id='A'):
        """
        Apply Tic stepper settings from protocol
        
        Args:
            settings: Dictionary of Tic settings
            tic_id: 'A' or 'B' to specify which TIC
        """
        try:
            from modes.hardware.tic_handler import TicThread
            import time
            
            tic_serial = self.tic_a_serial if tic_id == 'A' else self.tic_b_serial
            
            if not tic_serial:
                self._log_warning(f"Tic {tic_id} not configured - skipping Tic settings")
                return
            
            # Create or reuse persistent thread
            if self.tic_threads[tic_id] is None or not self.tic_threads[tic_id].isRunning():
                # Create new thread
                self.tic_threads[tic_id] = TicThread(tic_serial)
                
                # Connect command logging
                self.tic_threads[tic_id].command_log.connect(
                    lambda cmd, resp, tid=tic_id: self._log_tic_command(cmd, resp, tid)
                )
                
                self.tic_threads[tic_id].start()
                time.sleep(0.3)  # Give thread time to initialize
                
                self._log_info(f"Tic {tic_id} thread started", f"TIC-{tic_id}")
            
            tic_thread = self.tic_threads[tic_id]
            
            # IMPORTANT: Apply energize BEFORE velocity
            # Motors must be energized before they can move
            if 'energize' in settings:
                if settings['energize']:
                    tic_thread.energize()
                    self._log_info(f"Tic {tic_id} motor energized", f"TIC-{tic_id}")
                    time.sleep(0.15)  # Give motor time to energize
                else:
                    # De-energize (but don't stop thread)
                    tic_thread.deenergize()
                    self._log_info(f"Tic {tic_id} motor de-energized", f"TIC-{tic_id}")
                    time.sleep(0.1)
            
            # Apply velocity setting after energizing
            if 'velocity' in settings:
                velocity = settings['velocity']
                tic_thread.set_velocity(velocity)
                self._log_info(f"Tic {tic_id} velocity set: {velocity} steps/10000s", f"TIC-{tic_id}")
                time.sleep(0.1)  # Give command time to process
            
            # Keep thread running - don't stop it
            # It will be cleaned up when protocol finishes or new settings applied
            
        except Exception as e:
            self._log_error(f"Error applying Tic {tic_id} settings: {str(e)}", f"TIC-{tic_id}-ERROR")
    
    def apply_chiller_settings(self, settings):
        """
        Apply chiller settings from protocol
        
        Args:
            settings: Dictionary of chiller settings
        """
        try:
            from modes.hardware.chiller_handler import ChillerThread
            
            if not self.chiller_port:
                self._log_warning("Chiller not configured - skipping chiller settings")
                return
            
            # Create temporary chiller thread
            chiller_thread = ChillerThread(self.chiller_port, baudrate=CHILLER_BAUDRATE)
            
            # Connect command logging
            chiller_thread.command_log.connect(self._log_chiller_command)
            
            chiller_thread.start()
            chiller_thread.wait(500)
            
            # Apply temperature setting
            if 'temperature' in settings:
                temp = settings['temperature']
                chiller_thread.set_temperature(temp)
                self._log_info(f"Chiller setpoint: {temp}°C", "CHILLER")
            
            # Apply pump speed
            if 'pump_speed' in settings:
                speed = settings['pump_speed']
                chiller_thread.set_pump_speed(speed)
                self._log_info(f"Chiller pump speed: {speed}%", "CHILLER")
            
            # Start/stop chiller
            if 'start' in settings:
                if settings['start']:
                    chiller_thread.start_chiller()
                    self._log_success("Chiller started", "CHILLER")
                else:
                    chiller_thread.stop_chiller()
                    self._log_error("Chiller stopped", "CHILLER")
            
            # Clean up
            chiller_thread.stop()
            chiller_thread.wait(500)
            
        except Exception as e:
            self._log_error(f"Error applying chiller settings: {str(e)}", "CHILLER-ERROR")
    
    def apply_all_settings(self, pump_settings=None, tic_a_settings=None, tic_b_settings=None, chiller_settings=None):
        """
        Apply settings to all devices
        
        Args:
            pump_settings: Pump settings dict (optional)
            tic_a_settings: Tic A settings dict (optional)
            tic_b_settings: Tic B settings dict (optional)
            chiller_settings: Chiller settings dict (optional)
        """
        if pump_settings:
            self.apply_pump_settings(pump_settings)
        
        if tic_a_settings:
            self.apply_tic_settings(tic_a_settings, 'A')
        
        if tic_b_settings:
            self.apply_tic_settings(tic_b_settings, 'B')
        
        if chiller_settings:
            self.apply_chiller_settings(chiller_settings)
    
    # Logging helpers 
    def _log_info(self, message, log_type="DEVICE"):
        """Log info message"""
        if hasattr(self.parent, 'log_event'):
            self.parent.log_event(message, color=COLOR_INFO, log_type=log_type)
    
    def _log_success(self, message, log_type="DEVICE"):
        """Log success message"""
        if hasattr(self.parent, 'log_event'):
            self.parent.log_event(message, color=COLOR_SUCCESS, log_type=log_type)
    
    def _log_warning(self, message, log_type="DEVICE"):
        """Log warning message"""
        if hasattr(self.parent, 'log_event'):
            self.parent.log_event(message, color=COLOR_WARNING, log_type=log_type)
    
    def _log_error(self, message, log_type="DEVICE"):
        """Log error message"""
        if hasattr(self.parent, 'log_event'):
            self.parent.log_event(message, color=COLOR_ERROR, log_type=log_type)
    
    # Command logging handle
    def _log_pump_command(self, command, response):
        """Log pump command and response"""
        if hasattr(self.parent, 'log_event'):
            self.parent.log_event(
                f"PUMP {command} | {response}",
                color=COLOR_PUMP,
                log_type="PUMP-SERIAL"
            )
    
    def _log_tic_command(self, command, response, tic_id='A'):
        """Log Tic command and response"""
        if hasattr(self.parent, 'log_event'):
            self.parent.log_event(
                f"TIC {tic_id} {command} | {response}",
                color=COLOR_TIC,
                log_type=f"TIC-{tic_id}-SERIAL"
            )
    
    def _log_chiller_command(self, command, response):
        """Log chiller command and response"""
        if hasattr(self.parent, 'log_event'):
            self.parent.log_event(
                f"CHILLER {command} | {response}",
                color=COLOR_CHILLER,
                log_type="CHILLER-SERIAL"
            )
    
    def stop_all_tic_threads(self):
        """Stop all persistent TIC threads"""
        import time
        for tic_id in ['A', 'B']:
            if self.tic_threads[tic_id] and self.tic_threads[tic_id].isRunning():
                self._log_info(f"Stopping Tic {tic_id} thread", f"TIC-{tic_id}")
                self.tic_threads[tic_id].stop()
                self.tic_threads[tic_id].wait(1000)
                self.tic_threads[tic_id] = None
                time.sleep(0.1)
    
    def stop_all_devices(self):
        """
        Stop all devices and put them in a safe stopped state
        Called when program is closing
        """
        import time
        
        # Stop syringe pump
        if self.pump_port:
            try:
                from modes.hardware.syringe_pump_handler import SyringePumpThread
                self._log_info("Stopping syringe pump", "PUMP")
                
                pump_thread = SyringePumpThread(self.pump_port, baudrate=PUMP_BAUDRATE)
                pump_thread.start()
                pump_thread.wait(500)
                
                # Send stop command
                pump_thread.send_command("STP")
                time.sleep(0.1)
                
                pump_thread.stop()
                pump_thread.wait(500)
                
                self._log_success("Syringe pump stopped", "PUMP")
            except Exception as e:
                self._log_error(f"Error stopping pump: {str(e)}", "PUMP-ERROR")
        
        # Stop chiller
        if self.chiller_port:
            try:
                from modes.hardware.chiller_handler import ChillerThread
                self._log_info("Stopping chiller", "CHILLER")
                
                chiller_thread = ChillerThread(self.chiller_port, baudrate=CHILLER_BAUDRATE)
                chiller_thread.start()
                chiller_thread.wait(500)
                
                # Stop the chiller
                chiller_thread.stop_chiller()
                time.sleep(0.1)
                
                chiller_thread.stop()
                chiller_thread.wait(500)
                
                self._log_success("Chiller stopped", "CHILLER")
            except Exception as e:
                self._log_error(f"Error stopping chiller: {str(e)}", "CHILLER-ERROR")
        
        # Stop Tic A
        if self.tic_a_serial:
            try:
                from modes.hardware.tic_handler import TicThread
                self._log_info("Stopping Tic A", "TIC-A")
                
                # Use persistent thread if available, otherwise create temporary
                if self.tic_threads['A'] and self.tic_threads['A'].isRunning():
                    tic_thread = self.tic_threads['A']
                else:
                    tic_thread = TicThread(self.tic_a_serial)
                    tic_thread.start()
                    time.sleep(0.3)
                
                # Set velocity to 0 and deenergize
                tic_thread.set_velocity(0)
                time.sleep(0.1)
                tic_thread.deenergize()
                time.sleep(0.1)
                
                if self.tic_threads['A'] is None or not self.tic_threads['A'].isRunning():
                    tic_thread.stop()
                    tic_thread.wait(500)
                
                self._log_success("Tic A stopped and deenergized", "TIC-A")
            except Exception as e:
                self._log_error(f"Error stopping Tic A: {str(e)}", "TIC-A-ERROR")
        
        # Stop Tic B
        if self.tic_b_serial:
            try:
                from modes.hardware.tic_handler import TicThread
                self._log_info("Stopping Tic B", "TIC-B")
                
                # Use persistent thread if available, otherwise create temporary
                if self.tic_threads['B'] and self.tic_threads['B'].isRunning():
                    tic_thread = self.tic_threads['B']
                else:
                    tic_thread = TicThread(self.tic_b_serial)
                    tic_thread.start()
                    time.sleep(0.3)
                
                # Set velocity to 0 and deenergize
                tic_thread.set_velocity(0)
                time.sleep(0.1)
                tic_thread.deenergize()
                time.sleep(0.1)
                
                if self.tic_threads['B'] is None or not self.tic_threads['B'].isRunning():
                    tic_thread.stop()
                    tic_thread.wait(500)
                
                self._log_success("Tic B stopped and deenergized", "TIC-B")
            except Exception as e:
                self._log_error(f"Error stopping Tic B: {str(e)}", "TIC-B-ERROR")
        
        # Stop all persistent TIC threads
        self.stop_all_tic_threads()
