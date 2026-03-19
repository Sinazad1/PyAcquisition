"""
Data Parser Module (within Acquisition Mode)
Handles parsing of serial data for both DUT and reference devices
Extracts complete measurement data including frequency, magnitude, and phase

Doc status: done, MK, 01/30/2026
"""
import re
from datetime import datetime

# Import configuration settings
try:
    from modes.utils.config import TIMESTAMP_FORMAT
except ImportError:
    TIMESTAMP_FORMAT = "%H:%M:%S.%f"

class DataParser:
    """Parses serial data and extracts measurement for acquisition mode"""
    
    @staticmethod
    def timestamp_to_seconds(timestamp_str):
        """Convert timestamp string to Unix timestamp (seconds since epoch)"""
        try:
            time_str = timestamp_str.strip()
            
            # Check if timestamp includes date (ISO format: "YYYY-MM-DD HH:MM:SS.fff")
            if ' ' in time_str:
                # Full ISO format with date
                dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S.%f")
                return dt.timestamp()
            else:
                # Time-only format: "HH:MM:SS.fff"
                today = datetime.now().date()
                
                # Parse hours, minutes, seconds from timestamp
                time_parts = time_str.split(':')
                if len(time_parts) >= 3:
                    hours = int(time_parts[0])
                    minutes = int(time_parts[1])
                    # Handle seconds with decimal
                    seconds_parts = time_parts[2].split('.')
                    seconds = int(seconds_parts[0])
                    milliseconds = int(seconds_parts[1]) if len(seconds_parts) > 1 else 0
                    
                    # Create a datetime object for today at this time
                    dt = datetime(today.year, today.month, today.day, hours, minutes, seconds, milliseconds * 1000)
                    
                    # Convert to Unix timestamp
                    return dt.timestamp()
                else:
                    # Fallback to current time
                    return datetime.now().timestamp()
        except Exception as e:
            print(f"Error converting timestamp: {e}")
            return datetime.now().timestamp()
    
    @staticmethod
    def parse_dut_units(data):
        """
        Parse DUT unit measurements from serial data with full details
        
        Example data:
        "Selected Unit: 2 | Reset Pin: 22 | Interrupt Pin: 21 Unit 2: Performing settling measurements... 
        Freq: 10000.00 Hz DataPoints: 1 RzMag: 1017.36 Ohm, RzPhase: -0.01 deg;
        Freq:0.0 1 RzMag: 1000.88165 Ohm, RzPhase: 0.0"
        
        Returns:
            List of dicts with complete measurement data:
            [{
                'unit_id': 2,
                'conductivity': {
                    'frequency': 10000.00,
                    'rzmag': 1017.36,
                    'rzphase': -0.01
                },
                'temperature': {
                    'frequency': 0.0,
                    'rzmag': 1000.88165,
                    'rzphase': 0.0
                }
            }, ...]
        """
        results = []
        
        # Split data by unit blocks (each starts with "Selected Unit:")
        unit_blocks = re.split(r'Selected Unit:', data)
        
        for block in unit_blocks[1:]:  # Skip first empty split
            try:
                # Extract unit ID
                unit_match = re.search(r'^\s*(\d+)', block)
                if not unit_match:
                    continue
                unit_id = int(unit_match.group(1))
                
                # Only process valid units (1-6)
                if not (1 <= unit_id <= 6):
                    continue
                
                # Find all frequency/RzMag/RzPhase sets
                # Pattern: Freq: XX.XX Hz DataPoints: X RzMag: YY.YY Ohm, RzPhase: ZZ.ZZ deg
                # or: Freq:XX.X X RzMag: YY.YY Ohm, RzPhase: ZZ.ZZ
                # RzMag can be inf (infinity)
                
                measurements = []
                
                # First measurement (with "Hz" and "DataPoints")
                # Allow "inf" as a value for RzMag
                first_pattern = r'Freq:\s*([\d.]+)\s*Hz\s*DataPoints:\s*\d+\s*RzMag:\s*([\d.]+|inf)\s*Ohm,\s*RzPhase:\s*([-\d.]+)'
                first_match = re.search(first_pattern, block)
                if first_match:
                    rzmag_str = first_match.group(2)
                    rzmag = float('inf') if rzmag_str == 'inf' else float(rzmag_str)
                    measurements.append({
                        'frequency': float(first_match.group(1)),
                        'rzmag': rzmag,
                        'rzphase': float(first_match.group(3))
                    })
                
                # Second measurement (after semicolon, simpler format)
                # Allow extra spaces and "inf" values
                second_pattern = r';.*?Freq:\s*([\d.]+)\s+\d+\s+RzMag:\s*([-\d.]+|inf)\s*Ohm,\s*RzPhase:\s*([-\d.]+)'
                second_match = re.search(second_pattern, block)
                if second_match:
                    rzmag_str = second_match.group(2)
                    # Validate RzMag - reject obviously invalid values (e.g., negative for temperature)
                    try:
                        rzmag = float('inf') if rzmag_str == 'inf' else float(rzmag_str)
                        # Only add if rzmag is reasonable (not large negative number which indicates error)
                        if rzmag > -1000:  # Allow small negatives but reject large error values
                            measurements.append({
                                'frequency': float(second_match.group(1)),
                                'rzmag': rzmag,
                                'rzphase': float(second_match.group(3))
                            })
                    except ValueError:
                        pass  # Skip invalid measurement
                
                # Accept measurements - need at least 1 valid measurement
                if len(measurements) >= 1:
                    result = {
                        'unit_id': unit_id,
                        'conductivity': measurements[0]  # First measurement (always present)
                    }
                    # Add temperature measurement if available
                    if len(measurements) >= 2:
                        result['temperature'] = measurements[1]
                    else:
                        # No valid temperature measurement
                        result['temperature'] = None
                    
                    results.append(result)
                else:
                    # Debug: print what we found
                    print(f"[PARSER] Unit {unit_id}: No valid measurements found")
                    if len(measurements) > 0:
                        print(f"[PARSER]   Found {len(measurements)} measurement(s): {measurements}")
                    
            except Exception as e:
                print(f"Error parsing DUT unit block: {e}")
                continue
        
        return results
    
    @staticmethod
    def parse_reference_devices(data):
        """
        Parse reference device measurements from serial data
        
        Returns:
            List of dicts with complete measurement data:
            [{
                'ref_id': 1,
                'conductivity': {
                    'frequency': 10000.00,
                    'rzmag': 1017.36,
                    'rzphase': -0.01
                },
                'temperature': {
                    'frequency': 0.0,
                    'rzmag': 1000.88165,
                    'rzphase': 0.0
                }
            }, ...]
        """
        results = []
        
        # Split data by reference unit blocks (each starts with "Reference Unit:" or "Ref:")
        ref_blocks = re.split(r'(?:Reference Unit|Ref):', data)
        
        for block in ref_blocks[1:]:  # Skip first empty split
            try:
                # Extract reference ID
                ref_match = re.search(r'^\s*(\d+)', block)
                if not ref_match:
                    continue
                ref_id = int(ref_match.group(1))
                
                # Only process valid reference devices (1-2)
                if not (1 <= ref_id <= 2):
                    continue
                
                measurements = []
                
                # First measurement (with "Hz" and "DataPoints")
                first_pattern = r'Freq:\s*([\d.]+)\s*Hz\s*DataPoints:\s*\d+\s*RzMag:\s*([\d.]+)\s*Ohm,\s*RzPhase:\s*([-\d.]+)'
                first_match = re.search(first_pattern, block)
                if first_match:
                    measurements.append({
                        'frequency': float(first_match.group(1)),
                        'rzmag': float(first_match.group(2)),
                        'rzphase': float(first_match.group(3))
                    })
                
                # Second measurement (after semicolon)
                second_pattern = r';.*?Freq:\s*([\d.]+)\s+\d+\s+RzMag:\s*([\d.]+)\s*Ohm,\s*RzPhase:\s*([-\d.]+)'
                second_match = re.search(second_pattern, block)
                if second_match:
                    measurements.append({
                        'frequency': float(second_match.group(1)),
                        'rzmag': float(second_match.group(2)),
                        'rzphase': float(second_match.group(3))
                    })
                
                # We need both measurements
                if len(measurements) >= 2:
                    results.append({
                        'ref_id': ref_id,
                        'conductivity': measurements[0],  # First measurement
                        'temperature': measurements[1]     # Second measurement
                    })
                    
            except Exception as e:
                print(f"Error parsing reference device block: {e}")
                continue
        
        return results
    
    @staticmethod
    def parse_all_measurements(data, timestamp_str):
        """
        Parse all measurements from serial data
        
        Returns:
            dict with 'dut_units' and 'reference_devices' keys containing parsed data
        """
        time_seconds = DataParser.timestamp_to_seconds(timestamp_str)
        
        return {
            'timestamp': time_seconds,
            'timestamp_str': timestamp_str,
            'dut_units': DataParser.parse_dut_units(data),
            'reference_devices': DataParser.parse_reference_devices(data)
        }
