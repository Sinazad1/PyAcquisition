"""
Mode Manager
Mode management classes for handling application mode transitions.

Doc status: done, MK, 01/30/2026
"""

import sys
import logging
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

from modes.acquisition_mode import AcquisitionWindow
from modes.analysis_mode import AnalysisWindow
from modes.programming_mode import ProgrammingWindow
from modes.dialogs.app_mode_selector import AppModeSelector

# region AppMode
class AppMode:
    """Application mode constants"""
    ACQUISITION = "acquisition"
    ANALYSIS = "analysis"
    PROGRAMMING = "programming"
    PRODUCTION = "production"
# end region

# region MODE MANAGER

class ModeManager:
    """
    Manages the application window transitions and close out
    
    This class handles:
    - Application initialization
    - Mode selection and window launching
    - Production mode workflow management
    - Cleanup and shutdown
    """
    
    # region INITIALIZATION
    
    def __init__(self):
        """
        Initialize the mode manager.
        
        Sets up the QApplication, mode selection dialog, and manages transitions
        between Acquisition, Analysis, and Production modes.
        """
        self.app = QApplication(sys.argv)
        self.current_window: Optional[QWidget] = None
        self.production_manager = ProductionModeManager()
        self.logger = logging.getLogger(f"{__name__}.ModeManager")
        
        # Connect cleanup handler
        self.app.lastWindowClosed.connect(self._on_last_window_closed)
        
        self.logger.info("Mode manager initialized")
    
    # endregion
    
    # region APPLICATION LIFECYCLE
    
    def _on_last_window_closed(self) -> None:
        """
        Handle last window closing event.
        
        Stops any active devices and quits the application event loop.
        """
        self.logger.info("Last window closed")
        self._stop_devices()
        self.app.quit()
    
    def _stop_devices(self) -> None:
        """Stop all devices if the current window supports device management"""
        if self.current_window and hasattr(self.current_window, 'stop_all_devices'):
            self.logger.info("Stopping all devices")
            try:
                self.current_window.stop_all_devices()
            except Exception as e:
                self.logger.error(f"Error stopping devices: {e}", exc_info=True)
    
    def run(self) -> int:
        """
        Main application loop.
        
        Continuously shows mode selector and launches appropriate windows
        until the user exits or an error occurs.
        
        Returns:
            Exit code (0 for success)
        """
        self.logger.info("Starting application main loop")
        
        while True:
            # Determine which mode to launch next
            selected_mode = self._get_next_mode()
            if selected_mode is None:
                self.logger.info("No mode selected, exiting application")
                break
            
            # Launch the appropriate window for the selected mode
            if not self._launch_window(selected_mode):
                self.logger.warning("Failed to launch window, exiting application")
                break
            
            # Run the event loop for this window
            self.app.exec()
            
            # Handle post-window closure tasks
            self._handle_window_closed()
        
        self.logger.info("Application loop ended")
        return 0
    
    # endregion
    
    # region MODE SELECTION
    
    def _get_next_mode(self) -> Optional[str]:
        """
        Determine which mode to launch next.
        
        In production mode, this advances through the workflow phases.
        Otherwise, shows the mode selector dialog.
        
        Returns:
            The mode string to launch, or None to exit
        """
        # If in production mode, get the next phase
        if self.production_manager.is_active():
            mode = self.production_manager.get_current_mode()
            self.logger.info(f"Production mode: launching {mode}")
            return mode
        
        # Show mode selector dialog
        self.logger.info("Showing mode selector dialog")
        mode_selector = AppModeSelector()
        
        if mode_selector.exec() != AppModeSelector.Accepted:
            self.logger.info("Mode selector cancelled")
            return None
        
        selected_mode = mode_selector.get_selected_mode()
        self.logger.info(f"User selected mode: {selected_mode}")
        
        # Check if production mode was selected
        if selected_mode == AppMode.PRODUCTION:
            self.production_manager.start()
            return self.production_manager.get_current_mode()
        
        return selected_mode
    
    # endregion
    
    # region WINDOW MANAGEMENT
    
    def _create_window(self, mode: str) -> Optional[QWidget]:
        """
        Factory method for creating windows based on mode.
        
        Args:
            mode: The mode string (acquisition, analysis, or programming)
            
        Returns:
            The created window, or None if mode is invalid
        """
        production_mode = self.production_manager.is_active()
        
        window_factory = {
            AppMode.ACQUISITION: lambda: AcquisitionWindow(production_mode=production_mode),
            AppMode.ANALYSIS: lambda: AnalysisWindow(),
            AppMode.PROGRAMMING: lambda: ProgrammingWindow()
        }
        
        if mode not in window_factory:
            self.logger.error(f"Invalid mode requested: {mode}")
            return None
        
        try:
            window = window_factory[mode]()
            window.setAttribute(Qt.WA_DeleteOnClose)
            return window
        except Exception as e:
            self.logger.error(f"Error creating {mode} window: {e}", exc_info=True)
            return None
    
    def _launch_window(self, mode: str) -> bool:
        """
        Launch a window for the specified mode.
        
        Args:
            mode: The mode string to launch
            
        Returns:
            True if window was successfully launched, False otherwise
        """
        self.logger.info(f"Launching {mode} window")
        
        try:
            self.current_window = self._create_window(mode)
            
            if self.current_window is None:
                self.logger.error(f"Failed to create window for mode: {mode}")
                self._handle_invalid_mode()
                return False
            
            self.current_window.show()
            self.logger.info(f"{mode.capitalize()} window launched successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error launching {mode} window: {e}", exc_info=True)
            self._handle_launch_error(mode, e)
            return False
    
    # endregion
    
    # region POST-WINDOW HANDLERS
    
    def _handle_window_closed(self) -> None:
        """
        Handle post-window closure tasks.
        
        Checks for setup cancellation and manages production mode progression.
        """
        # Check if window setup was cancelled
        if self._was_setup_cancelled():
            self.logger.info("Window setup was cancelled")
            if self.production_manager.is_active():
                self.logger.info("Resetting production mode due to cancelled setup")
                self.production_manager.reset()
        
        # Advance production mode if active
        elif self.production_manager.is_active():
            self.production_manager.advance()
        
        # Clean up window reference
        self.current_window = None
    
    def _was_setup_cancelled(self) -> bool:
        """
        Check if the current window's setup was cancelled.
        
        Returns:
            True if setup was cancelled, False otherwise
        """
        return (
            self.current_window is not None and
            hasattr(self.current_window, 'setup_cancelled') and
            self.current_window.setup_cancelled
        )
    
    def _handle_invalid_mode(self) -> None:
        """Handle invalid mode selection"""
        self.logger.error("Invalid mode selected")
        if self.production_manager.is_active():
            self.production_manager.reset()
    
    def _handle_launch_error(self, mode: str, error: Exception) -> None:
        """
        Handle errors during window launch.
        
        Args:
            mode: The mode that failed to launch
            error: The exception that was raised
        """
        self.logger.error(f"Failed to launch {mode} mode: {error}")
        if self.production_manager.is_active():
            self.production_manager.reset()
    
    # endregion
    
# endregion


# region PRODUCTION MODE MANAGER
class ProductionModeManager:
    """
    Manages production mode workflow transitions.
    
    Production mode runs a sequence of phases: Acquisition -> Analysis -> Programming
    """
    
    PHASES = [AppMode.ACQUISITION, AppMode.ANALYSIS, AppMode.PROGRAMMING]
    
    # region INITIALIZATION
    
    def __init__(self):
        """
        Initialize the production mode manager.
        
        Sets up the production workflow manager that coordinates the sequence
        of Acquisition -> Analysis -> Programming phases for production testing.
        """
        self.active: bool = False
        self.current_phase_index: int = 0
        self.logger = logging.getLogger(f"{__name__}.ProductionModeManager")
    
    # endregion
    
    # region WORKFLOW MANAGEMENT
    
    def start(self) -> None:
        """Start production mode workflow from the beginning"""
        self.active = True
        self.current_phase_index = 0
        self.logger.info("Production mode started")
    
    def get_current_mode(self) -> Optional[str]:
        """
        Get the current mode/phase in the production workflow.
        
        Returns:
            The current mode string, or None if workflow is complete or inactive
        """
        if not self.active or self.current_phase_index >= len(self.PHASES):
            return None
        return self.PHASES[self.current_phase_index]
    
    def advance(self) -> bool:
        """
        Move to the next phase in the production workflow.
        
        Returns:
            True if more phases remain, False if workflow is complete
        """
        self.current_phase_index += 1
        
        if self.current_phase_index >= len(self.PHASES):
            self.logger.info("Production mode workflow complete")
            self.reset()
            return False
        
        current_mode = self.get_current_mode()
        self.logger.info(f"Production mode advanced to: {current_mode}")
        return True
    
    def reset(self) -> None:
        """Reset production mode to inactive state"""
        self.active = False
        self.current_phase_index = 0
        self.logger.info("Production mode reset")
    
    def is_active(self) -> bool:
        """Check if production mode is currently active"""
        return self.active
    
    # endregion
    
# endregion
