"""
Configuration and constants for the property phone scraper.

This module centralizes all configuration, API keys, and magic numbers
so they're documented in one place rather than scattered across files.
"""
import os
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Configure logging for the entire scraper package
# Clean format without timestamps for readable progress output
logging.basicConfig(
    level=logging.INFO,
    format='      %(message)s'
)
logger = logging.getLogger('scraper')

# Suppress noisy HTTP library logs
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)


@dataclass
class Config:
    """
    Centralized configuration for all scraper components.
    
    Load from environment variables via Config.from_env(), or pass values directly
    for testing.
    """
    serpapi_key: Optional[str] = None
    openai_key: Optional[str] = None
    crawlbase_token: Optional[str] = None
    brightdata_token: Optional[str] = None
    brightdata_zone: str = 'web_unlocker1'
    
    @classmethod
    def from_env(cls, env_file: Optional[Path] = None) -> 'Config':
        """
        Load configuration from environment variables.
        Optionally loads a .env file first.
        """
        # Load .env file if it exists (check package dir first, then parent project dir)
        if env_file:
            env_path = env_file
        elif (Path(__file__).parent / '.env').exists():
            env_path = Path(__file__).parent / '.env'
        else:
            env_path = Path(__file__).parent.parent / '.env'
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ.setdefault(key.strip(), value.strip())
        
        return cls(
            serpapi_key=os.environ.get('SERPAPI_KEY'),
            openai_key=os.environ.get('OPENAI_API_KEY'),
            crawlbase_token=os.environ.get('CRAWLBASE_TOKEN'),
            brightdata_token=os.environ.get('BRIGHTDATA_TOKEN'),
            brightdata_zone=os.environ.get('BRIGHTDATA_ZONE', 'web_unlocker1'),
        )
    
    def validate(self) -> list[str]:
        """Return list of missing required keys."""
        missing = []
        if not self.serpapi_key:
            missing.append('SERPAPI_KEY')
        return missing


# =============================================================================
# Model Configuration
# =============================================================================

# GPT model for URL selection and phone extraction
# Using gpt-4o-mini for cost efficiency - it handles structured selection well
GPT_MODEL = "gpt-4o-mini"

# Max tokens for GPT responses (we only need short answers: a number or phone)
GPT_MAX_TOKENS_URL_PICK = 10
GPT_MAX_TOKENS_PHONE_PICK = 30


# =============================================================================
# Search Configuration  
# =============================================================================

# Number of Google results to fetch per search
# 30 gives good coverage without API cost increase (SerpAPI charges per search, not per result)
SEARCH_RESULT_COUNT = 30

# HTTP request timeout in seconds
HTTP_TIMEOUT = 30
HTTP_TIMEOUT_EXTENDED = 60  # For Bright Data requests which can be slower


# =============================================================================
# Matching Thresholds
# =============================================================================

# Minimum keyword overlap ratio to consider a name match
# 0.5 = at least half the searched keywords must appear in result
# Why 0.5? Balances false positives (too low) vs missing valid matches (too high)
NAME_MATCH_THRESHOLD = 0.5

# Minimum location parts overlap for a location match  
# 2 = typically city + state must match
# Why 2? Single word matches too loosely (e.g., just "CA" matches wrong cities)
LOCATION_MATCH_MIN_PARTS = 2

# Maximum character distance to associate a heading with a phone number
# 2000 chars ≈ a few paragraphs - headings further away aren't contextually relevant
HEADING_PROXIMITY_THRESHOLD = 2000


# =============================================================================
# Aggregator Domains
# =============================================================================

# ILS (Internet Listing Service) domains to skip when looking for property websites.
# These are aggregators that list many properties - we want the property's OWN site.
# Organized by category for easier maintenance.

AGGREGATOR_DOMAINS = [
    # Major rental aggregators
    'apartments.com',
    'zillow.com', 
    'trulia.com',
    'rent.com',
    'realtor.com',
    'hotpads.com',
    'zumper.com',
    'apartmentlist.com',
    'apartmentfinder.com',
    'rentcafe.com',
    'forrent.com',
    'padmapper.com',
    'apartmentguide.com',
    'rentpath.com',
    'abodo.com',
    'apartmenthomeliving.com',
    'mynewplace.com',
    'rentjungle.com',
    'renthop.com',
    'rentable.co',
    
    # Real estate / home buying sites (sometimes list rentals)
    'redfin.com',
    'homes.com',
    'costar.com',
    'loopnet.com',
    'move.com',
    'movoto.com',
    'homesnap.com',
    'compass.com',
    'homelight.com',
    'opendoor.com',
    'offerpad.com',
    
    # General directories and review sites
    'google.com',
    'yelp.com',
    'bbb.org',
    'yellowpages.com',
    'mapquest.com',
    'walkscore.com',
    'apartmentratings.com',
    'craigslist.org',
    
    # Social media
    'facebook.com',
    'linkedin.com',
    'instagram.com',
    'twitter.com',
    'x.com',
    
    # Other services
    'umovefree.com',  # Relocation service
    'furnishedhousing.com',  # Furnished rentals aggregator
]


# =============================================================================
# Phone Extraction Labels
# =============================================================================

# Labels that indicate a phone is the primary contact number
POSITIVE_PHONE_LABELS = [
    'contact',
    'phone', 
    'call',
    'leasing',
    'tel:',
    'reach us',
    'get in touch',
]

# Labels that indicate a phone should be skipped
NEGATIVE_PHONE_LABELS = [
    'fax',
    'emergency',
    'tty',
    'maintenance',
    'corporate',
    'headquarters',
    'billing',
]

