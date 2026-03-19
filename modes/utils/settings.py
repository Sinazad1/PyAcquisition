"""
Settings Manager
Reads configuration from external config.ini file at runtime

Doc status: done, MK, 01/30/2026
"""
import configparser
import logging
from pathlib import Path
import shutil
import sys

logger = logging.getLogger(__name__)


def get_executable_dir():
    """Get directory where the executable is located (actual .exe, not temp extraction)"""
    if getattr(sys, 'frozen', False):
        # Running as compiled executable        
        # Method 1: Try sys.argv[0] - this is the path used to launch the program
        try:
            exe_path = Path(sys.argv[0]).resolve()
            if exe_path.is_file():
                return exe_path.parent
        except:
            pass
        
        # Method 2: Try __file__ if available
        try:
            return Path(__file__).parent
        except:
            pass
        
        # Method 3: Fallback to sys.executable parent
        return Path(sys.executable).parent
    else:
        # Running as script
        return Path(__file__).parent

def find_config_file():
    """Find config.ini by checking multiple possible locations"""
    # Check if running as compiled exe (multiple detection methods in case compiled)
    is_frozen = (
        getattr(sys, 'frozen', False) or
        getattr(sys, '_MEIPASS', False) or
        '__compiled__' in globals()
    )
    
    # Location 1: Executable directory (for packaged .exe)
    if is_frozen:
        try:
            exe_dir = get_executable_dir()
            # Preferred: side-by-side config next to the executable.
            config_path = exe_dir / "config.ini"
            if config_path.exists():
                return config_path

            # Fallback for one-folder bundles where data is under _internal.
            internal_config = exe_dir / "_internal" / "config.ini"
            if internal_config.exists():
                return internal_config
        except Exception:
            pass

        # Last frozen fallback: current working directory.
        config_path = Path.cwd() / "config.ini"
        if config_path.exists():
            return config_path
    
    # Location 2: Project root directory (for development)
    # Find project root by looking for main.py
    if not is_frozen:
        try:
            # Start from this file's location
            current_dir = Path(__file__).parent
            
            # Walk up the directory tree looking for main.py
            for parent in [current_dir] + list(current_dir.parents):
                main_py = parent / "main.py"
                if main_py.exists():
                    # Found project root, check for config.ini there
                    config_path = parent / "config.ini"
                    if config_path.exists():
                        return config_path
                    # If config.ini doesn't exist in root, we'll create it here later
                    break
        except:
            pass
    
    # Location 3: Script directory (fallback for development)
    try:
        script_dir = Path(__file__).parent
        config_path = script_dir / "config.ini"
        if config_path.exists():
            return config_path
    except:
        pass
    
    # Location 4: Current working directory (fallback)
    config_path = Path.cwd() / "config.ini"
    if config_path.exists():
        return config_path
    
    # Location 5: User's home directory
    config_path = Path.home() / ".serial_data_monitor" / "config.ini"
    if config_path.exists():
        return config_path
    
    return None


def _ensure_frozen_user_config():
    """
    Ensure a writable config.ini exists next to the executable in frozen mode.
    If missing, copy from bundled _internal/config.ini when available.
    """
    is_frozen = (
        getattr(sys, 'frozen', False) or
        getattr(sys, '_MEIPASS', False) or
        '__compiled__' in globals()
    )
    if not is_frozen:
        return

    try:
        exe_dir = get_executable_dir()
        user_config = exe_dir / "config.ini"
        if user_config.exists():
            return

        internal_config = exe_dir / "_internal" / "config.ini"
        if internal_config.exists():
            shutil.copy2(internal_config, user_config)
            logger.info("Created user config from bundled config: %s", user_config)
            return

        create_default_config_file(exe_dir)
        logger.info("Created default user config next to executable: %s", user_config)
    except Exception as e:
        logger.warning("Could not ensure user config in frozen mode: %s", e)

def save_ports_to_config(dut_port=None, ref1_port=None, ref2_port=None, 
                        pump_port=None, chiller_port=None, tic_a_serial=None, tic_b_serial=None):
    """
    Save selected port assignments to config.ini
    
    Args:
        dut_port: DUT COM port
        ref1_port: IBP Reference 1 COM port
        ref2_port: IBP Reference 2 COM port
        pump_port: Syringe pump COM port
        chiller_port: Chiller COM port
        tic_a_serial: Tic A serial number
        tic_b_serial: Tic B serial number
    
    Returns:
        bool: True if successful, False otherwise
    """
    # Find config file
    config_path = find_config_file()
    
    if config_path is None:
        # No config file exists, try to create one next to exe or in project root
        if getattr(sys, 'frozen', False):
            try:
                exe_dir = Path(sys.argv[0]).resolve().parent
                config_path = exe_dir / "config.ini"
            except:
                return False
        else:
            # Find project root by looking for main.py
            try:
                current_dir = Path(__file__).parent
                for parent in [current_dir] + list(current_dir.parents):
                    main_py = parent / "main.py"
                    if main_py.exists():
                        config_path = parent / "config.ini"
                        break
                else:
                    # Fallback to script directory if main.py not found
                    config_path = Path(__file__).parent / "config.ini"
            except:
                return False
        
        # Create default config file first
        if not create_default_config_file(config_path.parent):
            return False
    
    # Read existing config
    config = configparser.ConfigParser()
    try:
        config.read(config_path)
        
        # Ensure Ports section exists
        if 'Ports' not in config:
            config.add_section('Ports')
        
        # Update port values (only update non-None values)
        if dut_port is not None:
            config.set('Ports', 'DUT_COM_PORT', dut_port if dut_port else '')
        if ref1_port is not None:
            config.set('Ports', 'IBP_REF1_PORT', ref1_port if ref1_port else '')
        if ref2_port is not None:
            config.set('Ports', 'IBP_REF2_PORT', ref2_port if ref2_port else '')
        if pump_port is not None:
            config.set('Ports', 'SYRINGE_PUMP_PORT', pump_port if pump_port else '')
        if chiller_port is not None:
            config.set('Ports', 'CHILLER_PORT', chiller_port if chiller_port else '')
        if tic_a_serial is not None:
            config.set('Ports', 'TIC_A_SERIAL_NUMBER', tic_a_serial if tic_a_serial else '')
        if tic_b_serial is not None:
            config.set('Ports', 'TIC_B_SERIAL_NUMBER', tic_b_serial if tic_b_serial else '')
        
        # Write back to file
        with open(config_path, 'w') as f:
            config.write(f)
        
        logger.info("Saved port assignments to: %s", config_path)
        return True
        
    except Exception as e:
        logger.error("Error saving config file: %s", e)
        return False

def save_cn0359_sensors_to_config(sensor_configs, enabled=None):
    """
    Save CN0359 sensor->COM assignments to config.ini.

    Args:
        sensor_configs: list of tuples (unit_id, port, address)
        enabled: optional bool to set [CN0359] enabled flag

    Returns:
        bool: True if successful, False otherwise
    """
    config_path = find_config_file()

    if config_path is None:
        if getattr(sys, 'frozen', False):
            try:
                exe_dir = Path(sys.argv[0]).resolve().parent
                config_path = exe_dir / "config.ini"
            except Exception:
                return False
        else:
            try:
                current_dir = Path(__file__).parent
                for parent in [current_dir] + list(current_dir.parents):
                    main_py = parent / "main.py"
                    if main_py.exists():
                        config_path = parent / "config.ini"
                        break
                else:
                    config_path = Path(__file__).parent / "config.ini"
            except Exception:
                return False

        if not create_default_config_file(config_path.parent):
            return False

    config = configparser.ConfigParser()
    try:
        config.read(config_path)

        if 'CN0359' not in config:
            config.add_section('CN0359')

        if enabled is not None:
            config.set('CN0359', 'enabled', 'true' if enabled else 'false')

        # Reset all sensor ports first so removed rows do not linger.
        for i in range(1, 9):
            config.set('CN0359', f'sensor_{i}_port', '')

        seen_units = set()
        seen_ports = set()
        for entry in sensor_configs or []:
            if not entry:
                continue
            unit_id = int(entry[0])
            port = str(entry[1]).strip() if len(entry) > 1 else ''
            if unit_id < 1 or unit_id > 8 or not port:
                continue
            if unit_id in seen_units or port in seen_ports:
                continue
            config.set('CN0359', f'sensor_{unit_id}_port', port)
            seen_units.add(unit_id)
            seen_ports.add(port)

        with open(config_path, 'w') as f:
            config.write(f)

        logger.info("Saved CN0359 sensor assignments to: %s", config_path)
        return True
    except Exception as e:
        logger.error("Error saving CN0359 config file: %s", e)
        return False

def create_default_config_file(directory):
    """Create a default config.ini file in the specified directory"""
    config_path = directory / "config.ini"
    
    config_content = """# 
# autogenerated config file
# 
# 

[Serial]
baudrate = 115200
read_timeout_max = 30.0
read_timeout_idle = 3.0
query_interval = 10

[Ports]
dut_com_port = 
ibp_ref1_port = 
ibp_ref2_port = 
syringe_pump_port = 
chiller_port = 
tic_a_serial_number = 
tic_b_serial_number = 

[Pump]
baudrate = 19200
timeout = 2.0

[Chiller]
baudrate = 4800
timeout = 2.0

[Tic]
timeout = 5

[CN0359]
enabled = false
sensor_1_port = 
sensor_2_port = 
sensor_3_port = 
sensor_4_port = 
sensor_5_port = 
sensor_6_port = 
sensor_7_port = 
sensor_8_port = 
baudrate = 115200
poll_interval = 10

[IonIn]
enabled = false

[Analysis]
analysis_model = Dual-Range Aly Model 2
constrain_low_range = False

[Developer]
devmode = True

"""
    
    try:
        with open(config_path, 'w') as f:
            f.write(config_content)
        return True
    except Exception as e:
        logger.error("Error creating config file: %s", e)
        return False

def load_settings():
    """Load settings from config.ini or use defaults"""
    _ensure_frozen_user_config()
    
    # Default values (used if config.ini not found)
    defaults = {
        # DUT Serial Settings
        'BAUDRATE': 115200,
        'TIMEOUT': 10.0,
        'READ_TIMEOUT_MAX': 30.0,
        'READ_TIMEOUT_IDLE': 3.0,
        'QUERY_INTERVAL': 10,
        
        # IBP Settings
        'ENABLE_IBP_REFERENCES': True,
        'IBP_BAUDRATE': 115200,
        'IBP_TIMEOUT': 2.0,
        
        # Port Assignments
        'DUT_COM_PORT': None,
        'IBP_REF1_PORT': None,
        'IBP_REF2_PORT': None,
        'SYRINGE_PUMP_PORT': None,
        'CHILLER_PORT': None,
        'TIC_A_SERIAL_NUMBER': None,
        'TIC_B_SERIAL_NUMBER': None,
        
        # Device-Specific Settings
        'PUMP_BAUDRATE': 19200,
        'PUMP_TIMEOUT': 2.0,
        'PUMP_RATE_UNITS': 'MM',  # MM=mL/min, MH=mL/hr, UM=µL/min, UH=µL/hr
        'CHILLER_BAUDRATE': 4800,
        'CHILLER_TIMEOUT': 2.0,
        'TIC_TIMEOUT': 5,
        
        # Data Display Settings
        'MAX_OUTPUT_LINES': 1000,
        'MAX_GRAPH_POINTS': 1000,
        'MAX_DUT_UNITS': 8,
        
        # Data Management
        'TIMESTAMP_FORMAT': "%Y-%m-%d %H:%M:%S.%f",
        'SAVE_DIRECTORY': "data",
        
        # Analysis Settings
        'ANALYSIS_MODEL': "Dual-Range Aly Model 2",
        'CONSTRAIN_LOW_RANGE': False,
        
        # Developer Settings
        'DEVMODE': True,
        
        # CN0359 Direct Sensor Settings
        'CN0359_ENABLED': False,
        'CN0359_BAUDRATE': 115200,
        'CN0359_POLL_INTERVAL': 10,
        # list of (unit_id, port, address) tuples; address is always ""
        # to keep compatibility with existing CN0359Handler call sites.
        'CN0359_SENSORS': [],
        # Optional feature flag to parse data through IonIn compatibility adapter.
        'IONIN_ENABLED': False,
    }
    
    # Try to find config.ini
    config_path = find_config_file()
    
    if config_path is None:
        logger.warning("Config file not found. Using default settings.")
        # Don't prompt here - will be handled by acquisition_window after Qt starts
        return defaults
    
    # Read config.ini
    config = configparser.ConfigParser()
    try:
        config.read(config_path)
        logger.info("Loaded settings from: %s", config_path)
        
        # Read Serial section
        if 'Serial' in config:
            defaults['BAUDRATE'] = config.getint('Serial', 'BAUDRATE', fallback=defaults['BAUDRATE'])
            defaults['TIMEOUT'] = config.getfloat('Serial', 'TIMEOUT', fallback=defaults['TIMEOUT'])
            defaults['READ_TIMEOUT_MAX'] = config.getfloat('Serial', 'READ_TIMEOUT_MAX', fallback=defaults['READ_TIMEOUT_MAX'])
            defaults['READ_TIMEOUT_IDLE'] = config.getfloat('Serial', 'READ_TIMEOUT_IDLE', fallback=defaults['READ_TIMEOUT_IDLE'])
            defaults['QUERY_INTERVAL'] = config.getint('Serial', 'QUERY_INTERVAL', fallback=defaults['QUERY_INTERVAL'])
        
        # Read Ports section
        if 'Ports' in config:
            # Read port values and strip whitespace and quotes
            dut_port = config.get('Ports', 'DUT_COM_PORT', fallback='').strip().strip('"').strip("'")
            ref1_port = config.get('Ports', 'IBP_REF1_PORT', fallback='').strip().strip('"').strip("'")
            ref2_port = config.get('Ports', 'IBP_REF2_PORT', fallback='').strip().strip('"').strip("'")
            pump_port = config.get('Ports', 'SYRINGE_PUMP_PORT', fallback='').strip().strip('"').strip("'")
            chiller_port = config.get('Ports', 'CHILLER_PORT', fallback='').strip().strip('"').strip("'")
            tic_a_serial = config.get('Ports', 'TIC_A_SERIAL_NUMBER', fallback='').strip().strip('"').strip("'")
            tic_b_serial = config.get('Ports', 'TIC_B_SERIAL_NUMBER', fallback='').strip().strip('"').strip("'")
            
            # Convert empty strings to None, keep valid values
            defaults['DUT_COM_PORT'] = dut_port if dut_port else None
            defaults['IBP_REF1_PORT'] = ref1_port if ref1_port else None
            defaults['IBP_REF2_PORT'] = ref2_port if ref2_port else None
            defaults['SYRINGE_PUMP_PORT'] = pump_port if pump_port else None
            defaults['CHILLER_PORT'] = chiller_port if chiller_port else None
            defaults['TIC_A_SERIAL_NUMBER'] = tic_a_serial if tic_a_serial else None
            defaults['TIC_B_SERIAL_NUMBER'] = tic_b_serial if tic_b_serial else None
        
        # Read IBP section
        if 'IBP' in config:
            defaults['ENABLE_IBP_REFERENCES'] = config.getboolean('IBP', 'ENABLE_IBP_REFERENCES', fallback=defaults['ENABLE_IBP_REFERENCES'])
        
        # Read Device sections
        if 'Pump' in config:
            defaults['PUMP_BAUDRATE'] = config.getint('Pump', 'BAUDRATE', fallback=defaults['PUMP_BAUDRATE'])
            defaults['PUMP_TIMEOUT'] = config.getfloat('Pump', 'TIMEOUT', fallback=defaults['PUMP_TIMEOUT'])
            # Read rate units (MM, MH, UM, UH) with MM as default
            rate_units = config.get('Pump', 'RATE_UNITS', fallback='MM').strip().upper()
            # Validate rate units
            if rate_units in ['MM', 'MH', 'UM', 'UH']:
                defaults['PUMP_RATE_UNITS'] = rate_units
            else:
                logger.warning("Invalid pump rate units '%s' in config. Using default 'MM'", rate_units)
                defaults['PUMP_RATE_UNITS'] = 'MM'
        
        if 'Chiller' in config:
            defaults['CHILLER_BAUDRATE'] = config.getint('Chiller', 'BAUDRATE', fallback=defaults['CHILLER_BAUDRATE'])
            defaults['CHILLER_TIMEOUT'] = config.getfloat('Chiller', 'TIMEOUT', fallback=defaults['CHILLER_TIMEOUT'])
        
        if 'Tic' in config:
            defaults['TIC_TIMEOUT'] = config.getint('Tic', 'TIMEOUT', fallback=defaults['TIC_TIMEOUT'])
        
        # Read Analysis section
        if 'Analysis' in config:
            defaults['ANALYSIS_MODEL'] = config.get('Analysis', 'ANALYSIS_MODEL', fallback=defaults['ANALYSIS_MODEL']).strip()
            defaults['CONSTRAIN_LOW_RANGE'] = config.getboolean('Analysis', 'CONSTRAIN_LOW_RANGE', fallback=defaults['CONSTRAIN_LOW_RANGE'])
        
        # Read Developer section
        if 'Developer' in config:
            defaults['DEVMODE'] = config.getboolean('Developer', 'DEVMODE', fallback=defaults['DEVMODE'])
        
        # ---- CN0359 DIRECT SENSOR CONFIGURATION ----
        # This section reads config.ini [CN0359] and builds the list of
        # sensors the app will poll directly (instead of going through
        # the Teensy board).  When enabled=false, none of this matters --
        # the app uses the old Teensy/DutHandler path.
        if 'CN0359' in config:
            # Master switch: true = use CN0359 sensors, false = use Teensy
            defaults['CN0359_ENABLED'] = config.getboolean('CN0359', 'enabled', fallback=False)

            # Validate baudrate -- CN0359 uses 115200, but we accept other
            # standard rates in case someone has custom firmware
            cn0359_baudrate = config.getint('CN0359', 'baudrate', fallback=115200)
            if cn0359_baudrate not in (9600, 19200, 38400, 57600, 115200):
                logger.warning("CN0359 baudrate %d is non-standard, using 115200", cn0359_baudrate)
                cn0359_baudrate = 115200
            defaults['CN0359_BAUDRATE'] = cn0359_baudrate

            # Validate poll interval -- how many seconds between each poll cycle.
            # Must be at least 1 second to avoid overwhelming the sensors.
            cn0359_poll = config.getint('CN0359', 'poll_interval', fallback=10)
            if cn0359_poll < 1:
                logger.warning("CN0359 poll_interval must be >= 1, got %d, using 1", cn0359_poll)
                cn0359_poll = 1
            defaults['CN0359_POLL_INTERVAL'] = cn0359_poll

            # Build the sensor list from config.ini entries:
            #   sensor_1_port = COM3     <- which USB-to-serial port
            # Address fields are intentionally ignored for V2 and bare "poll\n".
            # We support up to 8 sensors (sensor_1 through sensor_8).
            # Only sensors with a port configured are included.
            sensors = []
            seen_ports = set()  # track ports to catch duplicates
            for i in range(1, 9):
                port_key = f'sensor_{i}_port'
                port = config.get('CN0359', port_key, fallback='').strip().strip('"').strip("'")

                # Skip sensors with no port configured
                if not port:
                    continue

                # Each sensor must be on a different COM port
                if port in seen_ports:
                    logger.warning("sensor_%d_port '%s' is duplicate, skipping", i, port)
                    continue
                seen_ports.add(port)

                # Store as (unit_id, port, address) tuple. Address is fixed to
                # empty string so the handler always sends bare "poll\n".
                sensors.append((i, port, ""))

            defaults['CN0359_SENSORS'] = sensors

        # ---- IONIN COMPATIBILITY FLAG ----
        if 'IonIn' in config:
            defaults['IONIN_ENABLED'] = config.getboolean('IonIn', 'enabled', fallback=defaults['IONIN_ENABLED'])
            
    except Exception as e:
        logger.error("Error reading config file: %s", e)
        logger.warning("Using default settings")
    
    return defaults

# Load settings when module is imported
_settings = load_settings()
_config_file_found = find_config_file() is not None  # Track if config exists

# Export as module-level variables for compatibility with config.py
BAUDRATE = _settings['BAUDRATE']
TIMEOUT = _settings['TIMEOUT']
READ_TIMEOUT_MAX = _settings['READ_TIMEOUT_MAX']
READ_TIMEOUT_IDLE = _settings['READ_TIMEOUT_IDLE']
QUERY_INTERVAL = _settings['QUERY_INTERVAL']
ENABLE_IBP_REFERENCES = _settings['ENABLE_IBP_REFERENCES']
IBP_BAUDRATE = _settings['IBP_BAUDRATE']
IBP_TIMEOUT = _settings['IBP_TIMEOUT']
DUT_COM_PORT = _settings['DUT_COM_PORT']
IBP_REF1_PORT = _settings['IBP_REF1_PORT']
IBP_REF2_PORT = _settings['IBP_REF2_PORT']
SYRINGE_PUMP_PORT = _settings['SYRINGE_PUMP_PORT']
CHILLER_PORT = _settings['CHILLER_PORT']
TIC_A_SERIAL_NUMBER = _settings['TIC_A_SERIAL_NUMBER']
TIC_B_SERIAL_NUMBER = _settings['TIC_B_SERIAL_NUMBER']
PUMP_BAUDRATE = _settings['PUMP_BAUDRATE']
PUMP_TIMEOUT = _settings['PUMP_TIMEOUT']
PUMP_RATE_UNITS = _settings['PUMP_RATE_UNITS']
CHILLER_BAUDRATE = _settings['CHILLER_BAUDRATE']
CHILLER_TIMEOUT = _settings['CHILLER_TIMEOUT']
TIC_TIMEOUT = _settings['TIC_TIMEOUT']
MAX_OUTPUT_LINES = _settings['MAX_OUTPUT_LINES']
MAX_GRAPH_POINTS = _settings['MAX_GRAPH_POINTS']
MAX_DUT_UNITS = _settings['MAX_DUT_UNITS']
TIMESTAMP_FORMAT = _settings['TIMESTAMP_FORMAT']
SAVE_DIRECTORY = _settings['SAVE_DIRECTORY']
ANALYSIS_MODEL = _settings['ANALYSIS_MODEL']
CONSTRAIN_LOW_RANGE = _settings['CONSTRAIN_LOW_RANGE']
DEVMODE = _settings['DEVMODE']

CN0359_ENABLED = _settings['CN0359_ENABLED']
CN0359_BAUDRATE = _settings['CN0359_BAUDRATE']
CN0359_POLL_INTERVAL = _settings['CN0359_POLL_INTERVAL']
CN0359_SENSORS = _settings['CN0359_SENSORS']
IONIN_ENABLED = _settings['IONIN_ENABLED']

# Export flag indicating if config.ini was found
CONFIG_FILE_FOUND = _config_file_found