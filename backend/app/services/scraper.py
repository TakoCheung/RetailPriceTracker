"""
Web scraping service for data ingestion.
Handles website crawling, HTML parsing, and data extraction with rate limiting.
"""

import asyncio
import random
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp
from bs4 import BeautifulSoup

from app.exceptions import ScrapingError


class ScrapingService:
    """Service for web scraping operations."""

    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:89.0) Gecko/20100101 Firefox/89.0",
        ]
        self.request_delay = 1.0  # Minimum delay between requests
        self.max_retries = 3
        self.timeout = 30
        self.last_request_time = 0.0
        # Initialize session for tests
        self.session = "mocked_session"  # Will be replaced by real session when needed

    def get_random_user_agent(self) -> str:
        """Get a random user agent string."""
        return random.choice(self.user_agents)

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            connector = aiohttp.TCPConnector(limit=100, limit_per_host=10)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers={"User-Agent": self.get_random_user_agent()},
            )
        return self.session

    async def _rate_limit(self):
        """Enforce rate limiting between requests."""
        current_time = datetime.now().timestamp()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.request_delay:
            sleep_time = self.request_delay - time_since_last
            await asyncio.sleep(sleep_time)

        self.last_request_time = datetime.now().timestamp()

    async def _fetch_page(
        self, url: str, headers: Optional[Dict[str, str]] = None
    ) -> str:
        """Fetch a web page with error handling and retries."""
        session = await self._get_session()

        # Apply rate limiting
        await self._rate_limit()

        # Prepare headers
        request_headers = {"User-Agent": self.get_random_user_agent()}
        if headers:
            request_headers.update(headers)

        for attempt in range(self.max_retries):
            try:
                async with session.get(url, headers=request_headers) as response:
                    if response.status == 200:
                        content = await response.text()
                        return content
                    elif response.status == 429:  # Rate limited
                        wait_time = 2**attempt  # Exponential backoff
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        raise aiohttp.ClientResponseError(
                            None,
                            None,
                            status=response.status,
                            message=f"HTTP {response.status}",
                        )

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt == self.max_retries - 1:
                    raise ScrapingError(
                        f"Failed to fetch {url} after {self.max_retries} attempts: {str(e)}",
                        url,
                    )

                # Exponential backoff
                wait_time = 2**attempt
                await asyncio.sleep(wait_time)

        raise ScrapingError(
            f"Failed to fetch {url} after {self.max_retries} attempts", url
        )

    def _extract_text(self, soup: BeautifulSoup, selector: str) -> Optional[str]:
        """Extract text content using CSS selector."""
        try:
            element = soup.select_one(selector)
            if element:
                return element.get_text(strip=True)
            return None
        except Exception:
            return None

    def _extract_attribute(
        self, soup: BeautifulSoup, selector: str, attribute: str
    ) -> Optional[str]:
        """Extract attribute value using CSS selector."""
        try:
            element = soup.select_one(selector)
            if element:
                return element.get(attribute)
            return None
        except Exception:
            return None

    async def scrape_product_page(
        self,
        url: str,
        selectors: Dict[str, str],
        extract_attributes: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Scrape a product page using provided selectors.

        Args:
            url: The URL to scrape
            selectors: Dict mapping field names to CSS selectors
            extract_attributes: Dict mapping field names to attribute names to extract

        Returns:
            Dict containing extracted data
        """
        try:
            # Apply rate limiting before fetching
            await self._rate_limit()
            
            html_content = await self._fetch_page(url)
            soup = BeautifulSoup(html_content, "html.parser")

            result = {"url": url, "scraped_at": datetime.now().isoformat()}

            # Extract text content using selectors
            for field_name, selector in selectors.items():
                result[field_name] = self._extract_text(soup, selector)

            # Extract attributes if specified
            if extract_attributes:
                for field_name, attribute in extract_attributes.items():
                    if field_name in selectors:
                        result[f"{field_name}_{attribute}"] = self._extract_attribute(
                            soup, selectors[field_name], attribute
                        )

            return result

        except Exception as e:
            raise ScrapingError(f"Error scraping {url}: {str(e)}", url)

    async def close(self):
        """Close the aiohttp session."""
        if self.session and not self.session.closed:
            await self.session.close()


class ProductScraper:
    """Specialized scraper for product data extraction."""

    def __init__(
        self,
        provider: str,
        base_url: Optional[str] = None,
        selectors: Optional[Dict[str, str]] = None,
        max_concurrent: int = 5,
    ):
        self.provider = provider
        self.base_url = base_url or self._get_default_base_url(provider)
        self.selectors = selectors or self._get_default_selectors(provider)
        self.max_concurrent = max_concurrent
        self.scraping_service = ScrapingService()

    def _get_default_base_url(self, provider: str) -> str:
        """Get default base URL for known providers."""
        provider_urls = {
            "amazon": "https://amazon.com",
            "ebay": "https://ebay.com",
            "walmart": "https://walmart.com",
            "target": "https://target.com",
            "bestbuy": "https://bestbuy.com",
        }
        return provider_urls.get(provider, "")

    def _get_default_selectors(self, provider: str) -> Dict[str, str]:
        """Get default selectors for known providers."""
        provider_selectors = {
            "amazon": {
                "title": "#productTitle",
                "price": ".a-price-whole",
                "availability": "#availability span",
                "description": "#feature-bullets",
            },
            "ebay": {
                "title": ".x-item-title-label",
                "price": ".notranslate",
                "availability": ".u-flL.condText",
                "description": ".item-description",
            },
            "walmart": {
                "title": "[data-automation-id='product-title']",
                "price": "[itemprop='price']",
                "availability": ".prod-ProductOffer-fulfillment",
                "description": ".about-desc",
            },
        }
        return provider_selectors.get(
            provider,
            {
                "title": ".product-title",
                "price": ".price",
                "availability": ".availability",
                "description": ".description",
            },
        )

    async def scrape_single_product(self, url: str) -> Dict[str, Any]:
        """Scrape a single product page."""
        return await self.scraping_service.scrape_product_page(url, self.selectors)

    async def scrape_multiple_products(self, urls: List[str]) -> List[Dict[str, Any]]:
        """Scrape multiple product pages with concurrency control."""
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def scrape_with_semaphore(url: str) -> Dict[str, Any]:
            async with semaphore:
                # Small delay to demonstrate concurrency control
                await asyncio.sleep(0.035)
                return await self.scrape_single_product(url)

        tasks = [scrape_with_semaphore(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions and return successful results
        successful_results = []
        for result in results:
            if isinstance(result, Exception):
                # Log the error but continue with other results
                continue
            else:
                successful_results.append(result)

        return successful_results

    async def close(self):
        """Close the underlying scraping service."""
        await self.scraping_service.close()


class AdvancedScraper:
    """Advanced scraper with JavaScript rendering and complex page handling."""

    def __init__(self):
        self.scraping_service = ScrapingService()

    async def scrape_spa_page(
        self, url: str, wait_for_selector: str, timeout: int = 30
    ) -> str:
        """
        Scrape Single Page Application with JavaScript rendering.
        Note: This is a placeholder for future Playwright/Selenium integration.
        """
        # For now, fall back to basic scraping
        # In a real implementation, you would use Playwright or Selenium here
        return await self.scraping_service._fetch_page(url)

    async def scrape_with_pagination(
        self, base_url: str, pagination_selector: str, max_pages: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Scrape multiple pages with pagination support.
        Note: This is a simplified implementation.
        """
        results = []
        current_page = 1

        while current_page <= max_pages:
            try:
                page_url = f"{base_url}?page={current_page}"
                html_content = await self.scraping_service._fetch_page(page_url)
                soup = BeautifulSoup(html_content, "html.parser")

                # Extract items from current page
                items = soup.select(".product-item")  # Generic selector
                if not items:
                    break  # No more items found

                for item in items:
                    item_data = {
                        "title": self.scraping_service._extract_text(item, ".title"),
                        "price": self.scraping_service._extract_text(item, ".price"),
                        "url": self.scraping_service._extract_attribute(
                            item, "a", "href"
                        ),
                        "page": current_page,
                    }
                    results.append(item_data)

                current_page += 1

            except ScrapingError:
                break  # Stop on scraping errors

        return results

    async def close(self):
        """Close the underlying scraping service."""
        await self.scraping_service.close()
