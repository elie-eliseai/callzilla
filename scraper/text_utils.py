"""
Text processing utilities for the property phone scraper.

Consolidates text normalization and keyword extraction that was previously
duplicated across multiple files.
"""
import re
from typing import Optional, Set

from .scraper_config import AGGREGATOR_DOMAINS


def normalize_phone(phone: str) -> str:
    """
    Normalize a phone number to (XXX) XXX-XXXX format.
    
    Handles:
    - 10-digit numbers: 5551234567 -> (555) 123-4567
    - 11-digit with leading 1: 15551234567 -> (555) 123-4567  
    - Already formatted: returns as-is if can't parse
    
    Args:
        phone: Raw phone string in any format
        
    Returns:
        Normalized phone string
    """
    digits = re.sub(r'\D', '', phone)
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    elif len(digits) == 11 and digits.startswith('1'):
        return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
    return phone


def extract_phone_from_text(text: str) -> Optional[str]:
    """
    Find and normalize the first phone number in a text string.
    
    Args:
        text: Text that may contain a phone number
        
    Returns:
        Normalized phone string, or None if no phone found
    """
    match = re.search(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', text)
    if match:
        return normalize_phone(match.group())
    return None


# Default stop words removed during keyword extraction
DEFAULT_STOP_WORDS = frozenset({
    'the', 'at', 'of', 'in', 'on', 'and', 'or', 'a', 'an',
    'apartments', 'apartment', 'apts', 'apt',
    'llc', 'inc',
})


def normalize_text(text: str, extra_removals: Optional[list[str]] = None) -> str:
    """
    Normalize text for comparison: lowercase, remove noise words, collapse whitespace.
    
    This consolidates the previously duplicated normalize() functions from
    sanity_check_google() and sanity_check_apartments().
    
    Args:
        text: Text to normalize
        extra_removals: Additional strings to remove (e.g., [',', '-'])
        
    Returns:
        Normalized text string
    """
    if not text:
        return ""
    
    result = text.lower()
    
    # Remove standard noise words
    for word in ['apartments', 'apartment', 'apts', 'apt', 'llc', 'inc', 'the', ',']:
        result = result.replace(word, ' ')
    
    # Remove any extra specified characters
    if extra_removals:
        for char in extra_removals:
            result = result.replace(char, ' ')
    
    # Collapse multiple spaces
    return ' '.join(result.split())


def extract_keywords(
    text: str, 
    stop_words: Optional[Set[str]] = None,
    min_length: int = 0,
) -> Set[str]:
    """
    Extract meaningful keywords from text.
    
    Args:
        text: Text to extract keywords from
        stop_words: Words to exclude (defaults to DEFAULT_STOP_WORDS)
        min_length: Minimum word length to include (0 = no minimum)
        
    Returns:
        Set of keyword strings
    """
    if stop_words is None:
        stop_words = DEFAULT_STOP_WORDS
    
    normalized = normalize_text(text)
    words = set(normalized.split())
    
    # Remove stop words
    words = words - stop_words
    
    # Filter by length
    if min_length > 0:
        words = {w for w in words if len(w) >= min_length}
    
    return words


def is_aggregator_domain(domain: str) -> bool:
    """
    Check if a domain is a rental aggregator site (Zillow, Apartments.com, etc).
    
    Checks for:
    - Exact match: "apartments.com"
    - WWW prefix: "www.apartments.com"  
    - Subdomain: "seattle.apartments.com"
    
    Args:
        domain: Domain string (e.g., "www.zillow.com")
        
    Returns:
        True if this is an aggregator domain
    """
    domain_lower = domain.lower()
    
    for agg in AGGREGATOR_DOMAINS:
        if (domain_lower == agg or 
            domain_lower == 'www.' + agg or 
            domain_lower.endswith('.' + agg)):
            return True
    
    return False


def generate_org_patterns(org_name: str) -> list[str]:
    """
    Generate possible domain patterns from an organization name.
    
    Used to identify if a search result belongs to the property's management company.
    
    Examples:
        'Plenty of Places' -> ['plentyofplaces', 'plenty', 'pop', 'plentyplaces']
        'Left View Residential' -> ['leftviewresidential', 'leftview', 'lvresidential', 'lvr']
    
    Args:
        org_name: Organization/company name
        
    Returns:
        List of domain patterns, sorted by length (longer = more specific first)
    """
    if not org_name:
        return []
    
    # Normalize and split, removing common filler words
    words = org_name.lower().split()
    words = [w for w in words if w not in ['of', 'the', 'and', 'at', 'llc', 'inc']]
    
    if not words:
        return []
    
    patterns = set()
    
    # Full name joined: "plentyofplaces"
    patterns.add(''.join(words))
    
    # First word alone: "plenty"
    patterns.add(words[0])
    
    if len(words) >= 2:
        # First + last word: "plentyplaces"
        patterns.add(words[0] + words[-1])
        
        # Last word alone: "places"
        patterns.add(words[-1])
        
        # Initials + last word: "popplaces" or "lvresidential"
        initials = ''.join(w[0] for w in words[:-1])
        patterns.add(initials + words[-1])
        
        # Just initials: "pop", "lvr"
        patterns.add(''.join(w[0] for w in words))
        
        # First two words: "plentyof"
        patterns.add(words[0] + words[1])
    
    # Filter out very short patterns (< 3 chars) - too many false positives
    patterns = [p for p in patterns if len(p) >= 3]
    
    # Sort by length descending - longer patterns are more specific, check first
    return sorted(patterns, key=len, reverse=True)

