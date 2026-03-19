"""
Version Management Module
Provides version information and generates content-based hash for change tracking
Supports both development (source files) and compiled (executable file) modes

Doc status: done, MK, 01/30/2026
"""
import os
import sys
import hashlib
import json
from pathlib import Path 
from datetime import datetime

# Manual version number - update this when releasing new versions
AUTHOR = "{AUTHOR STRING CHANGE ME}" # update this with your name or identifier
VERSION = "1.0.0b " + AUTHOR

# Debug flag - set to False to disable console output
DEBUG = False

# region VERSIONING 

def debug_print(msg):
    """Print debug message if DEBUG is enabled"""
    if DEBUG:
        print(f"[VERSION] {msg}")

def is_compiled():
    """Check if running as a compiled executable"""
    # Check multiple indicators
    checks = {
        '__compiled__': hasattr(sys, '__compiled__'),
        'frozen': getattr(sys, 'frozen', False),
        '_MEIPASS': hasattr(sys, '_MEIPASS'),
        'exe_in_argv': sys.argv and sys.argv[0] and sys.argv[0].lower().endswith('.exe')
    }
    
    result = any(checks.values())
    
    if DEBUG:
        debug_print(f"Compiled detection checks: {checks}")
        debug_print(f"is_compiled() = {result}")
    
    return result

def get_executable_path():
    """
    Get the path to the executable file
    Returns None if not running as compiled executable
    """
    compiled = is_compiled()
    debug_print(f"get_executable_path() called, is_compiled={compiled}")
    
    if not compiled:
        return None
    
    # Method 1: sys.argv[0]
    if sys.argv and sys.argv[0]:
        exe_path = os.path.abspath(sys.argv[0])
        debug_print(f"sys.argv[0] = {sys.argv[0]}")
        debug_print(f"Absolute path = {exe_path}")
        debug_print(f"File exists = {os.path.exists(exe_path)}")
        
        if os.path.exists(exe_path):
            debug_print(f"Using sys.argv[0]: {exe_path}")
            return exe_path
    
    # Method 2: sys.executable fallback
    if sys.executable and os.path.exists(sys.executable):
        debug_print(f"Fallback to sys.executable: {sys.executable}")
        return sys.executable
    
    debug_print("ERROR: Could not determine executable path!")
    return None

def get_project_root():
    """Get the root directory of the project"""
    if is_compiled():
        # When compiled, use the executable's directory
        exe_path = get_executable_path()
        if exe_path:
            return Path(exe_path).parent
        # Fallback to current directory
        return Path(os.getcwd())
    else:
        # When running from source, go up two levels from modes/utils/
        return Path(__file__).parent.parent.parent

def calculate_file_hash(filepath, chunk_size=65536):
    """
    Calculate SHA256 hash of a file's contents
    Uses larger chunk size for better performance on big files
    """
    hasher = hashlib.sha256()
    try:
        filepath = Path(filepath)
        if not filepath.exists():
            debug_print(f"File does not exist: {filepath}")
            return None
            
        with open(filepath, 'rb') as f:
            # Read file in chunks to handle large files efficiently
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()
    except (IOError, OSError) as e:
        debug_print(f"Error hashing file {filepath}: {e}")
        return None

def get_executable_hash():
    """
    Get hash of the executable file when running as compiled
    
    Returns:
        str: 8-character hash of the executable, or None if not compiled
    """
    if not is_compiled():
        return None
    
    exe_path = get_executable_path()
    
    debug_print(f"get_executable_hash() called")
    debug_print(f"Executable path: {exe_path}")
    
    if not exe_path:
        debug_print("ERROR: No executable path available")
        return "noexe"
    
    try:
        exe_path = Path(exe_path)
        if not exe_path.exists():
            debug_print(f"ERROR: Executable path does not exist: {exe_path}")
            return "nofile"
        
        file_size = exe_path.stat().st_size
        debug_print(f"Hashing executable ({file_size:,} bytes)...")
        
        full_hash = calculate_file_hash(exe_path)
        
        if full_hash:
            short_hash = full_hash[:8]
            debug_print(f"Hash generated: {short_hash}")
            return short_hash
        else:
            debug_print("ERROR: Hash calculation returned None")
            return "hasherr"
            
    except Exception as e:
        debug_print(f"ERROR calculating executable hash: {e}")
        import traceback
        traceback.print_exc()
        return "error"

def get_version_hash(include_config=False):
    """
    Generate a short hash based on source files or executable
    
    Args:
        include_config: If True, includes .ini and .txt config files in hash
        
    Returns:
        str: 8-character hash representing the current state
    """
    # If running as compiled executable, hash the EXE itself
    if is_compiled():
        exe_hash = get_executable_hash()
        if exe_hash and exe_hash not in ['noexe', 'nofile', 'hasherr', 'error']:
            return exe_hash
        
        # If EXE hashing failed, try using timestamp as fallback
        debug_print("EXE hashing failed, using timestamp fallback")
        timestamp = datetime.now().strftime("%y%m%d%H")
        return timestamp
    
    # Otherwise, calculate hash from source files
    project_root = get_project_root()
    
    # Directories to scan for source files
    source_dirs = [
        'modes/controllers',
        'modes/dialogs', 
        'modes/hardware',
        'modes/utils',
        'modes/analysis'
    ]
    
    # Files in root directory and modes directory to include
    root_files = [
        'main.py',
        'modes/acquisition_mode.py',
        'modes/analysis_mode.py',
        'modes/programming_mode.py',
        'modes/app_mode_selector.py',
        'modes/__init__.py'
    ]
    
    # Collect all file hashes
    file_hashes = []
    
    # Hash root files
    for filename in sorted(root_files):
        filepath = project_root / filename
        if filepath.exists():
            file_hash = calculate_file_hash(filepath)
            if file_hash:
                file_hashes.append(file_hash)
    
    # Hash files in source directories
    for dir_name in source_dirs:
        dir_path = project_root / dir_name
        if not dir_path.exists():
            continue
            
        # Get all .py files recursively
        py_files = sorted(dir_path.rglob('*.py'))
        
        for filepath in py_files:
            # Skip __pycache__ and test files
            if '__pycache__' in str(filepath) or filepath.name.startswith('test_'):
                continue
                
            file_hash = calculate_file_hash(filepath)
            if file_hash:
                file_hashes.append(file_hash)
    
    # Optionally include config files
    if include_config:
        config_patterns = ['*.ini', '*.txt']
        for pattern in config_patterns:
            config_files = sorted(project_root.glob(pattern))
            for filepath in config_files:
                if filepath.name.startswith('_'):  # Skip backup configs
                    continue
                file_hash = calculate_file_hash(filepath)
                if file_hash:
                    file_hashes.append(file_hash)
    
    # Combine all hashes and create final hash
    if not file_hashes:
        return "00000000"  # Default if no files found
    
    combined = ''.join(file_hashes)
    final_hash = hashlib.sha256(combined.encode()).hexdigest()
    
    # Return first 8 characters for compact display
    return final_hash[:8]

def get_full_version_string(include_config=False):
    """
    Get the complete version string including version number and hash
    
    Args:
        include_config: If True, includes config files in hash calculation
        
    Returns:
        str: Version string in format "v1.0.0-a1b2c3d4"
    """
    version_hash = get_version_hash(include_config=include_config)
    
    # If hash is 00000000, try using just the version with timestamp
    if version_hash == "00000000":
        debug_print("WARNING: Hash is 00000000, using timestamp")
        timestamp = datetime.now().strftime("%y%m%d%H")
        version_hash = timestamp
    
    return f"v{VERSION}-{version_hash}"

def get_version_info(include_config=False):
    """
    Get detailed version information as a dictionary
    
    Args:
        include_config: If True, includes config files in hash calculation
        
    Returns:
        dict: Dictionary with 'version', 'hash', 'full', and 'mode' keys
    """
    version_hash = get_version_hash(include_config=include_config)
    full_version = f"v{VERSION}-{version_hash}"
    
    return {
        'version': VERSION,
        'hash': version_hash,
        'full': full_version,
        'mode': 'compiled' if is_compiled() else 'development',
        'exe_path': str(get_executable_path()) if is_compiled() else None
    }

# Cache the version hash for performance (recalculate on module reload)
_cached_hash = None
_cached_full_version = None

def get_cached_version():
    """Get cached version string for performance"""
    global _cached_hash, _cached_full_version
    
    if _cached_full_version is None:
        _cached_full_version = get_full_version_string()
    
    return _cached_full_version

# Module-level constant for easy import
VERSION_STRING = get_cached_version()

# endregion

if __name__ == "__main__":
    # Test the version system
    print("=" * 70)
    print("Version System Test")
    print("=" * 70)
    print(f"Running Mode: {'COMPILED' if is_compiled() else 'DEVELOPMENT'}")
    
    if is_compiled():
        print(f"Executable: {get_executable_path()}")
        print(f"sys.executable: {sys.executable}")
        print(f"sys.argv[0]: {sys.argv[0] if sys.argv else 'None'}")
    
    print(f"Version Number: {VERSION}")
    print(f"Content Hash: {get_version_hash()}")
    print(f"Full Version: {get_full_version_string()}")
    
    if not is_compiled():
        print(f"With Config: {get_full_version_string(include_config=True)}")
    
    print()
    info = get_version_info()
    print("Version Info Dict:")
    for key, value in info.items():
        print(f"  {key}: {value}")
    print("=" * 70)



