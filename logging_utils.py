"""
Logging Utilities Module - Custom logging and output handling.

This module contains:
- TeeLogger: Writes output to both console and log file simultaneously
"""

import sys


class TeeLogger:
    """
    Writes output to both console and a log file.
    
    Usage:
        logger = TeeLogger("output.log")
        sys.stdout = logger
        print("This goes to console AND file")
        sys.stdout = logger.terminal  # Restore original stdout
        logger.close()
    """
    
    def __init__(self, log_file):
        """
        Initialize the TeeLogger.
        
        Args:
            log_file: Path to the log file to write to
        """
        self.terminal = sys.stdout
        self.log_file = open(log_file, 'w', encoding='utf-8')
    
    def write(self, message):
        """Write message to both terminal and log file."""
        self.terminal.write(message)
        self.log_file.write(message)
        self.log_file.flush()  # Ensure immediate write
    
    def flush(self):
        """Flush both terminal and log file."""
        self.terminal.flush()
        self.log_file.flush()
    
    def close(self):
        """Close the log file."""
        self.log_file.close()

