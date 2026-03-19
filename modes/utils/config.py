"""
Config
Passthrough for configuration settings to read of program

Doc status: done, MK, 01/30/2026
Patch in for pump rate units, MK 02/03/2026
"""

# Try to load from external config.ini
try:
    from modes.utils.settings import *
    print("[CONFIG] Loaded settings from config.ini via settings.py")
    
except ImportError as e:
    # Running as script - use values below
    print(f"[CONFIG] Using config.py defaults (settings.py not found: {e})")
    
    # Serial Port Configuration
    DUT_COM_PORT = None
    IBP_REF1_PORT = None
    IBP_REF2_PORT = None
    SYRINGE_PUMP_PORT = None
    CHILLER_PORT = None
    TIC_A_SERIAL_NUMBER = None
    TIC_B_SERIAL_NUMBER = None
    
    # DUT Serial Settings
    BAUDRATE = 115200
    TIMEOUT = 10.0
    READ_TIMEOUT_MAX = 30.0
    READ_TIMEOUT_IDLE = 3.0
    QUERY_INTERVAL = 10
    
    # IBP Settings
    ENABLE_IBP_REFERENCES = True
    IBP_BAUDRATE = 115200
    IBP_TIMEOUT = 2.0
    
    # Pump Settings
    PUMP_BAUDRATE = 19200
    PUMP_TIMEOUT = 2.0
    PUMP_RATE_UNITS = 'MM'  # MM=mL/min, MH=mL/hr, UM=µL/min, UH=µL/hr
    
    # Chiller Settings
    CHILLER_BAUDRATE = 4800
    CHILLER_TIMEOUT = 2.0
    
    # Tic Settings
    TIC_TIMEOUT = 5
    
    # Data Display Settings
    MAX_OUTPUT_LINES = 1000
    MAX_GRAPH_POINTS = 1000
    MAX_LOG_LINES = 5000
    MAX_DUT_UNITS = 8
    
    # Data Management
    TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S.%f"
    SAVE_DIRECTORY = "data"
    
    # CN0359 Direct Sensor Settings
    CN0359_ENABLED = False
    CN0359_BAUDRATE = 115200
    CN0359_POLL_INTERVAL = 10
    CN0359_SENSORS = []
    IONIN_ENABLED = False
