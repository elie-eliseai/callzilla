"""
Property website scraping - find and extract phone from property's own website.

This is the most complex scraper because it needs to:
1. Find the property's website among many search results
2. Filter out aggregator sites (Zillow, Apartments.com, etc.)
3. Use GPT to pick the best candidate when multiple exist
4. Extract and identify the primary phone number from HTML

The GPT decisions are logged to gpt_decisions_corpus.jsonl for debugging accuracy.
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

from .scraper_config import HTTP_TIMEOUT, SEARCH_RESULT_COUNT
from .models import ScrapeResult, WebsiteCandidate
from .text_utils import normalize_phone, is_aggregator_domain, generate_org_patterns
from .clients import SerpAPIClient, OpenAIClient, HTTPClient
from .phone_extractor import extract_phones_from_html, pick_primary_phone

logger = logging.getLogger('scraper.property_website')

# Path to GPT decision corpus for debugging accuracy
CORPUS_FILE = Path(__file__).parent / "gpt_decisions_corpus.jsonl"


# =============================================================================
# URL Selection
# =============================================================================

def filter_search_results(
    organic_results: list[dict],
    org_patterns: list[str],
) -> list[WebsiteCandidate]:
    """
    Filter search results to find property website candidates.
    
    Removes aggregator domains (Zillow, Apartments.com, etc.) and
    extracts structured candidate objects.
    
    Args:
        organic_results: Raw search results from SerpAPI
        org_patterns: Domain patterns for the property's org (optional)
        
    Returns:
        List of WebsiteCandidate objects (non-aggregators only)
    """
    candidates = []
    
    for item in organic_results:
        url = item.get("link", "")
        if not url or len(url.split("/")) < 3:
            continue
            
        domain = url.split("/")[2].lower()
        
        # Skip aggregator domains
        if is_aggregator_domain(domain):
            continue
        
        candidates.append(WebsiteCandidate(
            url=url,
            domain=domain,
            title=item.get("title", ""),
            snippet=item.get("snippet", ""),
        ))
    
    return candidates


def build_url_pick_prompt(
    property_name: str,
    location: str,
    candidates: list[WebsiteCandidate],
    org_name: Optional[str] = None,
) -> str:
    """
    Build GPT prompt for selecting the best URL.
    
    Strips org_name from titles/snippets to avoid biasing GPT toward
    management company sites over property-specific sites.
    """
    def clean_text(text: str) -> str:
        """Remove org name variations to avoid bias."""
        if not org_name or not text:
            return text
        result = text
        for variant in [org_name, org_name.replace(',', ''), org_name.split(',')[0]]:
            result = result.replace(variant, '').replace(variant.lower(), '')
        return result.strip()
    
    candidates_text = "\n".join([
        f"{i+1}. {clean_text(c.title)}\n   URL: {c.url}\n   Snippet: {clean_text(c.snippet[:100])}..."
        for i, c in enumerate(candidates[:5])
    ])
    
    return f"""Select the official property website - where a renter would go to inquire.

Property: {property_name}, {location}

{candidates_text}

RULES (in priority order):
1. Prefer URLs containing the property name (e.g., altadavis.com for "Alta Davis")
2. Dedicated domains (property.com) beat company portfolio pages (company.com/property/X)
3. Skip aggregators, news, reviews, job postings

Reply with ONLY the number or NONE."""


def pick_best_candidate(
    candidates: list[WebsiteCandidate],
    property_name: str,
    location: str,
    gpt_client: Optional[OpenAIClient],
    org_name: Optional[str] = None,
) -> tuple[WebsiteCandidate, bool]:
    """
    Pick the best website candidate, using GPT if multiple exist.
    
    Args:
        candidates: Non-empty list of website candidates
        property_name: Property name for context
        location: Location for context
        gpt_client: OpenAI client (or None to use first candidate)
        org_name: Optional org name to hide from GPT prompt
        
    Returns:
        Tuple of (chosen_candidate, needs_review)
    """
    # Single candidate - no GPT needed
    if len(candidates) == 1:
        return candidates[0], False
    
    # No GPT client - use first candidate
    if not gpt_client:
        logger.warning("No OpenAI client - using first candidate")
        return candidates[0], True
    
    # Multiple candidates - ask GPT
    prompt = build_url_pick_prompt(property_name, location, candidates, org_name)
    pick = gpt_client.pick_url(prompt)
    
    # Build decision log for corpus
    gpt_decision = {
        "property_name": property_name,
        "location": location,
        "org_name": org_name,
        "candidates": [
            {"title": c.title, "url": c.url, "snippet": c.snippet[:150]}
            for c in candidates[:5]
        ],
        "gpt_pick": pick,
        "gpt_picked_url": None,
        "timestamp": datetime.now().isoformat(),
    }
    
    # Parse GPT response
    needs_review = False
    if pick and pick.isdigit() and 1 <= int(pick) <= len(candidates):
        chosen = candidates[int(pick) - 1]
        gpt_decision["gpt_picked_url"] = chosen.url
        logger.info(f"GPT picked: {chosen.domain}")
    else:
        # GPT unsure - use first, flag for review
        chosen = candidates[0]
        gpt_decision["gpt_picked_url"] = chosen.url
        needs_review = True
        logger.warning(f"GPT uncertain ('{pick}') - using first result")
    
    # Log decision to corpus
    _log_gpt_decision(gpt_decision)
    
    return chosen, needs_review


def _log_gpt_decision(decision: dict) -> None:
    """Append GPT decision to corpus file for accuracy analysis."""
    try:
        with open(CORPUS_FILE, "a") as f:
            f.write(json.dumps(decision) + "\n")
    except Exception as e:
        logger.warning(f"Failed to log GPT decision: {e}")


# =============================================================================
# Main Entry Point
# =============================================================================

async def scrape_property_website(
    property_name: str,
    location: str,
    serpapi_client: SerpAPIClient,
    gpt_client: Optional[OpenAIClient] = None,
    http_client: Optional[HTTPClient] = None,
    org_name: Optional[str] = None,
    url_only: bool = False,
) -> ScrapeResult:
    """
    Find and scrape the property's official website for phone number.
    
    Flow:
    1. Search Google for property + location
    2. Filter out aggregator domains
    3. Use GPT to pick best candidate (if multiple)
    4. Fetch HTML (with Cloudflare fallback)
    5. Extract phones and use GPT to pick primary
    
    Args:
        property_name: Name of the apartment property
        location: City, State or full address
        serpapi_client: Configured SerpAPI client
        gpt_client: OpenAI client for selection (optional but recommended)
        http_client: HTTP client with Cloudflare fallback (optional)
        org_name: Management company name for better search (optional)
        url_only: If True, return after finding URL (skip phone extraction)
        
    Returns:
        ScrapeResult with phone if found
    """
    # Build search query
    search_query = f"{property_name} {location}"
    if org_name:
        search_query += f" {org_name}"
    
    logger.info(f"Searching: {search_query}")
    
    # Generate org patterns for filtering
    org_patterns = generate_org_patterns(org_name) if org_name else []
    if org_patterns:
        logger.info(f"Org patterns: {org_patterns[:3]}...")
    
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            # Step 1: Search
            response = await serpapi_client.search(
                query=search_query,
                num_results=SEARCH_RESULT_COUNT,
                http_client=client,
            )
            organic_results = serpapi_client.get_organic_results(response)
            logger.info(f"Got {len(organic_results)} search results")
            
            # Step 2: Filter candidates
            candidates = filter_search_results(organic_results, org_patterns)
            
            if not candidates:
                return ScrapeResult.not_found(
                    property_name=property_name,
                    location=location,
                    source='property_website',
                    reason="No property website found (only aggregators)",
                )
            
            # Step 3: Pick best candidate
            chosen, url_needs_review = pick_best_candidate(
                candidates, property_name, location, gpt_client, org_name
            )
            
            logger.info(f"Selected: {chosen.domain}")
            
            # Build partial result
            result = ScrapeResult(
                property_name=property_name,
                location=location,
                source='property_website',
                listing_url=chosen.url,
                result_name=chosen.title,
                candidates=[c.domain for c in candidates[:10]],
            )
            
            if url_needs_review:
                result.with_review("GPT uncertain - used first result")
            
            # URL-only mode: stop here
            if url_only:
                result.status = 'url_found'
                result.verified = True
                logger.info("URL-only mode - skipping phone extraction")
                return result
            
            # Step 4: Fetch HTML
            logger.info("Fetching website content...")
            
            if http_client:
                html, fetch_error = await http_client.fetch(chosen.url, client)
            else:
                # Fallback to direct fetch
                try:
                    resp = await client.get(chosen.url, follow_redirects=True)
                    html, fetch_error = resp.text, None
                except Exception as e:
                    html, fetch_error = None, str(e)
            
            if fetch_error and not html:
                result.error = fetch_error
                result.status = 'error'
                return result
            
            if fetch_error:
                result.with_review(fetch_error)
            
            # Step 5: Extract phones (using phone_extractor module)
            phone_candidates = extract_phones_from_html(html)
            
            if not phone_candidates:
                logger.warning("No phone patterns found in HTML")
                result.status = 'not_found'
                result.with_review("No phone found on page")
                return result
            
            logger.info(f"Found {len(phone_candidates)} phone(s)")
            
            # Step 6: Pick primary phone (using phone_extractor module)
            phone, phone_needs_review = pick_primary_phone(
                phone_candidates, property_name, location, gpt_client
            )
            
            if phone:
                result.phone = normalize_phone(phone)
                result.status = 'found'
                result.verified = True
                if phone_needs_review:
                    result.with_review("GPT couldn't determine primary phone")
                logger.info(f"Primary phone: {result.phone}")
            else:
                result.status = 'not_found'
                result.with_review("No primary phone identified")
            
            return result
            
    except httpx.HTTPStatusError as e:
        return ScrapeResult.create_error(
            property_name=property_name,
            location=location,
            source='property_website',
            error=f"HTTP error: {e.response.status_code}",
        )
    except Exception as e:
        logger.exception(f"Property website scrape failed for {property_name}")
        return ScrapeResult.create_error(
            property_name=property_name,
            location=location,
            source='property_website',
            error=f"Scrape failed: {str(e)}",
        )
