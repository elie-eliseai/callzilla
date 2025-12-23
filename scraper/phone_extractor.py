"""
Phone extraction from HTML pages.

This module handles finding and selecting phone numbers from property websites.
Extracted as a separate module for:
1. Independent testing
2. Potential reuse in other scrapers
3. Clearer separation of concerns

Usage:
    from phone_extractor import extract_phones_from_html, pick_primary_phone
    
    candidates = extract_phones_from_html(html)
    phone, needs_review = pick_primary_phone(candidates, "Property Name", "City, ST", gpt_client)
"""
import logging
import re
from typing import Optional

from bs4 import BeautifulSoup

from .scraper_config import POSITIVE_PHONE_LABELS, NEGATIVE_PHONE_LABELS
from .models import PhoneCandidate
from .clients import OpenAIClient

logger = logging.getLogger('scraper.phone_extractor')


# =============================================================================
# Phone Extraction
# =============================================================================

def extract_phones_from_html(html: str) -> list[PhoneCandidate]:
    """
    Extract all phone numbers from HTML with contextual metadata.
    
    Extracts phones from:
    1. tel: links (<a href="tel:...">) - most reliable
    2. Formatted text patterns like (555) 123-4567
    
    For each phone, captures:
    - position: 'header', 'main', 'footer', or 'unknown'
    - is_tel_link: whether it was in a tel: link
    - nearby_labels: context words like 'contact', 'leasing', 'fax'
    - nearby_text: surrounding text for GPT context
    
    Args:
        html: Raw HTML content
        
    Returns:
        List of PhoneCandidate objects, deduplicated by digits
    """
    soup = BeautifulSoup(html, 'lxml')
    seen_digits = set()
    candidates = []
    
    # Method 1: Find tel: links (most reliable source)
    for tel_link in soup.find_all('a', href=re.compile(r'^tel:')):
        phone_num = tel_link.get('href', '').replace('tel:', '').strip()
        digits = re.sub(r'\D', '', phone_num)
        
        if len(digits) < 10 or digits in seen_digits:
            continue
        seen_digits.add(digits)
        
        candidates.append(_build_phone_candidate(
            phone=phone_num,
            element=tel_link,
            soup=soup,
            html=html,
            is_tel_link=True,
        ))
    
    # Method 2: Find formatted phones in text
    phone_pattern = re.compile(r'\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}')
    
    for elem in soup.find_all(True):
        # Get direct text only (not from children, to avoid duplicates)
        direct_text = ''.join(elem.find_all(string=True, recursive=False))
        match = phone_pattern.search(direct_text)
        
        if not match:
            continue
            
        phone_num = match.group()
        digits = re.sub(r'\D', '', phone_num)
        
        # Skip if: too short, already seen, or not properly formatted
        if len(digits) < 10 or digits in seen_digits:
            continue
        if not any(c in phone_num for c in ['-', '.', ' ', '(']):
            continue  # Reject unformatted digit strings
            
        seen_digits.add(digits)
        
        candidates.append(_build_phone_candidate(
            phone=phone_num,
            element=elem,
            soup=soup,
            html=html,
            is_tel_link=False,
        ))
    
    return candidates


def _build_phone_candidate(
    phone: str,
    element,
    soup,
    html: str,
    is_tel_link: bool,
) -> PhoneCandidate:
    """Build a PhoneCandidate with contextual metadata."""
    position = _get_element_position(element, html)
    nearby_text = _get_nearby_text(element)
    labels = _find_labels(nearby_text, element)
    
    return PhoneCandidate(
        phone=phone,
        position=position,
        is_tel_link=is_tel_link,
        nearby_labels=labels,
        nearby_text=nearby_text[:150],
    )


def _get_element_position(element, html: str) -> str:
    """
    Determine element's position in the page structure.
    
    Returns: 'header', 'main', 'footer', or 'unknown'
    
    Strategy:
    1. Walk up the DOM looking for semantic elements (header, main, footer)
    2. Check class names for common patterns
    3. Fall back to estimating from position in HTML string
    """
    current = element
    for _ in range(10):  # Walk up max 10 levels
        if not current or not hasattr(current, 'name'):
            break
            
        name = current.name
        classes = current.get('class', []) if hasattr(current, 'get') else []
        classes_str = ' '.join(classes) if isinstance(classes, list) else str(classes)
        
        # Check semantic HTML5 elements and common class patterns
        if name in ['header', 'nav'] or 'header' in classes_str or 'hero' in classes_str:
            return 'header'
        if name == 'main':
            return 'main'
        if name == 'footer' or 'footer' in classes_str:
            return 'footer'
        if 'contact' in classes_str:
            return 'main'  # Contact sections are primary content
            
        current = current.parent if hasattr(current, 'parent') else None
    
    # Fallback: estimate from position in HTML
    try:
        element_str = str(element)[:100]
        pos = html.find(element_str)
        if pos != -1:
            pct = pos / len(html)
            if pct < 0.25:
                return 'header'
            elif pct > 0.75:
                return 'footer'
            else:
                return 'main'
    except Exception:
        pass
    
    return 'unknown'


def _get_nearby_text(element) -> str:
    """
    Get text near an element for context.
    
    Tries parent first, then grandparent if parent text is too short.
    """
    try:
        parent = element.parent
        if parent:
            text = parent.get_text(separator=' ', strip=True)[:200]
            if len(text) < 50 and parent.parent:
                text = parent.parent.get_text(separator=' ', strip=True)[:200]
            return text
    except Exception:
        pass
    return ''


def _find_labels(nearby_text: str, element) -> list[str]:
    """
    Find contextual labels near a phone number.
    
    Checks nearby text and element class names for:
    - Positive labels: 'contact', 'phone', 'leasing', etc.
    - Negative labels: 'fax', 'emergency', 'maintenance', etc. (prefixed with !)
    
    Returns:
        List of matched labels, negative ones prefixed with '!'
    """
    # Combine nearby text with element's class names
    classes = element.get('class', []) if hasattr(element, 'get') else []
    classes_str = ' '.join(classes) if isinstance(classes, list) else ''
    
    text_to_check = (nearby_text + ' ' + classes_str).lower()
    
    labels = []
    for label in POSITIVE_PHONE_LABELS:
        if label in text_to_check:
            labels.append(label)
    for label in NEGATIVE_PHONE_LABELS:
        if label in text_to_check:
            labels.append(f"!{label}")  # Prefix negative with !
    
    return labels


# =============================================================================
# Phone Selection (GPT)
# =============================================================================

def build_phone_pick_prompt(
    candidates: list[PhoneCandidate],
    property_name: str,
    location: str,
) -> str:
    """
    Build GPT prompt for selecting the primary leasing phone.
    
    Formats up to 8 phone candidates with their context for GPT to evaluate.
    """
    phones_text = []
    for i, p in enumerate(candidates[:8], 1):
        labels_str = ', '.join(p.nearby_labels) if p.nearby_labels else 'none'
        source = 'tel: link' if p.is_tel_link else 'text'
        
        phones_text.append(f"""PHONE #{i}: {p.phone}
├── Position: {p.position}
├── Source: {source}
├── Labels nearby: {labels_str}
└── Context: {p.nearby_text[:100]}...""")
    
    return f"""I found these phone numbers on an apartment property website. Pick the PRIMARY LEASING phone.

Property: {property_name}
Location: {location}

{chr(10).join(phones_text)}

DECISION GUIDE:
- "contact" or "leasing" label nearby = primary phone
- Position "header" or "main" > "footer"
- tel: links are usually primary numbers
- IGNORE: fax, emergency, tty, maintenance, corporate (marked with !)

Respond with ONLY the phone number in format: (XXX) XXX-XXXX
Or respond: NOT_FOUND if none look like a main leasing number."""


def pick_primary_phone(
    candidates: list[PhoneCandidate],
    property_name: str,
    location: str,
    gpt_client: Optional[OpenAIClient],
) -> tuple[Optional[str], bool]:
    """
    Pick the primary leasing phone from candidates.
    
    Uses GPT to select among multiple candidates. Falls back to first
    candidate if GPT is unavailable or uncertain.
    
    Args:
        candidates: Phone candidates extracted from HTML
        property_name: Property name for GPT context
        location: Location for GPT context
        gpt_client: OpenAI client (or None to use first candidate)
        
    Returns:
        Tuple of (phone_string or None, needs_review: bool)
    """
    if not candidates:
        return None, False
    
    # Single candidate - no need for GPT
    if len(candidates) == 1:
        return candidates[0].phone, False
    
    # No GPT client - use first candidate
    if not gpt_client:
        logger.warning("No OpenAI client - using first phone")
        return candidates[0].phone, True
    
    # Multiple candidates - ask GPT to pick
    prompt = build_phone_pick_prompt(candidates, property_name, location)
    gpt_phone = gpt_client.pick_phone(prompt)
    
    if gpt_phone and 'NOT_FOUND' not in gpt_phone.upper():
        digits = re.sub(r'\D', '', gpt_phone)
        if len(digits) >= 10:
            return gpt_phone, False
    
    # GPT couldn't decide - fallback to first candidate
    logger.warning("GPT couldn't pick phone - using first")
    return candidates[0].phone, True

