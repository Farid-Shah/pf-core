"""
Currency utilities for single-currency app.

All amounts are stored in SITE_CURRENCY_CODE from settings.
"""

from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings


def get_currency_code() -> str:
    """
    Get the site's currency code.
    
    Returns:
        str: Currency code (e.g., 'USD')
    """
    return getattr(settings, 'SITE_CURRENCY_CODE', 'USD')


def get_minor_units() -> int:
    """
    Get the number of decimal places for the site currency.
    
    Returns:
        int: Number of minor units (e.g., 2 for cents)
    """
    return getattr(settings, 'SITE_CURRENCY_MINOR_UNITS', 2)


def format_amount(amount_minor: int) -> str:
    """
    Format minor units to human-readable string.
    
    Args:
        amount_minor: Amount in minor units (e.g., 1050 cents)
        
    Returns:
        Formatted string (e.g., "10.50")
        
    Example:
        >>> format_amount(1050)
        '10.50'
        >>> format_amount(1000)
        '10.00'
    """
    minor_units = get_minor_units()
    divisor = 10 ** minor_units
    major = Decimal(amount_minor) / Decimal(divisor)
    return f"{major:.{minor_units}f}"


def to_minor_units(amount: Decimal) -> int:
    """
    Convert major units to minor units.
    
    Args:
        amount: Amount in major units (e.g., Decimal('10.50'))
        
    Returns:
        Amount in minor units (e.g., 1050)
        
    Example:
        >>> to_minor_units(Decimal('10.50'))
        1050
        >>> to_minor_units(Decimal('10.00'))
        1000
    """
    minor_units = get_minor_units()
    multiplier = 10 ** minor_units
    # Use ROUND_HALF_UP to avoid floating point issues
    return int((amount * multiplier).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def format_currency(amount_minor: int, include_code: bool = False) -> str:
    """
    Format amount with currency symbol.
    
    Args:
        amount_minor: Amount in minor units
        include_code: If True, include currency code (e.g., "USD 10.50")
        
    Returns:
        Formatted string with currency (e.g., "$10.50" or "USD 10.50")
        
    Example:
        >>> format_currency(1050)
        '$10.50'
        >>> format_currency(1050, include_code=True)
        'USD 10.50'
    """
    formatted = format_amount(amount_minor)
    code = get_currency_code()
    
    if include_code:
        return f"{code} {formatted}"
    
    # Simple currency symbols (expand as needed)
    symbols = {
        'USD': '$',
        'EUR': '€',
        'GBP': '£',
        'JPY': '¥',
        'CNY': '¥',
        'INR': '₹',
        'CAD': 'CA$',
        'AUD': 'A$',
    }
    
    symbol = symbols.get(code, code)
    return f"{symbol}{formatted}"


def parse_amount(amount_str: str) -> int:
    """
    Parse user input string to minor units.
    
    Args:
        amount_str: User input (e.g., "10.50", "$10.50", "10")
        
    Returns:
        Amount in minor units
        
    Raises:
        ValueError: If input is invalid
        
    Example:
        >>> parse_amount("10.50")
        1050
        >>> parse_amount("$10.50")
        1050
        >>> parse_amount("10")
        1000
    """
    # Remove common symbols and whitespace
    cleaned = amount_str.strip().replace('$', '').replace('€', '').replace('£', '').replace(',', '')
    
    try:
        decimal_amount = Decimal(cleaned)
        if decimal_amount < 0:
            raise ValueError("Amount cannot be negative")
        return to_minor_units(decimal_amount)
    except Exception as e:
        raise ValueError(f"Invalid amount format: {amount_str}") from e