"""
Mode Selection Dialog
Allows the user to choose between Acquisition Mode, Analysis Mode, and Production Mode

Doc status: done, MK, 01/30/2026
"""
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QPushButton, QLabel, 
                               QHBoxLayout)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from modes.utils.version import VERSION_STRING

# Import DEVMODE setting from config
try:
    from modes.utils.settings import DEVMODE
except ImportError:
    # Fallback if settings.py not available
    try:
        from modes.utils.config import DEVMODE
    except (ImportError, AttributeError):
        # Default to False if not found in either location
        DEVMODE = False

class AppModeSelector(QDialog):
    """Dialog to select application mode: Acquisition, Analysis, or Production"""
    
    # region INITIALIZATION
    
    def __init__(self, parent=None):
        """
        Initialize the application mode selector dialog.
        
        Creates a modal dialog for choosing between Acquisition, Analysis,
        or Production modes on application startup.
        
        Args:
            parent (QWidget, optional): Parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.selected_mode = None
        self.init_ui()
    
    # endregion
    
    # region UI INITIALIZATION
        
    def init_ui(self):
        """Initialize the UI"""
        self.setWindowTitle("alyPyAcquisition - Select Mode")
        self.setModal(True)
        self.setMinimumWidth(550)
        self.setMinimumHeight(400)
        
        # Main layout
        layout = QVBoxLayout()
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # Title label
        title = QLabel("alyPyAcquisition")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Description label
        description = QLabel(
            "Select your operating mode below"
        )
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignCenter)
        layout.addWidget(description)
        
        # Add some spacing
        layout.addStretch()
        
        # Production mode button (large, on top)
        production_font = QFont()
        production_font.setPointSize(14)
        production_font.setBold(True)
        self.production_btn = QPushButton("Production")
        self.production_btn.setMinimumHeight(80)
        self.production_btn.setFont(production_font)
        self.production_btn.clicked.connect(self.select_production_mode)
        self.production_btn.setToolTip("Run Acquisition followed by Analysis followed by Programming")
        self.production_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                border-radius: 8px;
                padding: 15px;
            }
            QPushButton:hover {
                background-color: #FB8C00;
            }
            QPushButton:pressed {
                background-color: #F57C00;
            }
        """)
        layout.addWidget(self.production_btn)
        
        # Add description for production mode
        production_desc = QLabel("Runs Acquisition -> Analysis -> Programming Sequentially")
        production_desc.setAlignment(Qt.AlignCenter)
        production_desc.setStyleSheet("""
            QLabel {
                color: #666666;
                font-size: 9pt;
                font-style: italic;
                padding: 5px;
            }
        """)
        layout.addWidget(production_desc)
        
        # Add spacing between production and individual modes
        layout.addSpacing(15)
        
        # Individual mode buttons container - only show if DEVMODE is True
        if DEVMODE:
            button_layout = QHBoxLayout()
            button_layout.setSpacing(20)
            
            # Button font for individual modes
            button_font = QFont()
            button_font.setPointSize(11)
            button_font.setBold(True)
            
            # Acquisition mode button
            self.acquisition_btn = QPushButton("Acquisition")
            self.acquisition_btn.setMinimumHeight(60)
            self.acquisition_btn.setMinimumWidth(180)
            self.acquisition_btn.setFont(button_font)
            self.acquisition_btn.clicked.connect(self.select_acquisition_mode)
            self.acquisition_btn.setStyleSheet("""
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    border-radius: 5px;
                    padding: 10px;
                }
                QPushButton:hover {
                    background-color: #45a049;
                }
                QPushButton:pressed {
                    background-color: #3d8b40;
                }
            """)
            button_layout.addWidget(self.acquisition_btn)
            
            # Analysis mode button
            self.analysis_btn = QPushButton("Analysis")
            self.analysis_btn.setMinimumHeight(60)
            self.analysis_btn.setMinimumWidth(180)
            self.analysis_btn.setFont(button_font)
            self.analysis_btn.clicked.connect(self.select_analysis_mode)
            self.analysis_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2196F3;
                    color: white;
                    border-radius: 5px;
                    padding: 10px;
                }
                QPushButton:hover {
                    background-color: #0b7dda;
                }
                QPushButton:pressed {
                    background-color: #0970c9;
                }
            """)
            button_layout.addWidget(self.analysis_btn)
            
            layout.addLayout(button_layout)
        
        # Programming mode button (always shown)
        programming_font = QFont()
        programming_font.setPointSize(11)
        programming_font.setBold(True)
        self.programming_btn = QPushButton("Programming")
        self.programming_btn.setMinimumHeight(60)
        self.programming_btn.setFont(programming_font)
        self.programming_btn.clicked.connect(self.select_programming_mode)
        self.programming_btn.setToolTip("Program calibration coefficients to DUT sensors")
        self.programming_btn.setStyleSheet("""
            QPushButton {
                background-color: #9C27B0;
                color: white;
                border-radius: 5px;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #8E24AA;
            }
            QPushButton:pressed {
                background-color: #7B1FA2;
            }
        """)
        layout.addWidget(self.programming_btn)
        
        # Add some spacing
        layout.addStretch()
        
        # Exit button
        exit_btn = QPushButton("Exit")
        exit_btn.setMinimumHeight(40)
        exit_btn.clicked.connect(self.reject)
        exit_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border-radius: 5px;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
            QPushButton:pressed {
                background-color: #c41606;
            }
        """)
        layout.addWidget(exit_btn)
        
        # Add version label at bottom
        version_label = QLabel(VERSION_STRING)
        version_label.setAlignment(Qt.AlignCenter)
        version_label.setStyleSheet("""
            QLabel {
                color: #888888;
                font-size: 9pt;
                padding: 5px;
            }
        """)
        layout.addWidget(version_label)
        
        self.setLayout(layout)
    
    # endregion
    
    # region MODE SELECTION HANDLERS
        
    def select_acquisition_mode(self):
        """User selected acquisition mode"""
        self.selected_mode = "acquisition"
        self.accept()
        
    def select_analysis_mode(self):
        """User selected analysis mode"""
        self.selected_mode = "analysis"
        self.accept()
        
    def select_production_mode(self):
        """User selected production mode (acquisition followed by analysis followed by programming)"""
        self.selected_mode = "production"
        self.accept()
        
    def get_selected_mode(self):
        """Return the selected mode"""
        return self.selected_mode    
    
    def select_programming_mode(self):
        """User selected programming mode"""
        self.selected_mode = "programming"
        self.accept()
    
    # endregion
