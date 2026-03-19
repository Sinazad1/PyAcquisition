"""
PySide6 QtOpenGL Compatibility Shim
QtOpenGL module for PyQtGraph compatibility on some systems

Doc status: done, MK, 01/30/2026
"""
import sys

# Create a mock QtOpenGL module to satisfy PyQtGraph imports
# This prevents ModuleNotFoundError when PyQtGraph tries to import PySide6.QtOpenGL
class QtOpenGLModule:
    """Mock QtOpenGL module for compatibility with newer PySide6"""
    
    # Add common QtOpenGL classes as empty stubs
    class QGLWidget:
        """
        Shim class for QGLWidget compatibility.
        
        Provides a compatibility layer for PyQt6 which removed OpenGL support.
        Serves as a stub to prevent import errors.
        """
        pass
    
    class QGLFormat:
        """
        Shim class for QGLFormat compatibility.
        
        Provides a stub implementation for OpenGL format configuration.
        Prevents import errors when PyQtGraph attempts to use OpenGL.
        """
        pass
    
    class QGL:
        """
        Shim class for QGL enum compatibility.
        
        Provides stub OpenGL enum values for API compatibility.
        """
        pass

# Inject the mock module into sys.modules before any imports
if 'PySide6.QtOpenGL' not in sys.modules:
    sys.modules['PySide6.QtOpenGL'] = QtOpenGLModule()

# Also create the mock for direct QtOpenGL imports
sys.modules['QtOpenGL'] = QtOpenGLModule()
