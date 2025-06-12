"""
Datetime utilities for consistent timezone handling across the project.
"""

import datetime
from typing import Optional, Union

def get_utc_now() -> datetime.datetime:
    """
    Get current UTC time with timezone information.
    
    Returns:
        datetime.datetime: Current UTC time with timezone information
    """
    return datetime.datetime.now(datetime.timezone.utc)

def to_utc(dt: datetime.datetime) -> datetime.datetime:
    """
    Convert a datetime object to UTC with timezone information.
    If the datetime is naive (no timezone), assume it's in UTC.
    
    Args:
        dt (datetime.datetime): Datetime object to convert
        
    Returns:
        datetime.datetime: UTC datetime with timezone information
    """
    if dt.tzinfo is None:
        # If no timezone info, assume it's UTC and add timezone info
        return dt.replace(tzinfo=datetime.timezone.utc)
    else:
        # If it has timezone info, convert to UTC
        return dt.astimezone(datetime.timezone.utc)

def format_iso(dt: datetime.datetime) -> str:
    """
    Format a datetime object as ISO 8601 string with UTC timezone.
    
    Args:
        dt (datetime.datetime): Datetime object to format
        
    Returns:
        str: ISO 8601 formatted string with UTC timezone
    """
    utc_dt = to_utc(dt)
    return utc_dt.isoformat()

def parse_iso(iso_str: str) -> datetime.datetime:
    """
    Parse an ISO 8601 string into a datetime object with timezone information.
    
    Args:
        iso_str (str): ISO 8601 formatted string
        
    Returns:
        datetime.datetime: Datetime object with timezone information
    """
    dt = datetime.datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        # If parsed datetime has no timezone, assume UTC
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt