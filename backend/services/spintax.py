"""
Spintax parser for message randomization.
Supports nested spintax: {Hello|Hi {friend|buddy}}!
"""

import re
import random


def parse_spintax(text: str) -> str:
    """
    Parse spintax text and return a randomized version.
    
    Example:
        Input:  "{Привіт|Вітаю}! Шукаю траферів на {CPA|ПП}..."
        Output: "Вітаю! Шукаю траферів на CPA..."
    """
    pattern = r'\{([^{}]*)\}'
    
    while re.search(pattern, text):
        def replace_match(match):
            options = match.group(1).split('|')
            return random.choice(options)
        
        text = re.sub(pattern, replace_match, text)
    
    return text


def validate_spintax(text: str) -> dict:
    """
    Validate spintax syntax.
    Returns dict with 'valid' bool and 'error' message if invalid.
    """
    open_count = text.count('{')
    close_count = text.count('}')
    
    if open_count != close_count:
        return {
            "valid": False,
            "error": f"Mismatched braces: {open_count} opening, {close_count} closing"
        }
    
    # Check for empty options
    if '||' in text or '{|' in text or '|}' in text:
        return {
            "valid": False,
            "error": "Empty spintax option detected"
        }
    
    return {"valid": True, "error": None}


def count_variations(text: str) -> int:
    """Count the total number of possible unique variations."""
    pattern = r'\{([^{}]*)\}'
    matches = re.findall(pattern, text)
    
    if not matches:
        return 1
    
    count = 1
    for match in matches:
        options = match.split('|')
        count *= len(options)
    
    return count
