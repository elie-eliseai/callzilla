"""
Apartments.com scraping via Bright Data Web Unlocker.

Apartments.com has aggressive anti-bot protection that blocks regular requests.
We use Bright Data's Web Unlocker service to bypass this protection.

Flow:
1. Search Google for the Apartments.com listing URL
2. Fetch the listing page via Bright Data
3. Extract phone from the "Contact This Property" card
"""
import logging
import re
from typing import Optional

import httpx

from .scraper_config import HTTP_TIMEOUT, HTTP_TIMEOUT_EXTENDED
from .models import ScrapeResult
from .text_utils import normalize_phone, normalize_text, extract_keywords
from .clients import SerpAPIClient, BrightDataClient

logger = logging.getLogger('scraper.apartments')


def sanity_check_apartments(
    searched_name: str,
    searched_location: str,
    result_name: Optional[str],
    result_url: Optional[str],
) -> dict:
    """
    Verify Apartments.com result matches what we searched for.
    
    Less strict than Google sanity check because Apartments.com URLs
    often contain useful keywords we can match against.
    
    Args:
        searched_name: Property name we searched for
        searched_location: Location we searched for (unused but kept for API consistency)
        result_name: Title of the Apartments.com listing
        result_url: URL of the listing
        
    Returns:
        Dict with 'passed' and 'warnings' keys
    """
    warnings = []
    
    # Extract keywords from searched name
    searched_keywords = extract_keywords(searched_name, min_length=3)
    
    # Extract keywords from result name and URL
    result_keywords = extract_keywords(result_name, min_length=3) if result_name else set()
    
    if result_url:
        # URLs like /property-name-city-state/ contain useful keywords
        url_text = result_url.replace('/', ' ').replace('-', ' ')
        url_keywords = extract_keywords(url_text, min_length=3)
        result_keywords = result_keywords | url_keywords
    
    # Check for overlap
    overlap = searched_keywords & result_keywords
    
    if overlap:
        return {"passed": True, "warnings": []}
    else:
        warnings.append(f"No keyword overlap between '{searched_name}' and result")
        return {"passed": False, "warnings": warnings}


def _extract_phone_from_html(html: str) -> Optional[str]:
    """
    Extract phone number from Apartments.com HTML.
    
    Apartments.com embeds phone data in multiple places:
    - JSON-LD structured data
    - data-phone attributes
    - tel: links
    
    We try multiple patterns to maximize extraction success.
    """
    # Patterns in order of reliability
    patterns = [
        r'"phoneNumber"\s*:\s*"([^"]+)"',  # JSON-LD
        r'data-phone="([^"]+)"',            # Data attribute
        r'href="tel:([^"]+)"',              # Tel link
        r'"phone"\s*:\s*"([^"]+)"',         # Generic JSON
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, html)
        for match in matches:
            digits = re.sub(r'\D', '', match)
            # Valid US phone: 10 digits or 11 with leading 1
            if len(digits) == 10 or (len(digits) == 11 and digits.startswith('1')):
                return match
    
    return None


async def scrape_apartments(
    property_name: str,
    location: str,
    serpapi_client: SerpAPIClient,
    brightdata_client: BrightDataClient,
) -> ScrapeResult:
    """
    Find and scrape Apartments.com listing for phone number.
    
    Args:
        property_name: Name of the apartment property
        location: City, State or full address
        serpapi_client: Configured SerpAPI client
        brightdata_client: Configured Bright Data client
        
    Returns:
        ScrapeResult with phone if found
    """
    # Step 1: Find the Apartments.com listing via Google search
    search_query = f"{property_name} {location} apartments.com"
    
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_EXTENDED) as http_client:
            response = await serpapi_client.search(
                query=search_query,
                num_results=10,
                http_client=http_client,
            )
            
            organic_results = serpapi_client.get_organic_results(response)
            
            # Find apartments.com link (not a category page)
            apartments_url = None
            result_name = None
            
            for item in organic_results:
                url = item.get("link", "")
                # Match apartments.com property pages, not /apartments/ category pages
                if "apartments.com" in url and "/apartments/" not in url:
                    apartments_url = url
                    result_name = item.get("title", "")
                    break
            
            if not apartments_url:
                return ScrapeResult.not_found(
                    property_name=property_name,
                    location=location,
                    source='apartments.com',
                    reason="No apartments.com listing found in search results",
                )
            
            logger.info(f"Found Apartments.com listing: {apartments_url}")
            
            # Step 2: Fetch via Bright Data
            html, fetch_error = await brightdata_client.fetch(apartments_url, http_client)
            
            if fetch_error:
                return ScrapeResult.create_error(
                    property_name=property_name,
                    location=location,
                    source='apartments.com',
                    error=fetch_error,
                )
            
            logger.info(f"Bright Data returned {len(html)} bytes")
            
            # Step 3: Check if property is actively advertising
            if ("This property is not currently advertising" in html or
                "is not currently advertising on Apartments.com" in html):
                result = ScrapeResult.not_found(
                    property_name=property_name,
                    location=location,
                    source='apartments.com',
                    reason="Property not advertising on Apartments.com",
                    listing_url=apartments_url,
                    result_name=result_name,
                )
                result.status = 'not_advertising'
                return result
            
            # Step 4: Extract phone
            phone = _extract_phone_from_html(html)
            
            if not phone:
                # Debug info for troubleshooting
                tel_count = html.count('tel:')
                phone_count = html.lower().count('phone')
                logger.warning(
                    f"No phone extracted from {apartments_url} "
                    f"(tel: {tel_count}x, 'phone' {phone_count}x in HTML)"
                )
                return ScrapeResult.not_found(
                    property_name=property_name,
                    location=location,
                    source='apartments.com',
                    reason="No phone found in contact card",
                    listing_url=apartments_url,
                    result_name=result_name,
                )
            
            # Step 5: Sanity check
            check = sanity_check_apartments(property_name, location, result_name, apartments_url)
            
            result = ScrapeResult.success(
                property_name=property_name,
                location=location,
                source='apartments.com',
                phone=normalize_phone(phone),
                listing_url=apartments_url,
                result_name=result_name,
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
            source='apartments.com',
            error=f"HTTP error: {e.response.status_code}",
        )
    except Exception as e:
        logger.exception(f"Apartments.com scrape failed for {property_name}")
        return ScrapeResult.create_error(
            property_name=property_name,
            location=location,
            source='apartments.com',
            error=f"Apartments.com scrape failed: {str(e)}",
        )


# Backwards compatibility alias
scrape_apartments_crawlbase = scrape_apartments
