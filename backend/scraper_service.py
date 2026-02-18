import asyncio
import re
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from playwright.async_api import async_playwright, Browser, Page, TimeoutError as PlaywrightTimeout
import logging
from datetime import datetime
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Create screenshots directory
SCREENSHOTS_DIR = Path("/app/backend/screenshots")
SCREENSHOTS_DIR.mkdir(exist_ok=True)

class ScraperBase(ABC):
    """Base class for supplier-specific scrapers"""
    
    def __init__(self, supplier_id: str, supplier_name: str, url_login: str, url_search: str, 
                 username: str, password: str, selectors: Optional[Dict[str, str]] = None):
        self.supplier_id = supplier_id
        self.supplier_name = supplier_name
        self.url_login = url_login
        self.url_search = url_search
        self.username = username
        self.password = password
        self.selectors = selectors or {}
        self.page: Optional[Page] = None
        self.browser: Optional[Browser] = None
        
    async def init_browser(self):
        """Initialize browser and page"""
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        )
        self.page = await self.browser.new_page()
        self.page.set_default_timeout(30000)  # 30s timeout
        
    async def close_browser(self):
        """Close browser"""
        if self.browser:
            await self.browser.close()
            
    async def take_screenshot(self, name: str) -> str:
        """Take screenshot and return path"""
        if not self.page:
            return ""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.supplier_name}_{name}_{timestamp}.png"
        filepath = SCREENSHOTS_DIR / filename
        await self.page.screenshot(path=str(filepath))
        return str(filepath)
    
    @abstractmethod
    async def login(self) -> tuple[bool, str]:
        """Login to supplier website. Returns (success, message)"""
        pass
    
    @abstractmethod
    async def search_product(self, medida: str, marca: str, modelo: str, indice: str) -> Optional[float]:
        """Search for product and return price. Returns None if not found."""
        pass
    
    async def test_login(self) -> tuple[bool, str, Optional[str]]:
        """Test login and return (success, message, screenshot_path)"""
        try:
            await self.init_browser()
            success, message = await self.login()
            screenshot = await self.take_screenshot("test_login")
            await self.close_browser()
            return success, message, screenshot
        except Exception as e:
            logger.error(f"Test login error for {self.supplier_name}: {str(e)}")
            screenshot = await self.take_screenshot("test_login_error") if self.page else None
            await self.close_browser()
            return False, f"Error: {str(e)}", screenshot

class SJoseAdapter(ScraperBase):
    """Adapter for S. José B2B website"""
    
    async def login(self) -> tuple[bool, str]:
        """Login to S. José"""
        try:
            logger.info(f"Navigating to {self.url_login}")
            await self.page.goto(self.url_login, wait_until="networkidle")
            
            # Wait for page to load
            await asyncio.sleep(2)
            
            # Check if already logged in (look for logout or user info)
            logged_in = await self.page.locator("text=Bem vinda").count() > 0
            if logged_in:
                logger.info("Already logged in to S. José")
                return True, "Already logged in"
            
            # Find login form - try multiple strategies
            # Strategy 1: Look for username input by type="text" or id/name containing "user"
            username_input = self.page.locator('input[type="text"]').first
            if await username_input.count() > 0:
                await username_input.fill(self.username)
                logger.info("Filled username")
            
            # Strategy 2: Look for password input
            password_input = self.page.locator('input[type="password"]').first
            if await password_input.count() > 0:
                await password_input.fill(self.password)
                logger.info("Filled password")
            
            # Take screenshot before submit
            await self.take_screenshot("before_login")
            
            # Click login button - try multiple strategies
            login_button = self.page.locator('input[type="submit"], button[type="submit"]').first
            if await login_button.count() > 0:
                await login_button.click()
                logger.info("Clicked login button")
            
            # Wait for navigation
            await asyncio.sleep(3)
            
            # Check if login successful
            success = await self.page.locator("text=Bem vinda").count() > 0 or "PESQUISA" in await self.page.content()
            
            if success:
                logger.info("Login successful")
                return True, "Login successful"
            else:
                await self.take_screenshot("login_failed")
                return False, "Login failed - no success indicator found"
                
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            await self.take_screenshot("login_error")
            return False, f"Login error: {str(e)}"
    
    async def search_product(self, medida: str, marca: str, modelo: str, indice: str) -> Optional[float]:
        """Search for tire on S. José and return price"""
        try:
            # Navigate to search page if needed
            if "default.aspx" not in self.page.url:
                await self.page.goto(self.url_login, wait_until="networkidle")
                await asyncio.sleep(1)
            
            # Fill search form
            # Medidas field
            medida_input = self.page.locator('input[type="text"]').first
            await medida_input.fill(medida)
            logger.info(f"Searching for: {medida} {marca} {modelo} {indice}")
            
            # Select marca if dropdown exists
            marca_select = self.page.locator('select').first
            if await marca_select.count() > 0:
                # Try to select the brand
                try:
                    await marca_select.select_option(label=marca)
                except:
                    # If exact match fails, try contains
                    options = await marca_select.locator('option').all_text_contents()
                    for option in options:
                        if marca.lower() in option.lower():
                            await marca_select.select_option(label=option)
                            break
            
            # Click search button
            search_button = self.page.locator('text=PESQUISAR').or_(self.page.locator('input[value*="Pesqui"]'))
            await search_button.first.click()
            
            # Wait for results
            await asyncio.sleep(2)
            await self.page.wait_for_load_state("networkidle")
            
            # Parse results - look for price in results table/grid
            # S. José typically shows results in a grid/table format
            # Look for price patterns: €XX.XX or XX,XX€
            
            content = await self.page.content()
            
            # Check if "sem resultados" or "no results"
            if "sem resultado" in content.lower() or "nenhum registo" in content.lower():
                logger.info("No results found")
                return None
            
            # Extract prices - look for price patterns
            price_patterns = [
                r'(\d+[,.]\d{2})\s*€',  # 123.45€ or 123,45€
                r'€\s*(\d+[,.]\d{2})',  # €123.45
                r'Preço.*?(\d+[,.]\d{2})',  # Preço: 123.45
            ]
            
            prices = []
            for pattern in price_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    try:
                        # Normalize price (replace comma with dot)
                        price_str = match.replace(',', '.')
                        price = float(price_str)
                        if 10 < price < 1000:  # Reasonable tire price range
                            prices.append(price)
                    except ValueError:
                        continue
            
            if prices:
                # Return the first/lowest price found
                best_price = min(prices)
                logger.info(f"Found price: €{best_price}")
                return best_price
            
            logger.info("No valid price found in results")
            await self.take_screenshot(f"no_price_{medida.replace('/', '_')}")
            return None
            
        except Exception as e:
            logger.error(f"Search error for {medida}: {str(e)}")
            await self.take_screenshot(f"search_error_{medida.replace('/', '_')}")
            return None

class ScraperService:
    """Main scraper service that orchestrates scraping jobs"""
    
    def __init__(self):
        self.adapters: Dict[str, ScraperBase] = {}
    
    def get_adapter(self, supplier: Dict[str, Any]) -> ScraperBase:
        """Get or create adapter for supplier"""
        supplier_id = supplier['id']
        
        # Return existing adapter if available
        if supplier_id in self.adapters:
            return self.adapters[supplier_id]
        
        # Create new adapter based on supplier name/type
        # For now, we'll use SJoseAdapter for S. José and can add more adapters later
        if 'jose' in supplier['name'].lower() or 'sjose' in supplier['name'].lower():
            adapter = SJoseAdapter(
                supplier_id=supplier_id,
                supplier_name=supplier['name'],
                url_login=supplier['url_login'],
                url_search=supplier['url_search'],
                username=supplier['username'],
                password=supplier['password'],
                selectors=supplier.get('selectors')
            )
        else:
            # Default to SJoseAdapter structure - can be customized per supplier
            adapter = SJoseAdapter(
                supplier_id=supplier_id,
                supplier_name=supplier['name'],
                url_login=supplier['url_login'],
                url_search=supplier['url_search'],
                username=supplier['username'],
                password=supplier['password'],
                selectors=supplier.get('selectors')
            )
        
        self.adapters[supplier_id] = adapter
        return adapter
    
    async def test_supplier_login(self, supplier: Dict[str, Any]) -> tuple[bool, str, Optional[str]]:
        """Test login for a supplier"""
        adapter = self.get_adapter(supplier)
        return await adapter.test_login()
    
    async def scrape_product(self, supplier: Dict[str, Any], medida: str, marca: str, 
                            modelo: str, indice: str) -> Optional[float]:
        """Scrape single product from supplier"""
        adapter = self.get_adapter(supplier)
        
        # Initialize browser if not already done
        if not adapter.page:
            await adapter.init_browser()
            # Login first
            success, message = await adapter.login()
            if not success:
                logger.error(f"Login failed for {supplier['name']}: {message}")
                return None
        
        # Search product with retry logic
        max_retries = 2
        for attempt in range(max_retries):
            try:
                price = await adapter.search_product(medida, marca, modelo, indice)
                if price is not None:
                    return price
                # If not found but no error, return None (not found)
                if attempt == max_retries - 1:
                    return None
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed: {str(e)}")
                if attempt == max_retries - 1:
                    return None
                await asyncio.sleep(1)  # Wait before retry
        
        return None
    
    async def cleanup_supplier(self, supplier_id: str):
        """Close browser for supplier"""
        if supplier_id in self.adapters:
            await self.adapters[supplier_id].close_browser()
            del self.adapters[supplier_id]
