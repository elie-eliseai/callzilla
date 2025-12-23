"""
Property Phone Number Scraper
=============================

Scrapes phone numbers from Google, Apartments.com, and property websites.

Library Usage:
    from scraper import PropertyPhoneScraper
    
    scraper = PropertyPhoneScraper()
    
    # Single property
    result = await scraper.scrape_google("AZ Commons", "Tucson, AZ")
    
    # All sources
    results = await scraper.scrape_all("AZ Commons", "Tucson, AZ")

CLI Usage:
    python scraper.py --csv properties.csv --sources google,apartments.com,property_website
"""
import asyncio
import csv
import argparse
import logging
from datetime import datetime
from typing import Optional

from .scraper_config import Config, logger
from .models import ScrapeResult
from .clients import ClientFactory, SerpAPIClient, OpenAIClient, HTTPClient, BrightDataClient
from .google import scrape_google
from .apartments import scrape_apartments
from .property_website import scrape_property_website


class PropertyPhoneScraper:
    """
    Unified scraper for property phone numbers.
    
    Creates API clients once and reuses them across all scrape calls,
    rather than creating new clients for each request.
    
    Usage:
        scraper = PropertyPhoneScraper()  # Loads config from env
        
        result = await scraper.scrape_google("Property Name", "City, ST")
        result = await scraper.scrape_apartments("Property Name", "City, ST")
        result = await scraper.scrape_property_website("Property Name", "City, ST")
        
        # Or scrape all sources
        results = await scraper.scrape_all("Property Name", "City, ST")
    """
    
    def __init__(self, config: Optional[Config] = None):
        """
        Initialize scraper with configuration.
        
        Args:
            config: Configuration object. If None, loads from environment.
        """
        self.config = config or Config.from_env()
        self._factory = ClientFactory(self.config)
    
    @property
    def serpapi(self) -> Optional[SerpAPIClient]:
        """Get SerpAPI client."""
        return self._factory.serpapi()
    
    @property
    def openai(self) -> Optional[OpenAIClient]:
        """Get OpenAI client."""
        return self._factory.openai()
    
    @property
    def http(self) -> HTTPClient:
        """Get HTTP client."""
        return self._factory.http()
    
    @property
    def brightdata(self) -> Optional[BrightDataClient]:
        """Get Bright Data client."""
        return self._factory.brightdata()
    
    async def scrape_google(self, property_name: str, location: str) -> ScrapeResult:
        """
        Scrape Google Knowledge Panel for phone.
        
        Args:
            property_name: Name of the apartment property
            location: City, State or full address
            
        Returns:
            ScrapeResult with phone if found in Knowledge Graph
        """
        if not self.serpapi:
            return ScrapeResult.create_error(
                property_name, location, 'google',
                error="SerpAPI key required (set SERPAPI_KEY env var)"
            )
        
        return await scrape_google(property_name, location, self.serpapi)
    
    async def scrape_apartments(self, property_name: str, location: str) -> ScrapeResult:
        """
        Scrape Apartments.com for phone via Bright Data.
        
        Args:
            property_name: Name of the apartment property
            location: City, State or full address
            
        Returns:
            ScrapeResult with phone if found on Apartments.com
        """
        if not self.serpapi:
            return ScrapeResult.create_error(
                property_name, location, 'apartments.com',
                error="SerpAPI key required (set SERPAPI_KEY env var)"
            )
        
        if not self.brightdata:
            return ScrapeResult.create_error(
                property_name, location, 'apartments.com',
                error="Bright Data token required (set BRIGHTDATA_TOKEN env var)"
            )
        
        return await scrape_apartments(
            property_name, location, self.serpapi, self.brightdata
        )
    
    async def scrape_property_website(
        self,
        property_name: str,
        location: str,
        org_name: Optional[str] = None,
        url_only: bool = False,
    ) -> ScrapeResult:
        """
        Scrape property's official website for phone.
        
        Args:
            property_name: Name of the apartment property
            location: City, State or full address
            org_name: Optional management company name for better search
            url_only: If True, return after finding URL (skip phone extraction)
            
        Returns:
            ScrapeResult with phone if found on property website
        """
        if not self.serpapi:
            return ScrapeResult.create_error(
                property_name, location, 'property_website',
                error="SerpAPI key required (set SERPAPI_KEY env var)"
            )
        
        return await scrape_property_website(
            property_name, location,
            serpapi_client=self.serpapi,
            gpt_client=self.openai,
            http_client=self.http,
            org_name=org_name,
            url_only=url_only,
        )
    
    async def scrape_all(
        self,
        property_name: str,
        location: str,
        sources: Optional[list[str]] = None,
        org_name: Optional[str] = None,
    ) -> list[ScrapeResult]:
        """
        Scrape phone from multiple sources.
        
        Args:
            property_name: Name of the property
            location: City, State or full address
            sources: List of sources to scrape (default: all)
            org_name: Optional org name for property website search
            
        Returns:
            List of ScrapeResult objects, one per source
        """
        if sources is None:
            sources = ['google', 'apartments.com', 'property_website']
        
        results = []
        
        for source in sources:
            if source == 'google':
                result = await self.scrape_google(property_name, location)
            elif source == 'apartments.com':
                result = await self.scrape_apartments(property_name, location)
            elif source == 'property_website':
                result = await self.scrape_property_website(
                    property_name, location, org_name
                )
            else:
                result = ScrapeResult.create_error(
                    property_name, location, source,
                    error=f"Unknown source: {source}"
                )
            
            results.append(result)
        
        return results


# =============================================================================
# Convenience Functions
# =============================================================================

async def get_phone(
    property_name: str,
    location: str,
    sources: Optional[list[str]] = None,
    org_name: Optional[str] = None,
) -> Optional[str]:
    """
    Get phone number for a single property.
    
    Returns the first phone found from any source, or None.
    
    Example:
        phone = await get_phone("AZ Commons", "Tucson, AZ")
    """
    scraper = PropertyPhoneScraper()
    results = await scraper.scrape_all(property_name, location, sources, org_name)
    
    for result in results:
        if result.phone:
            return result.phone
    
    return None


async def get_phones(
    properties: list[dict],
    sources: Optional[list[str]] = None,
) -> list[dict]:
    """
    Get phone numbers for multiple properties.
    
    Example:
        results = await get_phones([
            {"name": "AZ Commons", "location": "Tucson, AZ"},
            {"name": "Casa Presidio", "location": "Tucson, AZ"},
        ])
    """
    scraper = PropertyPhoneScraper()
    all_results = []
    
    for prop in properties:
        name = prop.get("name") or prop.get("property_name")
        location = prop.get("location") or prop.get("address")
        org_name = prop.get("org_name")
        
        if not name or not location:
            all_results.append({
                "property_name": name,
                "location": location,
                "error": "Missing name or location"
            })
            continue
        
        results = await scraper.scrape_all(name, location, sources, org_name)
        all_results.extend([r.to_dict() for r in results])
    
    return all_results


def get_phone_sync(property_name: str, location: str, **kwargs) -> Optional[str]:
    """Synchronous wrapper for get_phone()."""
    return asyncio.run(get_phone(property_name, location, **kwargs))


def get_phones_sync(properties: list[dict], **kwargs) -> list[dict]:
    """Synchronous wrapper for get_phones()."""
    return asyncio.run(get_phones(properties, **kwargs))


# =============================================================================
# CLI
# =============================================================================

def _print_result(result: ScrapeResult) -> None:
    """Print a scrape result with formatting."""
    status_emoji = "✅" if result.phone else "❌"
    phone_display = result.phone or result.status
    verified = "✓" if result.verified else ""
    
    print(f"   {result.source}: {status_emoji} {phone_display} {verified}")
    
    if result.listing_url:
        print(f"      🔗 {result.listing_url}")
    if result.error:
        print(f"      ⚠️ {result.error}")


async def main():
    parser = argparse.ArgumentParser(
        description='Scrape property phone numbers',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scraper.py -p "AZ Commons" -l "Tucson, AZ"
  python scraper.py --csv properties.csv --sources google,property_website
  python scraper.py --csv properties.csv -o results.csv
        """
    )
    
    parser.add_argument('--property', '-p', help='Property name')
    parser.add_argument('--location', '-l', help='Property location')
    parser.add_argument('--csv', help='CSV file with properties')
    parser.add_argument('--output', '-o', help='Output CSV file')
    parser.add_argument(
        '--sources', '-s',
        default='google,apartments.com,property_website',
        help='Comma-separated sources to scrape'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Configure logging
    if args.verbose:
        logging.getLogger('scraper').setLevel(logging.DEBUG)
    
    sources = [s.strip() for s in args.sources.split(',')]
    scraper = PropertyPhoneScraper()
    
    if args.csv:
        # Batch mode from CSV
        with open(args.csv, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        all_results = []
        
        for i, row in enumerate(rows, 1):
            # Support multiple column naming conventions
            prop = (
                row.get('property_name') or row.get('name') or
                row.get('BUILDING_NAME') or row.get('building_name') or ''
            )
            loc = (
                row.get('location') or row.get('FULL_ADDRESS') or
                row.get('full_address') or row.get('address') or ''
            )
            org_name = row.get('org_name', '')
            
            if not prop or not loc:
                print(f"⚠️ Row {i}: Missing property name or location")
                continue
            
            print(f"\n🔍 {prop} ({loc})")
            
            for source in sources:
                if source == 'google':
                    result = await scraper.scrape_google(prop, loc)
                elif source == 'apartments.com':
                    result = await scraper.scrape_apartments(prop, loc)
                elif source == 'property_website':
                    result = await scraper.scrape_property_website(
                        prop, loc, org_name if org_name else None
                    )
                else:
                    continue
                
                all_results.append(result)
                _print_result(result)
        
        # Write output CSV
        if all_results:
            output_file = args.output or f"output/results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            
            fieldnames = [
                'property_name', 'location', 'source', 'phone',
                'verified', 'needs_review', 'review_reason',
                'listing_url', 'result_name', 'address',
                'status', 'warnings', 'error'
            ]
            
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                writer.writeheader()
                writer.writerows([r.to_dict() for r in all_results])
            
            print(f"\n✅ Results saved to {output_file}")
    
    elif args.property and args.location:
        # Single property mode
        print(f"\n🔍 {args.property} ({args.location})")
        
        for source in sources:
            if source == 'google':
                result = await scraper.scrape_google(args.property, args.location)
            elif source == 'apartments.com':
                result = await scraper.scrape_apartments(args.property, args.location)
            elif source == 'property_website':
                result = await scraper.scrape_property_website(
                    args.property, args.location
                )
            else:
                continue
            
            _print_result(result)
    
    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
