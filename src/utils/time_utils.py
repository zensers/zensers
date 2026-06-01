# -*- coding: utf-8 -*-
"""
Time Utility Functions

Provides unified time format parsing, supporting multiple common formats.
"""

import re
from datetime import datetime
from typing import Optional

__all__ = ["parse_time"]


def parse_time(time_str: str) -> Optional[datetime]:
    """
    Unified time format parsing
    
    Supported formats:
    - Quarter: "2024-Q3"
    - ISO date: "2024-01-01"
    - ISO timestamp: "2024-01-01T10:00:00"
    - Year: "2024"
    - Year-month: "2024-01"
    
    Args:
        time_str: Time string
        
    Returns:
        datetime object, returns None on parse failure
        
    Examples:
        >>> parse_time("2024-Q3")
        datetime(2024, 7, 1)
        >>> parse_time("2024-01-15")
        datetime(2024, 1, 15)
        >>> parse_time("2024")
        datetime(2024, 1, 1)
    """
    if not time_str:
        return None
    
    # Handle quarter format "2024-Q3"
    if "-Q" in time_str:
        match = re.match(r"(\d{4})-Q(\d)", time_str)
        if match:
            year = int(match.group(1))
            quarter = int(match.group(2))
            # Boundary check: quarter must be between 1-4
            if not 1 <= quarter <= 4:
                return None
            month = (quarter - 1) * 3 + 1
            return datetime(year, month, 1)
    
    # Try multiple ISO formats
    for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y-%m", "%Y"]:
        try:
            return datetime.strptime(time_str, fmt)
        except ValueError:
            continue
    
    return None