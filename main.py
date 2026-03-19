"""
Main application entry point

This module initializes the application and runs the main event loop.

Doc status: done, MK, 01/30/2026
"""
import sys
from modes.utils import qt_opengl_shim
from modes.mode_manager import ModeManager

def main():
    """
    Application entry point.
    
    Initializes the mode manager and runs the main loop.
    """
    
    try:
        manager = ModeManager()
        exit_code = manager.run()
        sys.exit(exit_code)
    except Exception as e:
        sys.exit(1)

if __name__ == "__main__":
    main()
