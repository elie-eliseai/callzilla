"""
Data models for the property phone scraper.

Centralizes the result structure so all scrapers return consistent data.
"""
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class ScrapeResult:
    """
    Standardized result from any scraping source.
    
    Use factory methods for common patterns:
        ScrapeResult.success(phone="(555) 123-4567", ...)
        ScrapeResult.not_found(property_name, location, source, reason="...")
        ScrapeResult.create_error(property_name, location, source, error="...")
    """
    property_name: str
    location: str
    source: str  # 'google', 'apartments.com', or 'property_website'
    
    # Core result
    phone: Optional[str] = None
    status: str = 'pending'  # 'found', 'not_found', 'not_advertising', 'url_found', 'pending'
    
    # Metadata about what was found
    result_name: Optional[str] = None  # Name returned by search/page
    address: Optional[str] = None
    listing_url: Optional[str] = None
    
    # Quality indicators
    verified: bool = False
    needs_review: bool = False
    review_reason: Optional[str] = None
    
    # Issues
    warnings: Optional[List[str]] = None
    error: Optional[str] = None
    
    # For property_website source: candidate domains found (useful for accuracy analysis)
    candidates: List[str] = field(default_factory=list)
    
    @classmethod
    def success(
        cls,
        property_name: str,
        location: str, 
        source: str,
        phone: str,
        listing_url: Optional[str] = None,
        result_name: Optional[str] = None,
        address: Optional[str] = None,
        candidates: Optional[List[str]] = None,
    ) -> 'ScrapeResult':
        """Create a successful result with a phone number."""
        return cls(
            property_name=property_name,
            location=location,
            source=source,
            phone=phone,
            status='found',
            verified=True,
            listing_url=listing_url,
            result_name=result_name,
            address=address,
            candidates=candidates or [],
        )
    
    @classmethod
    def not_found(
        cls,
        property_name: str,
        location: str,
        source: str,
        reason: Optional[str] = None,
        listing_url: Optional[str] = None,
        result_name: Optional[str] = None,
        candidates: Optional[List[str]] = None,
        needs_review: bool = False,
    ) -> 'ScrapeResult':
        """Create a not-found result."""
        return cls(
            property_name=property_name,
            location=location,
            source=source,
            status='not_found',
            listing_url=listing_url,
            result_name=result_name,
            needs_review=needs_review,
            review_reason=reason if needs_review else None,
            warnings=[reason] if reason else None,
            candidates=candidates or [],
        )
    
    @classmethod  
    def create_error(
        cls,
        property_name: str,
        location: str,
        source: str,
        error: str,
    ) -> 'ScrapeResult':
        """Create an error result."""
        return cls(
            property_name=property_name,
            location=location,
            source=source,
            status='error',
            error=error,
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for CSV output or JSON serialization."""
        return {
            'property_name': self.property_name,
            'location': self.location,
            'source': self.source,
            'phone': self.phone,
            'status': self.status,
            'result_name': self.result_name,
            'address': self.address,
            'listing_url': self.listing_url,
            'verified': self.verified,
            'needs_review': self.needs_review,
            'review_reason': self.review_reason,
            'warnings': self.warnings,
            'error': self.error,
            'candidates': self.candidates,
        }
    
    def with_review(self, reason: str) -> 'ScrapeResult':
        """Return a copy of this result flagged for review."""
        self.needs_review = True
        self.review_reason = reason
        return self
    
    def with_warnings(self, warnings: List[str]) -> 'ScrapeResult':
        """Return a copy of this result with warnings added."""
        self.warnings = (self.warnings or []) + warnings
        return self


@dataclass
class PhoneCandidate:
    """
    A phone number found on a webpage with contextual metadata.
    
    Simplified from the original 7-field structure to 3 essential fields
    that GPT actually needs to make a decision.
    """
    phone: str
    position: str  # 'header', 'main', 'footer', 'unknown'
    is_tel_link: bool  # True if found in <a href="tel:...">
    nearby_labels: List[str] = field(default_factory=list)  # e.g., ['contact', 'phone']
    nearby_text: str = ''  # Text context around the phone (for GPT)
    
    def has_positive_label(self) -> bool:
        """Check if any positive labels are nearby."""
        from scraper_config import POSITIVE_PHONE_LABELS
        return any(label in self.nearby_labels for label in POSITIVE_PHONE_LABELS)
    
    def has_negative_label(self) -> bool:
        """Check if any negative labels are nearby."""
        from scraper_config import NEGATIVE_PHONE_LABELS
        return any(label in self.nearby_labels for label in NEGATIVE_PHONE_LABELS)


@dataclass  
class WebsiteCandidate:
    """A candidate website URL from search results."""
    url: str
    domain: str
    title: str
    snippet: str = ''

