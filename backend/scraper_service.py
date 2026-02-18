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
            
            # Check if login successful - multiple indicators:
            # 1. Search form is visible
            # 2. Product listings are visible  
            # 3. NOT on login page anymore
            success_indicators = [
                await self.page.locator("input[placeholder*='Medidas'], input[name*='medida']").count() > 0,
                await self.page.locator("text=MICHELIN, text=CONTINENTAL, text=BRIDGESTONE").count() > 0,
                await self.page.locator("text=UTILIZADOR").count() == 0,  # Login form gone
            ]
            
            success = any(success_indicators)
            
            await self.take_screenshot("after_login")
            
            if success:
                logger.info("Login successful - authenticated page detected")
                return True, "Login successful"
            else:
                logger.warning(f"Login unclear - indicators: {success_indicators}")
                # Even if unclear, try to continue - might be logged in
                return True, "Login completed (verification unclear)"
                
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
            medida_normalized = self.normalize_medida(medida)
            indice_normalized = self.normalize_indice(indice)
            
            logger.info(f"Searching: {medida} → {medida_normalized} | {marca} | {modelo} | {indice} → {indice_normalized}")
            
            await asyncio.sleep(1)
            
            # Find and fill search input (Medidas field)
            medida_input = self.page.locator('input[type="text"], input[placeholder*="Medida"]').first
            await medida_input.clear()
            await medida_input.fill(medida_normalized)
            logger.info(f"Filled search with: {medida_normalized}")
            await asyncio.sleep(0.5)
            
            # Select marca (brand) if dropdown exists
            marca_select = self.page.locator('select').first
            if await marca_select.count() > 0:
                try:
                    # Try exact match first
                    await marca_select.select_option(label=marca)
                    logger.info(f"Selected brand: {marca}")
                except:
                    # Try partial match
                    try:
                        options = await marca_select.locator('option').all_text_contents()
                        for option in options:
                            if marca.lower() in option.lower():
                                await marca_select.select_option(label=option)
                                logger.info(f"Selected brand (partial): {option}")
                                break
                    except:
                        logger.warning(f"Could not select brand: {marca}")
            
            await asyncio.sleep(0.5)
            
            # Click search button
            search_button = self.page.locator('text=PESQUISAR, button:has-text("PESQUISAR"), input[value*="Pesqui"]').first
            if await search_button.count() > 0:
                await search_button.click()
                logger.info("Clicked PESQUISAR")
            else:
                # Fallback: press Enter
                await medida_input.press("Enter")
                logger.info("Pressed Enter to search")
            
            # Wait for results to load
            await asyncio.sleep(3)
            await self.page.wait_for_load_state("domcontentloaded", timeout=10000)
            
            await self.take_screenshot(f"search_results_{medida_normalized}")
            
            # Get page content
            content = await self.page.content()
            
            # Check for "no results"
            if any(text in content.lower() for text in ["sem resultado", "nenhum registo", "não foram encontrados"]):
                logger.info(f"No results found for {medida_normalized}")
                return None
            
            # Extract prices using multiple patterns
            # Pattern 1: XX,XX€ (comma as decimal separator, common in PT)
            # Pattern 2: €XX,XX
            # Pattern 3: Price in text/spans
            
            import re
            
            price_patterns = [
                r'(\d+[,\.]\d{2})\s*€',  # 77,85€ or 77.85€
                r'€\s*(\d+[,\.]\d{2})',  # €77,85
                r'(\d+[,\.]\d{2})€',     # 77,85€
            ]
            
            found_prices = []
            for pattern in price_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    try:
                        # Normalize: replace comma with dot
                        price_str = match.replace(',', '.')
                        price = float(price_str)
                        # Reasonable tire price range: 10-1000 euros
                        if 10 < price < 1000:
                            found_prices.append(price)
                    except ValueError:
                        continue
            
            if found_prices:
                # Return the lowest price found (best deal)
                best_price = min(found_prices)
                logger.info(f"Found {len(found_prices)} prices, lowest: €{best_price}")
                return best_price
            
            logger.warning(f"No valid prices found in results for {medida_normalized}")
            return None
            
        except Exception as e:
            logger.error(f"Search error for {medida}: {str(e)}")
            await self.take_screenshot(f"search_error_{self.normalize_medida(medida)}")
            return None

class EuromaisAdapter(ScraperBase):
    """Adapter for Euromais/Eurotyre B2B website"""
    
    def normalize_medida(self, medida: str) -> str:
        """Normalize medida format: remove / and R"""
        return medida.replace('/', '').replace('R', '').replace('r', '')
    
    def normalize_indice(self, indice: str) -> str:
        """Normalize indice: remove XL"""
        return indice.replace(' XL', '').replace('XL', '').strip()
    
    async def login(self) -> tuple[bool, str]:
        """Login to Euromais"""
        try:
            logger.info(f"Navigating to {self.url_login}")
            await self.page.goto(self.url_login, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(3)
            
            # Check if already logged in
            already_logged_in = await self.page.locator("text=Sair, text=Logout, text=Pesquisar").count() > 0
            if already_logged_in:
                logger.info("Already logged in to Euromais")
                return True, "Already logged in"
            
            # Fill username/email
            username_inputs = self.page.locator('input[type="text"], input[type="email"], input[name*="user"], input[name*="email"]')
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
            
            # Click LOGIN button
            login_button = self.page.locator('text=LOGIN, button:has-text("LOGIN"), input[value*="Login"], button[type="submit"]').first
            if await login_button.count() > 0:
                await login_button.click()
                logger.info("Clicked LOGIN button")
            else:
                await self.page.keyboard.press("Enter")
                logger.info("Pressed Enter to login")
            
            await asyncio.sleep(4)
            await self.page.wait_for_load_state("domcontentloaded", timeout=10000)
            
            # Check login success
            success_indicators = [
                await self.page.locator("text=Sair, text=Logout").count() > 0,
                await self.page.locator("input[placeholder*='Pesquis'], input[name*='search']").count() > 0,
                "login" not in self.page.url.lower(),
            ]
            
            success = any(success_indicators)
            await self.take_screenshot("after_login")
            
            if success:
                logger.info("Login successful to Euromais")
                return True, "Login successful"
            else:
                logger.warning("Login verification unclear")
                return True, "Login completed (verification unclear)"
                
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            await self.take_screenshot("login_error")
            return False, f"Login error: {str(e)}"
    
    async def search_product(self, medida: str, marca: str, modelo: str, indice: str) -> Optional[float]:
        """Search for tire on Euromais"""
        try:
            medida_normalized = self.normalize_medida(medida)
            indice_normalized = self.normalize_indice(indice)
            
            logger.info(f"Searching Euromais: {medida} → {medida_normalized} | {marca}")
            
            await asyncio.sleep(1)
            
            # Find search input
            search_input = self.page.locator('input[type="text"], input[type="search"], input[placeholder*="Pesquis"]').first
            await search_input.clear()
            await search_input.fill(medida_normalized)
            logger.info(f"Filled search: {medida_normalized}")
            await asyncio.sleep(0.5)
            
            # Submit search
            search_button = self.page.locator('button[type="submit"], button:has-text("Pesquisar"), input[type="submit"]').first
            if await search_button.count() > 0:
                await search_button.click()
            else:
                await search_input.press("Enter")
            
            await asyncio.sleep(3)
            await self.page.wait_for_load_state("domcontentloaded", timeout=10000)
            
            await self.take_screenshot(f"search_results_{medida_normalized}")
            
            content = await self.page.content()
            
            # Check for no results
            if any(text in content.lower() for text in ["sem resultado", "não encontrado", "nenhum produto"]):
                logger.info(f"No results for {medida_normalized}")
                return None
            
            # Extract prices - PT format (XX,XX€)
            import re
            price_patterns = [
                r'(\d+[,\.]\d{2})\s*€',
                r'€\s*(\d+[,\.]\d{2})',
                r'price["\']?\s*:\s*["\']?(\d+[,\.]\d{2})',
            ]
            
            found_prices = []
            for pattern in price_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    try:
                        price_str = match.replace(',', '.')
                        price = float(price_str)
                        if 10 < price < 1000:
                            found_prices.append(price)
                    except ValueError:
                        continue
            
            if found_prices:
                best_price = min(found_prices)
                logger.info(f"Found {len(found_prices)} prices, lowest: €{best_price}")
                return best_price
            
            logger.warning(f"No valid prices found for {medida_normalized}")
            return None
            
        except Exception as e:
            logger.error(f"Search error: {str(e)}")
            await self.take_screenshot(f"search_error_{self.normalize_medida(medida)}")
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
        
        # Create new adapter based on supplier name/URL
        supplier_name_lower = supplier['name'].lower()
        supplier_url_lower = supplier.get('url_login', '').lower()
        
        if 'jose' in supplier_name_lower or 'sjose' in supplier_name_lower:
            adapter = SJoseAdapter(
                supplier_id=supplier_id,
                supplier_name=supplier['name'],
                url_login=supplier['url_login'],
                url_search=supplier['url_search'],
                username=supplier['username'],
                password=supplier['password'],
                selectors=supplier.get('selectors')
            )
        elif 'euromais' in supplier_name_lower or 'eurotyre' in supplier_name_lower or 'eurotyre.pt' in supplier_url_lower:
            adapter = EuromaisAdapter(
                supplier_id=supplier_id,
                supplier_name=supplier['name'],
                url_login=supplier['url_login'],
                url_search=supplier['url_search'],
                username=supplier['username'],
                password=supplier['password'],
                selectors=supplier.get('selectors')
            )
        else:
            # Default to generic adapter (using SJoseAdapter as base for now)
            logger.warning(f"No specific adapter for {supplier['name']}, using generic adapter")
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
            # Default to generic adapter (using SJoseAdapter as base for now)
            logger.warning(f"No specific adapter for {supplier['name']}, using generic adapter")
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
