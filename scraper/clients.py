"""
API client wrappers for the property phone scraper.

Centralizes HTTP, SerpAPI, OpenAI, and Bright Data interactions so they're
created once and reused, rather than instantiated in every function.
"""
import logging
from typing import Optional, Any

import httpx

from .scraper_config import (
    Config,
    GPT_MODEL,
    GPT_MAX_TOKENS_URL_PICK,
    GPT_MAX_TOKENS_PHONE_PICK,
    HTTP_TIMEOUT,
    HTTP_TIMEOUT_EXTENDED,
    SEARCH_RESULT_COUNT,
)

logger = logging.getLogger('scraper.clients')


class SerpAPIClient:
    """
    Client for Google search via SerpAPI.
    
    Usage:
        client = SerpAPIClient(api_key)
        results = await client.search("property name location")
    """
    
    BASE_URL = "https://serpapi.com/search.json"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
    
    async def search(
        self,
        query: str,
        num_results: int = SEARCH_RESULT_COUNT,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> dict:
        """
        Search Google via SerpAPI.
        
        Args:
            query: Search query string
            num_results: Number of results to request (max 100)
            http_client: Optional httpx client (creates one if not provided)
            
        Returns:
            Full SerpAPI response dict
            
        Raises:
            httpx.HTTPStatusError: On non-200 response
        """
        params = {
            "q": query,
            "api_key": self.api_key,
            "num": num_results,
            "hl": "en",
            "gl": "us",
        }
        
        if http_client:
            response = await http_client.get(self.BASE_URL, params=params)
        else:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                response = await client.get(self.BASE_URL, params=params)
        
        response.raise_for_status()
        return response.json()
    
    def get_organic_results(self, response: dict) -> list[dict]:
        """Extract organic search results from SerpAPI response."""
        return response.get("organic_results", [])
    
    def get_knowledge_graph(self, response: dict) -> Optional[dict]:
        """Extract knowledge graph data from SerpAPI response."""
        return response.get("knowledge_graph")


class OpenAIClient:
    """
    Client for OpenAI GPT completions.
    
    Wraps the OpenAI SDK to provide simpler methods for our specific use cases:
    picking URLs and picking phone numbers.
    
    Usage:
        client = OpenAIClient(api_key)
        pick = client.pick_from_options(prompt, max_tokens=10)
    """
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client = None
    
    @property
    def client(self):
        """Lazy-load the OpenAI client."""
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key)
        return self._client
    
    def complete(
        self,
        prompt: str,
        max_tokens: int = GPT_MAX_TOKENS_PHONE_PICK,
        temperature: float = 0,
    ) -> Optional[str]:
        """
        Get a completion from GPT.
        
        Args:
            prompt: The prompt to send
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0 = deterministic)
            
        Returns:
            Response text, or None on error
        """
        try:
            response = self.client.chat.completions.create(
                model=GPT_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"OpenAI API error: {e}")
            return None
    
    def pick_url(self, prompt: str) -> Optional[str]:
        """Pick a URL from candidates. Returns the response (number or 'NONE')."""
        return self.complete(prompt, max_tokens=GPT_MAX_TOKENS_URL_PICK)
    
    def pick_phone(self, prompt: str) -> Optional[str]:
        """Pick a phone number. Returns the phone or 'NOT_FOUND'."""
        return self.complete(prompt, max_tokens=GPT_MAX_TOKENS_PHONE_PICK)


class HTTPClient:
    """
    HTTP client with Cloudflare bypass fallback via Crawlbase.
    
    Usage:
        client = HTTPClient(crawlbase_token="...")
        html, error = await client.fetch("https://example.com")
    """
    
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    
    def __init__(self, crawlbase_token: Optional[str] = None):
        self.crawlbase_token = crawlbase_token
    
    async def fetch(
        self,
        url: str,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Fetch a URL with Cloudflare detection and fallback.
        
        Args:
            url: URL to fetch
            http_client: Optional httpx client (creates one if not provided)
            
        Returns:
            Tuple of (html, error). One will be None.
            - On success: (html_content, None)
            - On Cloudflare without token: (partial_html, "Cloudflare protection")
            - On error: (None, error_message)
        """
        headers = {"User-Agent": self.DEFAULT_USER_AGENT}
        
        async def do_fetch(client: httpx.AsyncClient) -> tuple[Optional[str], Optional[str]]:
            try:
                response = await client.get(url, headers=headers, follow_redirects=True)
                html = response.text
                
                # Detect Cloudflare challenge
                if self._is_cloudflare_challenge(html):
                    return await self._fetch_via_crawlbase(url, client, html)
                
                return html, None
                
            except Exception as e:
                return None, f"Fetch failed: {str(e)}"
        
        if http_client:
            return await do_fetch(http_client)
        else:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                return await do_fetch(client)
    
    def _is_cloudflare_challenge(self, html: str) -> bool:
        """Check if response is a Cloudflare challenge page."""
        return 'Just a moment' in html or 'challenge-platform' in html
    
    async def _fetch_via_crawlbase(
        self,
        url: str,
        client: httpx.AsyncClient,
        original_html: str,
    ) -> tuple[Optional[str], Optional[str]]:
        """Fetch via Crawlbase to bypass Cloudflare."""
        if not self.crawlbase_token:
            return original_html, "Cloudflare protection - add CRAWLBASE_TOKEN"
        
        logger.info(f"Cloudflare detected, using Crawlbase for {url}")
        
        try:
            params = {
                "token": self.crawlbase_token,
                "url": url,
                "page_wait": 3000,
                "ajax_wait": "true",
            }
            response = await client.get(
                "https://api.crawlbase.com/",
                params=params,
                timeout=45,
            )
            
            if response.status_code == 200:
                return response.text, None
            else:
                return original_html, f"Crawlbase error: {response.status_code}"
                
        except Exception as e:
            return original_html, f"Crawlbase fetch failed: {str(e)}"


class BrightDataClient:
    """
    Client for Bright Data Web Unlocker API.
    
    Used for fetching Apartments.com pages that have anti-bot protection.
    
    Usage:
        client = BrightDataClient(token, zone="web_unlocker1")
        html, error = await client.fetch("https://apartments.com/...")
    """
    
    API_URL = "https://api.brightdata.com/request"
    
    def __init__(self, token: str, zone: str = "web_unlocker1"):
        self.token = token
        self.zone = zone
    
    async def fetch(
        self,
        url: str,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Fetch a URL via Bright Data Web Unlocker.
        
        Args:
            url: URL to fetch
            http_client: Optional httpx client
            
        Returns:
            Tuple of (html, error)
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        payload = {
            "zone": self.zone,
            "url": url,
            "format": "raw",
        }
        
        async def do_fetch(client: httpx.AsyncClient) -> tuple[Optional[str], Optional[str]]:
            try:
                response = await client.post(
                    self.API_URL,
                    headers=headers,
                    json=payload,
                )
                
                if response.status_code != 200:
                    return None, f"Bright Data error: {response.status_code}"
                
                html = response.text
                
                return html, None
                
            except Exception as e:
                return None, f"Bright Data fetch failed: {str(e)}"
        
        if http_client:
            return await do_fetch(http_client)
        else:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_EXTENDED) as client:
                return await do_fetch(client)


class ClientFactory:
    """
    Factory for creating all API clients from a Config.
    
    Usage:
        config = Config.from_env()
        factory = ClientFactory(config)
        
        serp = factory.serpapi()  # Returns SerpAPIClient or None
        gpt = factory.openai()    # Returns OpenAIClient or None
    """
    
    def __init__(self, config: Config):
        self.config = config
        self._serpapi: Optional[SerpAPIClient] = None
        self._openai: Optional[OpenAIClient] = None
        self._http: Optional[HTTPClient] = None
        self._brightdata: Optional[BrightDataClient] = None
    
    def serpapi(self) -> Optional[SerpAPIClient]:
        """Get SerpAPI client, or None if no API key configured."""
        if self._serpapi is None and self.config.serpapi_key:
            self._serpapi = SerpAPIClient(self.config.serpapi_key)
        return self._serpapi
    
    def openai(self) -> Optional[OpenAIClient]:
        """Get OpenAI client, or None if no API key configured."""
        if self._openai is None and self.config.openai_key:
            self._openai = OpenAIClient(self.config.openai_key)
        return self._openai
    
    def http(self) -> HTTPClient:
        """Get HTTP client (always available, Crawlbase optional)."""
        if self._http is None:
            self._http = HTTPClient(self.config.crawlbase_token)
        return self._http
    
    def brightdata(self) -> Optional[BrightDataClient]:
        """Get Bright Data client, or None if no token configured."""
        if self._brightdata is None and self.config.brightdata_token:
            self._brightdata = BrightDataClient(
                self.config.brightdata_token,
                self.config.brightdata_zone,
            )
        return self._brightdata

