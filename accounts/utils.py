"""
Username utilities: normalization, validation helpers.
"""
import re
import unicodedata
from typing import Optional
from django.conf import settings


def normalize_username(raw: str) -> str:
    """
    Normalize a username to canonical form.
    
    Rules:
    - Strip leading/trailing whitespace
    - Apply Unicode NFKC normalization
    - Convert to lowercase (for case-insensitive uniqueness)
    
    This function is the single source of truth for username normalization
    and MUST be used in:
    - User registration
    - Username changes
    - Availability checks
    - Database lookups
    - Reserved username checks
    
    Args:
        raw: Raw username string
        
    Returns:
        Normalized username (lowercase, NFKC normalized)
        
    Example:
        >>> normalize_username("  JohnDoe  ")
        'johndoe'
        >>> normalize_username("Admin")
        'admin'
    """
    if raw is None:
        return raw
    s = raw.strip()
    s = unicodedata.normalize("NFKC", s)
    return s.lower()


def is_username_format_valid(username: str) -> tuple[bool, Optional[str]]:
    """
    Check if username matches the required format (regex and length).
    Does NOT check availability, reserved status, or change window.
    
    Uses settings:
    - USERNAME_REGEX (default: ^[a-z0-9_]{3,32}$)
    - USERNAME_MIN_LEN (default: 3)
    - USERNAME_MAX_LEN (default: 32)
    
    Args:
        username: Username to validate (should be normalized first)
        
    Returns:
        (is_valid, error_code) tuple
        error_code is None if valid, otherwise one of:
        - 'username_required': Empty username
        - 'too_short': Below minimum length
        - 'too_long': Above maximum length
        - 'invalid_format': Doesn't match regex pattern
    """
    if not username:
        return False, 'username_required'
    
    normalized = normalize_username(username)
    
    # Length constraints
    min_len = getattr(settings, 'USERNAME_MIN_LEN', 3)
    max_len = getattr(settings, 'USERNAME_MAX_LEN', 32)
    
    if len(normalized) < min_len:
        return False, 'too_short'
    if len(normalized) > max_len:
        return False, 'too_long'
    
    # Format: regex pattern from settings
    pattern = getattr(settings, 'USERNAME_REGEX', r'^[a-z0-9_]{3,32}$')
    if not re.match(pattern, normalized):
        return False, 'invalid_format'
    
    return True, None


def get_username_error_message(error_code: str) -> str:
    """
    Get human-readable error message for a given error code.
    
    This provides a centralized mapping of machine-readable error codes
    to user-friendly messages.
    
    Args:
        error_code: Machine-readable error code
        
    Returns:
        Human-readable error message
    """
    messages = {
        'username_required': 'Username is required.',
        'too_short': 'Username must be at least 3 characters long.',
        'too_long': 'Username must be at most 32 characters long.',
        'invalid_format': 'Username can only contain lowercase letters, numbers, and underscores.',
        'reserved': 'This username is reserved and cannot be used.',
        'taken': 'This username is already taken.',
        'immutable_username': 'You have already used your one-time username change.',
        'same_username': 'New username cannot be the same as your current username.',
    }
    return messages.get(error_code, 'Invalid username.')