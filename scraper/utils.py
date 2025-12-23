"""
Backwards compatibility re-exports.

Most utilities have moved to more specific modules:
- text_utils.py: normalize_phone, extract_phone_from_text, normalize_text, etc.
- config.py: AGGREGATOR_DOMAINS
- google.py: sanity_check_google
- apartments.py: sanity_check_apartments

This file re-exports them for backwards compatibility with existing imports.
"""

# Re-export from text_utils
from .text_utils import (
    normalize_phone,
    extract_phone_from_text,
    normalize_text,
    extract_keywords,
    is_aggregator_domain,
    generate_org_patterns,
)

# Re-export from config
from .scraper_config import AGGREGATOR_DOMAINS

# Re-export sanity checks from their new locations
from .google import sanity_check_google
from .apartments import sanity_check_apartments

__all__ = [
    # Text utilities
    'normalize_phone',
    'extract_phone_from_text',
    'normalize_text',
    'extract_keywords',
    'is_aggregator_domain',
    'generate_org_patterns',
    # Config
    'AGGREGATOR_DOMAINS',
    # Sanity checks
    'sanity_check_google',
    'sanity_check_apartments',
]
