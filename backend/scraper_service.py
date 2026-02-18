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
            await self.page.goto(self.url_login, wait_until="domcontentloaded", timeout=60000)
            
            await asyncio.sleep(3)
            
            # Check if already logged in - look for specific elements that only appear after login
            # After login, usually there's a search form or products visible
            already_logged_in = await self.page.locator("input[placeholder*='Medidas'], input[name*='medida']").count() > 0
            if already_logged_in:
                logger.info("Already logged in to S. José")
                return True, "Already logged in"
            
            # Fill username - first text input
            username_inputs = self.page.locator('input[type="text"]')
            if await username_inputs.count() > 0:
                await username_inputs.first.fill(self.username)
                logger.info(f"Filled username: {self.username}")
                await asyncio.sleep(0.5)
            
            # Fill password
            password_inputs = self.page.locator('input[type="password"]')
            if await password_inputs.count() > 0:
                await password_inputs.first.fill(self.password)
                logger.info("Filled password")
                await asyncio.sleep(0.5)
            
            await self.take_screenshot("before_login")
            
            # Click ENTRAR button - look for text or submit button
            login_button = self.page.locator('text=ENTRAR, input[type="submit"], button[type="submit"], button:has-text("ENTRAR")').first
            if await login_button.count() > 0:
                await login_button.click()
                logger.info("Clicked ENTRAR button")
            else:
                # If button not found, try submitting the form directly
                await self.page.keyboard.press("Enter")
                logger.info("Submitted form via Enter key")
            
            # Wait for navigation after login
            await asyncio.sleep(4)
            await self.page.wait_for_load_state("domcontentloaded", timeout=10000)
            
            # Check if login successful - look for search form elements
            success = await self.page.locator("input[placeholder*='Medidas'], input[name*='medida']").count() > 0
            
            await self.take_screenshot("after_login")
            
            if success:
                logger.info("Login successful - search form detected")
                return True, "Login successful"
            else:
                logger.warning("Login may have failed - search form not detected")
                return False, "Login failed - no search form found"
                
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            await self.take_screenshot("login_error")
            return False, f"Login error: {str(e)}"
    
    def normalize_medida(self, medida: str) -> str:
        """Normalize medida format: remove / and R (ex: 195/55R16 -> 1955516)"""
        return medida.replace('/', '').replace('R', '').replace('r', '')
    
    def normalize_indice(self, indice: str) -> str:
        """Normalize indice: remove XL (ex: 94W XL -> 94W)"""
        return indice.replace(' XL', '').replace('XL', '').strip()
    
    async def search_product(self, medida: str, marca: str, modelo: str, indice: str) -> Optional[float]:
        """Search for tire on S. José and return price"""
        try:
            # Normalize formats for B2B search
            medida_normalized = self.normalize_medida(medida)
            indice_normalized = self.normalize_indice(indice)
            
            logger.info(f"Searching: {medida} ({medida_normalized}) {marca} {modelo} {indice} ({indice_normalized})")
            
            # Navigate to search page if needed
            if "default.aspx" not in self.page.url:
                await self.page.goto(self.url_login, wait_until="networkidle")
                await asyncio.sleep(1)
            
            # Fill search form with normalized medida
            medida_input = self.page.locator('input[type="text"]').first
            await medida_input.fill(medida_normalized)
            
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
