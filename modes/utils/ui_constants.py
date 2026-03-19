"""
UI Constants
Centralized constants for consistent styling and sizing
Stub for now

Doc status: done, MK, 01/30/2026
"""


# region BUTTON SIZES

BUTTON_MIN_WIDTH = 120
BUTTON_MIN_HEIGHT = 70
LARGE_BUTTON_HEIGHT = 80
SMALL_BUTTON_WIDTH = 80
#regionend

# region COLORS

# Status Colors
COLOR_SUCCESS = "#4CAF50"
COLOR_SUCCESS_DARK = "#27AE60"
COLOR_ERROR = "#f44336"
COLOR_ERROR_DARK = "#E74C3C"
COLOR_WARNING = "#FFA500"
COLOR_INFO = "#3498DB"
COLOR_INFO_DARK = "#2980B9"
COLOR_RUNNING = "#2ECC71"
COLOR_STOPPED = "#E74C3C"
COLOR_PAUSED = "#F39C12"

# UI Colors
COLOR_BACKGROUND = "#2A2A2A"
COLOR_BACKGROUND_HOVER = "#3A3A3A"
COLOR_BORDER = "#333"
COLOR_TEXT_PRIMARY = "#FFFFFF"
COLOR_TEXT_SECONDARY = "#666"
COLOR_TEXT_MUTED = "#888"
COLOR_DISABLED = "#cccccc"
COLOR_DISABLED_TEXT = "#666"

# Button Colors
COLOR_BUTTON_NORMAL = "#666"
COLOR_BUTTON_HOVER = "#555"

# Device Colors (for logging and UI elements)
COLOR_CHILLER = "#00CED1"
COLOR_PUMP = "#00BFFF"
COLOR_TIC = "#9370DB"
COLOR_PROTOCOL = "#00FF00"
COLOR_SYSTEM = "#00BFFF"

# Log Colors
COLOR_LOG_BACKGROUND = "#1E1E1E"
COLOR_LOG_TEXT = "#00FF00"

# Data Display Colors
COLOR_DISPLAY_BACKGROUND = "#2C3E50"
COLOR_DISPLAY_VALUE = "#3498DB"
#regionend


# region FONTS

FONT_FAMILY_MONO = "'Consolas', 'Monaco', 'Courier New', monospace"
FONT_FAMILY_UI = "'Arial', sans-serif"

FONT_SIZE_SMALL = "9pt"
FONT_SIZE_NORMAL = "10pt"
FONT_SIZE_MEDIUM = "11pt"
FONT_SIZE_LARGE = "12pt"
FONT_SIZE_XLARGE = "14pt"
FONT_SIZE_XXLARGE = "16pt"
FONT_SIZE_HUGE = "18pt"
FONT_SIZE_DISPLAY = "36pt"
#regionend

# region SPACING
PADDING_SMALL = "5px"
PADDING_MEDIUM = "8px"
PADDING_LARGE = "10px"
PADDING_XLARGE = "15px"

MARGIN_SMALL = "5px"
MARGIN_MEDIUM = "10px"

BORDER_RADIUS_SMALL = "3px"
BORDER_RADIUS_MEDIUM = "5px"
#regionend



# region STYLESHEETS
def get_button_style(color, hover_color=None):
    """Get standard button stylesheet"""
    if hover_color is None:
        # Darken the color for hover
        hover_color = color.replace("4CAF50", "45a049").replace("3498DB", "2980B9")
    
    return f"""
        QPushButton {{
            background-color: {color};
            color: white;
            padding: {PADDING_LARGE};
            font-size: {FONT_SIZE_MEDIUM};
            font-weight: bold;
            border-radius: {BORDER_RADIUS_SMALL};
        }}
        QPushButton:hover {{
            background-color: {hover_color};
        }}
        QPushButton:disabled {{
            background-color: #cccccc;
            color: #666;
        }}
    """

def get_log_style():
    """Get standard log widget stylesheet"""
    return f"""
        QTextEdit {{
            background-color: {COLOR_LOG_BACKGROUND};
            color: {COLOR_LOG_TEXT};
            font-family: {FONT_FAMILY_MONO};
            font-size: {FONT_SIZE_SMALL};
        }}
    """

def get_status_label_style(status_color):
    """Get standard status label stylesheet"""
    return f"""
        QLabel {{
            background-color: {status_color};
            color: white;
            padding: {PADDING_MEDIUM};
            font-weight: bold;
            font-size: {FONT_SIZE_LARGE};
            border-radius: {BORDER_RADIUS_SMALL};
        }}
    """

def get_display_label_style(text_color=COLOR_DISPLAY_VALUE):
    """Get standard display label stylesheet"""
    return f"""
        QLabel {{
            background-color: {COLOR_DISPLAY_BACKGROUND};
            color: {text_color};
            font-size: {FONT_SIZE_DISPLAY};
            font-weight: bold;
            padding: 20px;
            border-radius: {BORDER_RADIUS_MEDIUM};
            font-family: {FONT_FAMILY_UI};
        }}
    """
#regionend