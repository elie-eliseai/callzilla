"""
Google Knowledge Panel scraping via SerpAPI.

This module extracts phone numbers from Google's Knowledge Graph panel,
which appears on the right side of search results for businesses.

The Knowledge Graph is Google's curated database of business information,
so phones found here are typically reliable and well-verified.
"""
import logging
from typing import Optional

import httpx

from .scraper_config import HTTP_TIMEOUT, NAME_MATCH_THRESHOLD, LOCATION_MATCH_MIN_PARTS
from .models import ScrapeResult
from .text_utils import normalize_phone, normalize_text, extract_keywords
from .clients import SerpAPIClient

logger = logging.getLogger('scraper.google')


def sanity_check_google(
    searched_name: str,
    searched_location: str,
    result_name: Optional[str],
    result_address: Optional[str],
) -> dict:
    """
    Verify Google Knowledge Graph result matches what we searched for.
    
    Uses strict matching to avoid returning phone numbers for wrong businesses
    (e.g., searching "Oak Park Apartments" shouldn't return "Oak Ridge Apartments").
    
    Args:
        searched_name: Property name we searched for
        searched_location: Location we searched for
        result_name: Name returned by Google
        result_address: Address returned by Google
        
    Returns:
        Dict with 'passed', 'name_match', 'location_match', 'warnings' keys
    """
    warnings = []
    name_match = False
    location_match = False
    
    # Check name match
    if result_name:
        searched_keywords = extract_keywords(searched_name, min_length=0)
        result_keywords = extract_keywords(result_name, min_length=0)
        
        if searched_keywords and result_keywords:
            overlap = searched_keywords & result_keywords
            coverage = len(overlap) / max(len(searched_keywords), 1)
            
            if coverage >= NAME_MATCH_THRESHOLD:
                name_match = True
            elif coverage > 0:
                warnings.append(f"Partial name match: '{result_name}' vs searched '{searched_name}'")
            else:
                warnings.append(f"Name mismatch: '{result_name}' vs searched '{searched_name}'")
    else:
        warnings.append("No name returned from Google")
    
    # Check location match
    if result_address and searched_location:
        searched_parts = _extract_location_parts(normalize_text(searched_location))
        result_parts = _extract_location_parts(normalize_text(result_address))
        
        if searched_parts and result_parts:
            overlap = searched_parts & result_parts
            if len(overlap) >= LOCATION_MATCH_MIN_PARTS:
                location_match = True
            elif overlap:
                warnings.append(f"Partial location match: '{result_address}'")
            else:
                warnings.append(f"Location mismatch: '{result_address}' vs searched '{searched_location}'")
    elif not result_address:
        warnings.append("No address returned from Google")
    
    return {
        "passed": name_match and location_match,
        "name_match": name_match,
        "location_match": location_match,
        "warnings": warnings,
    }


def _extract_location_parts(normalized_location: str) -> set[str]:
    """
    Extract meaningful location parts from a normalized location string.
    
    Includes words 3+ chars and common 2-letter state abbreviations.
    """
    # Common US state abbreviations (lowercase)
    state_abbrevs = {'ca', 'az', 'nv', 'co', 'tx', 'fl', 'ny', 'wa', 'or', 
                    'ga', 'nc', 'sc', 'va', 'md', 'pa', 'oh', 'il', 'mi'}
    
    parts = set()
    for word in normalized_location.split():
        if len(word) >= 3 or word in state_abbrevs:
            parts.add(word)
    return parts


async def scrape_google(
    property_name: str,
    location: str,
    serpapi_client: SerpAPIClient,
) -> ScrapeResult:
    """
    Search Google and extract phone from Knowledge Panel.
    
    The Knowledge Panel is Google's structured data about businesses,
    appearing on the right side of search results. It's the most reliable
    source when available, but not all properties have one.
    
    Args:
        property_name: Name of the apartment property
        location: City, State or full address
        serpapi_client: Configured SerpAPI client
        
    Returns:
        ScrapeResult with phone if found in Knowledge Graph
    """
    search_query = f"{property_name} {location}"
    
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as http_client:
            # Search via SerpAPI
            response = await serpapi_client.search(
                query=search_query,
                num_results=10,  # We only need Knowledge Graph, not organic results
                http_client=http_client,
            )
            
            # Build Google search URL for reference
            listing_url = f"https://www.google.com/search?q={search_query.replace(' ', '+')}"
            
            # Extract Knowledge Graph data
            knowledge_graph = serpapi_client.get_knowledge_graph(response)
            
            if not knowledge_graph:
                return ScrapeResult.not_found(
                    property_name=property_name,
                    location=location,
                    source='google',
                    reason="No Knowledge Graph found",
                    listing_url=listing_url,
                    needs_review=True,
                )
            
            result_name = knowledge_graph.get("title")
            result_address = knowledge_graph.get("address")
            phone = knowledge_graph.get("phone")
            
            if not phone:
                return ScrapeResult.not_found(
                    property_name=property_name,
                    location=location,
                    source='google',
                    reason="Knowledge Graph has no phone",
                    listing_url=listing_url,
                    result_name=result_name,
                    needs_review=True,
                )
            
            # Sanity check: verify result matches what we searched
            check = sanity_check_google(property_name, location, result_name, result_address)
            
            result = ScrapeResult.success(
                property_name=property_name,
                location=location,
                source='google',
                phone=normalize_phone(phone),
                listing_url=listing_url,
                result_name=result_name,
                address=result_address,
            )
            
            if not check["passed"]:
                result.with_review("Sanity check failed")
                result.warnings = check["warnings"]
            elif check["warnings"]:
                result.warnings = check["warnings"]
            
            return result
            
    except httpx.HTTPStatusError as e:
        return ScrapeResult.create_error(
            property_name=property_name,
            location=location,
            source='google',
            error=f"SerpAPI error: {e.response.status_code}",
        )
    except Exception as e:
        logger.exception(f"Google scrape failed for {property_name}")
        return ScrapeResult.create_error(
            property_name=property_name,
            location=location,
            source='google',
            error=f"Google scrape failed: {str(e)}",
        )


# Backwards compatibility: old function signature
async def scrape_google_serpapi(
    property_name: str,
    location: str,
    serpapi_key: str = None,
) -> dict:
    """
    Legacy wrapper for scrape_google().
    
    Deprecated: Use scrape_google() with a SerpAPIClient instead.
    """
    import os
    key = serpapi_key or os.environ.get('SERPAPI_KEY')
    if not key:
        return ScrapeResult.create_error(
            property_name=property_name,
            location=location,
            source='google',
            error="SerpAPI key required",
        ).to_dict()
    
    client = SerpAPIClient(key)
    result = await scrape_google(property_name, location, client)
    return result.to_dict()
