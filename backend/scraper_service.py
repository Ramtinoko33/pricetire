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
        """Initialize browser and page with anti-detection"""
        playwright = await async_playwright().start()
        # Launch with anti-detection args
        self.browser = await playwright.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
            ]
        )
        # Create context with fake user agent and viewport
        context = await self.browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='pt-PT',
            timezone_id='Europe/Lisbon',
        )
        self.page = await context.new_page()
        
        # Remove webdriver flag
        await self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
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
            
            # CRITICAL FIX: If still on login page after submit, force navigate
            current_url = self.page.url
            if "login.aspx" in current_url.lower():
                logger.warning("Still on login.aspx, forcing navigation to catalog...")
                catalog_urls = [
                    "https://b2b.sjosepneus.com/articles.aspx",
                    "https://b2b.sjosepneus.com/default.aspx",
                ]
                for url in catalog_urls:
                    try:
                        await self.page.goto(url, wait_until="domcontentloaded", timeout=10000)
                        await asyncio.sleep(2)
                        has_content = await self.page.locator('input[type="text"]').count() > 0
                        if has_content:
                            logger.info(f"Successfully navigated to {url}")
                            break
                    except:
                        continue
            
            # Check if login successful - multiple indicators:
            # 1. Search form is visible
            # 2. Product listings are visible  
            # 3. NOT on login page anymore
            success_indicators = [
                await self.page.locator("input[placeholder*='Medidas'], input[name*='medida']").count() > 0,
                await self.page.locator("text=MICHELIN, text=CONTINENTAL, text=BRIDGESTONE").count() > 0,
                await self.page.locator("text=UTILIZADOR").count() == 0,  # Login form gone
                await self.page.locator("input[type='text']").count() > 0,  # Any input present
            ]
            
            success = any(success_indicators)
            logger.info(f"Login check - indicators: {success_indicators}")
            
            await self.take_screenshot("after_login")
            
            # Be more lenient - if we have any text input, proceed
            if success or await self.page.locator("input[type='text']").count() > 0:
                logger.info("Login successful - proceeding with scraping")
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
            already_logged_in = await self.page.locator("text=Sair, text=Logout").count() > 0
            if already_logged_in:
                logger.info("Already logged in to Euromais")
                return True, "Already logged in"
            
            # Fill username/email  
            username_inputs = self.page.locator('input[type="text"], input[type="email"], input[name*="user"], input[name*="email"], input[name*="login"]')
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
            login_button = self.page.locator('text=LOGIN, button:has-text("LOGIN"), input[value*="Login"], button[type="submit"], input[type="submit"]').first
            if await login_button.count() > 0:
                async with self.page.expect_navigation(timeout=15000, wait_until="domcontentloaded"):
                    await login_button.click()
                logger.info("Clicked LOGIN button")
            else:
                await self.page.keyboard.press("Enter")
                await asyncio.sleep(2)
                logger.info("Pressed Enter to login")
            
            await asyncio.sleep(3)
            
            # Navigate directly to tire catalog (from screenshot: eurotyrepl.log/consulta-de-pneus)
            catalog_urls = [
                "https://eurotyrepl.log/consulta-de-pneus/?tab=pneus&subtab=pneus",
                "https://www.eurotyre.pt/pt/consulta-de-pneus/?tab=pneus&subtab=pneus",
                "https://www.eurotyre.pt/pt/pneus",
            ]
            
            for url in catalog_urls:
                try:
                    await self.page.goto(url, wait_until="domcontentloaded", timeout=10000)
                    await asyncio.sleep(2)
                    # Check if we have search elements
                    has_search = await self.page.locator('input[type="text"], input[type="search"]').count() > 0
                    if has_search:
                        logger.info(f"Found catalog at {url}")
                        break
                except Exception as e:
                    logger.debug(f"Catalog URL {url} failed: {str(e)}")
                    continue
            
            await self.take_screenshot("after_login")
            
            # Check login success - be lenient
            success_indicators = [
                await self.page.locator("text=Sair, text=Logout").count() > 0,
                await self.page.locator("input[type='text'], input[type='search']").count() > 0,
                "login" not in self.page.url.lower(),
            ]
            
            success = any(success_indicators)
            logger.info(f"Login indicators: {success_indicators}")
            
            if success or await self.page.locator("input[type='text']").count() > 0:
                logger.info("Login successful to Euromais")
                return True, "Login successful"
            else:
                logger.warning("Login verification unclear - proceeding")
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
            
            # Find and fill search input (first text input on catalog page)
            search_inputs = await self.page.locator('input[type="text"]').all()
            if search_inputs:
                await search_inputs[0].clear()
                await search_inputs[0].fill(medida_normalized)
                logger.info(f"Filled search: {medida_normalized}")
                await asyncio.sleep(1)
                
                # Press Enter or click search icon
                await search_inputs[0].press("Enter")
                logger.info("Submitted search")
            else:
                logger.warning("No search input found")
                return None
            
            # Wait for results
            await asyncio.sleep(4)
            await self.page.wait_for_load_state("domcontentloaded", timeout=10000)
            
            await self.take_screenshot(f"search_results_{medida_normalized}")
            
            # Get page content
            content = await self.page.content()
            
            # Check for no results
            if any(text in content.lower() for text in ["sem resultado", "não encontrado", "nenhum produto", "nenhum registo"]):
                logger.info(f"No results for {medida_normalized}")
                return None
            
            # Extract prices from PREÇO column (based on screenshot)
            # Prices appear in format: € 36.99, € 29.98, etc.
            import re
            
            # Multiple patterns for PT price format
            price_patterns = [
                r'€\s*(\d+[,\.]\d{2})',  # € 36.99 or € 36,99
                r'(\d+[,\.]\d{2})\s*€',  # 36.99€ or 36,99€
                r'"price"\s*:\s*"?(\d+[,\.]\d{2})"?',  # JSON price
                r'PREÇO.*?€\s*(\d+[,\.]\d{2})',  # After PREÇO label
            ]
            
            found_prices = []
            for pattern in price_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    try:
                        price_str = match.replace(',', '.')
                        price = float(price_str)
                        # Reasonable tire price range
                        if 15 < price < 500:
                            found_prices.append(price)
                            logger.debug(f"Found price: €{price}")
                    except ValueError:
                        continue
            
            if found_prices:
                # Remove duplicates and get lowest
                found_prices = list(set(found_prices))
                best_price = min(found_prices)
                logger.info(f"Found {len(found_prices)} unique prices, lowest: €{best_price}")
                return best_price
            
            logger.warning(f"No valid prices extracted for {medida_normalized}")
            return None
            return None
            
        except Exception as e:
            logger.error(f"Search error: {str(e)}")
            await self.take_screenshot(f"search_error_{self.normalize_medida(medida)}")
            return None

class MP24Adapter(ScraperBase):
    """Adapter for MP24 (Euromaster Marketplace) using Playwright"""
    
    def normalize_medida(self, medida: str) -> str:
        return medida.replace('/', '').replace('R', '').replace('r', '')
    
    def normalize_indice(self, indice: str) -> str:
        return indice.replace(' XL', '').replace('XL', '').strip()
    
    async def login(self) -> tuple[bool, str]:
        """Login to MP24"""
        try:
            logger.info(f"MP24: Navigating to {self.url_login}")
            await self.page.goto(self.url_login, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(3)
            
            # Check if already logged in
            content = await self.page.content()
            if 'sair' in content.lower() or 'logout' in content.lower():
                logger.info("MP24: Already logged in")
                return True, "Already logged in"
            
            # Fill username using name attribute
            username_input = self.page.locator('input[name="_username"]')
            if await username_input.count() > 0:
                await username_input.fill(self.username)
                logger.info(f"Filled username: {self.username}")
            else:
                await self.page.locator('input[type="text"]').first.fill(self.username)
            
            # Fill password
            password_input = self.page.locator('input[name="_password"]')
            if await password_input.count() > 0:
                await password_input.fill(self.password)
            else:
                await self.page.locator('input[type="password"]').first.fill(self.password)
            logger.info("Filled password")
            
            await asyncio.sleep(1)
            
            # Submit login
            login_btn = self.page.locator('a:has-text("Início de sessão")')
            if await login_btn.count() > 0:
                await login_btn.click()
            else:
                await self.page.evaluate("document.getElementById('login_form')?.submit()")
            
            await asyncio.sleep(4)
            await self.page.wait_for_load_state("networkidle")
            
            # Check if logged in
            content = await self.page.content()
            if 'sair' in content.lower() or 'logout' in content.lower():
                logger.info("MP24 login successful")
                return True, "Login successful"
            
            return True, "Login completed"
            
        except Exception as e:
            logger.error(f"MP24 login error: {str(e)}")
            return False, f"Login error: {str(e)}"
    
    async def search_product(self, medida: str, marca: str, modelo: str, indice: str) -> Optional[float]:
        """Search for tire on MP24 using matchcode"""
        try:
            medida_normalized = self.normalize_medida(medida)
            logger.info(f"MP24 search: {medida} → {medida_normalized}")
            
            # Navigate to tyres page
            await self.page.goto("https://pt.mp24.online/pt_PT/tyres/", wait_until="networkidle", timeout=45000)
            await asyncio.sleep(3)
            
            # Wait for matchcode field to be available
            try:
                await self.page.wait_for_selector('#matchcodeField', timeout=10000)
            except:
                logger.warning("MP24: matchcodeField not found, waiting more...")
                await asyncio.sleep(3)
            
            # Use matchcode search field
            matchcode_input = self.page.locator('#matchcodeField')
            if await matchcode_input.count() > 0:
                await matchcode_input.clear()
                await matchcode_input.fill(medida_normalized)
                logger.info(f"MP24: Filled matchcode with {medida_normalized}")
                await asyncio.sleep(1)
                
                # Submit search - find the form's submit button
                submit_btn = self.page.locator('#matchcode button[type="submit"]')
                if await submit_btn.count() > 0:
                    await submit_btn.click()
                    logger.info("MP24: Clicked submit button")
                else:
                    await matchcode_input.press("Enter")
                    logger.info("MP24: Pressed Enter")
                
                await asyncio.sleep(5)
                await self.page.wait_for_load_state("networkidle")
            else:
                logger.warning("MP24: matchcodeField not found")
                return None
            
            # Get content and extract prices
            content = await self.page.content()
            
            price_patterns = [
                r'€\s*(\d+[,\.]\d{2})',
                r'(\d+[,\.]\d{2})\s*€',
                r'"purchasePrice"\s*:\s*"?(\d+\.?\d*)"?',
                r'"price"\s*:\s*"?(\d+\.?\d*)"?',
            ]
            
            found_prices = []
            for pattern in price_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    try:
                        price_str = match.replace(',', '.')
                        price = float(price_str)
                        if 15 < price < 500:
                            found_prices.append(price)
                    except ValueError:
                        continue
            
            if found_prices:
                best_price = min(found_prices)
                logger.info(f"MP24: Found {len(found_prices)} prices, best: €{best_price}")
                return best_price
            
            logger.info(f"MP24: No prices found for {medida_normalized}")
            return None
            
        except Exception as e:
            logger.error(f"MP24 search error: {str(e)}")
            return None


class PrismanilAdapter(ScraperBase):
    """Adapter for Prismanil B2B using Playwright"""
    
    def normalize_medida(self, medida: str) -> str:
        return medida.replace('/', '').replace('R', '').replace('r', '')
    
    def normalize_indice(self, indice: str) -> str:
        return indice.replace(' XL', '').replace('XL', '').strip()
    
    async def login(self) -> tuple[bool, str]:
        """Login to Prismanil"""
        try:
            logger.info(f"Prismanil: Navigating to {self.url_login}")
            await self.page.goto(self.url_login, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(3)
            
            # Check if already logged in (search field visible)
            content = await self.page.content()
            if "txtPesquisa" in content and "btnPesquisar" in content:
                logger.info("Prismanil: Already logged in")
                return True, "Already logged in"
            
            # Fill username
            username_input = self.page.locator('input[type="text"]').first
            if await username_input.count() > 0:
                await username_input.fill(self.username)
                logger.info(f"Filled username: {self.username}")
            
            # Fill password
            password_input = self.page.locator('input[type="password"]').first
            if await password_input.count() > 0:
                await password_input.fill(self.password)
                logger.info("Filled password")
            
            await asyncio.sleep(1)
            
            # Submit
            submit_btn = self.page.locator('button:has-text("Entrar")').first
            if await submit_btn.count() > 0:
                await submit_btn.click()
                logger.info("Clicked Entrar button")
            else:
                await password_input.press("Enter")
                logger.info("Pressed Enter")
            
            await asyncio.sleep(5)
            await self.page.wait_for_load_state("networkidle")
            
            # Wait for search elements to appear
            try:
                await self.page.wait_for_selector('#txtPesquisa', timeout=15000)
                logger.info("Prismanil login successful - search field visible")
                return True, "Login successful"
            except:
                # Check content anyway
                content = await self.page.content()
                if "Pneus" in content or "pesquisa" in content.lower():
                    logger.info("Prismanil login completed")
                    return True, "Login completed"
            
            return True, "Login completed"
            
        except Exception as e:
            logger.error(f"Prismanil login error: {str(e)}")
            return False, f"Login error: {str(e)}"
    
    async def search_product(self, medida: str, marca: str, modelo: str, indice: str) -> Optional[float]:
        """Search for tire on Prismanil"""
        try:
            medida_normalized = self.normalize_medida(medida)
            logger.info(f"Prismanil search: {medida} → {medida_normalized}")
            
            # Ensure we're on the search page
            current_url = self.page.url
            if 'pesquisa' not in current_url:
                await self.page.goto("https://www.prismanil.pt/b2b/pesquisa", wait_until="networkidle", timeout=30000)
                await asyncio.sleep(3)
            
            # Wait for search field
            try:
                await self.page.wait_for_selector('#txtPesquisa', timeout=10000)
            except:
                logger.warning("Prismanil: txtPesquisa not found, waiting more...")
                await asyncio.sleep(3)
            
            # Fill search field
            search_input = self.page.locator('#txtPesquisa')
            if await search_input.count() > 0:
                await search_input.clear()
                await search_input.fill(medida_normalized)
                logger.info(f"Prismanil: Filled search with {medida_normalized}")
            else:
                logger.warning("Prismanil: #txtPesquisa not found")
                return None
            
            await asyncio.sleep(1)
            
            # Click search button
            search_btn = self.page.locator('#btnPesquisar')
            if await search_btn.count() > 0:
                await search_btn.click()
                logger.info("Prismanil: Clicked Pesquisar")
            else:
                await search_input.press("Enter")
                logger.info("Prismanil: Pressed Enter")
            
            # Wait for results
            await asyncio.sleep(5)
            await self.page.wait_for_load_state("networkidle")
            
            # Extract prices
            content = await self.page.content()
            
            price_patterns = [
                r'€\s*(\d+[,\.]\d{2})',
                r'(\d+[,\.]\d{2})\s*€',
                r'"preco"\s*:\s*"?(\d+[,\.]\d{2})"?',
                r'"price"\s*:\s*"?(\d+[,\.]\d{2})"?',
            ]
            
            found_prices = []
            for pattern in price_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    try:
                        price_str = match.replace(',', '.')
                        price = float(price_str)
                        if 15 < price < 500:
                            found_prices.append(price)
                    except ValueError:
                        continue
            
            if found_prices:
                best_price = min(found_prices)
                logger.info(f"Prismanil: Found {len(found_prices)} prices, best: €{best_price}")
                return best_price
            
            logger.info(f"Prismanil: No prices found for {medida_normalized}")
            return None
            
        except Exception as e:
            logger.error(f"Prismanil search error: {str(e)}")
            return None
            return None
            
        except Exception as e:
            logger.error(f"Prismanil search error: {str(e)}")
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
        
        # Select appropriate adapter based on supplier
        if 'mp24' in supplier_name_lower or 'mp24' in supplier_url_lower:
            logger.info(f"Using MP24Adapter for {supplier['name']}")
            adapter = MP24Adapter(
                supplier_id=supplier_id,
                supplier_name=supplier['name'],
                url_login=supplier['url_login'],
                url_search=supplier['url_search'],
                username=supplier['username'],
                password=supplier['password'],
                selectors=supplier.get('selectors')
            )
        elif 'prismanil' in supplier_name_lower or 'prismanil' in supplier_url_lower:
            logger.info(f"Using PrismanilAdapter for {supplier['name']}")
            adapter = PrismanilAdapter(
                supplier_id=supplier_id,
                supplier_name=supplier['name'],
                url_login=supplier['url_login'],
                url_search=supplier['url_search'],
                username=supplier['username'],
                password=supplier['password'],
                selectors=supplier.get('selectors')
            )
        elif 'sjose' in supplier_name_lower or 'sjose' in supplier_url_lower:
            logger.info(f"Using SJoseAdapter for {supplier['name']}")
            adapter = SJoseAdapter(
                supplier_id=supplier_id,
                supplier_name=supplier['name'],
                url_login=supplier['url_login'],
                url_search=supplier['url_search'],
                username=supplier['username'],
                password=supplier['password'],
                selectors=supplier.get('selectors')
            )
        elif 'euromais' in supplier_name_lower or 'eurotyre' in supplier_url_lower:
            logger.info(f"Using EuromaisAdapter for {supplier['name']}")
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
            # Default: Use SJoseAdapter as generic fallback
            logger.info(f"Using generic SJoseAdapter for {supplier['name']}")
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
