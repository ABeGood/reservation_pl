"""
Centralized logging configuration for Polish Card Reservation System.
"""

import logging
import os
from datetime import datetime


def setup_logging(log_level=logging.INFO, log_file=None):
    """
    Configure logging for the entire application.
    
    Args:
        log_level: Logging level (default: INFO)
        log_file: Log file path (default: polish_card_bot.log)
    """
    if log_file is None:
        log_file = 'polish_card_bot.log'
    
    # Create logs directory if it doesn't exist
    log_dir = os.path.dirname(log_file) if os.path.dirname(log_file) else '.'
    os.makedirs(log_dir, exist_ok=True)
    
    # Clear any existing handlers to avoid conflicts
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Configure logging
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),  # Console output
            logging.FileHandler(log_file, encoding='utf-8')  # File output with UTF-8 encoding
        ]
    )
    
    # Set specific logger levels
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('selenium').setLevel(logging.WARNING)
    
    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured - Level: {logging.getLevelName(log_level)}, File: {log_file}")
    
    return logger


def get_logger(name):
    """Get a logger instance for the given module name."""
    return logging.getLogger(name)