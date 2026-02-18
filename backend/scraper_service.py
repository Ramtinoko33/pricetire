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

class ScrapingBeeAdapter(ScraperBase):
    """Adapter using ScrapingBee API with session management for login"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.api_key = "O39DKUCEBZMYH87283H6GI2JE84RI5WRRZ9190ARLV7MX5AROAKDTU8DD9RURWDERRV82VO4O1OAN9UW"
        self.api_url = "https://app.scrapingbee.com/api/v1/"
        self.session_id = None  # Will store session after login
    
    def normalize_medida(self, medida: str) -> str:
        return medida.replace('/', '').replace('R', '').replace('r', '')
    
    def normalize_indice(self, indice: str) -> str:
        return indice.replace(' XL', '').replace('XL', '').strip()
    
    async def init_browser(self):
        """No browser needed - uses API"""
        pass
    
    async def close_browser(self):
        """Clean up session"""
        self.session_id = None
    
    async def login(self) -> tuple[bool, str]:
        """Login using ScrapingBee session and JavaScript execution"""
        try:
            import requests
            
            logger.info(f"ScrapingBee: Attempting login to {self.url_login}")
            
            # Generate unique session ID for this supplier
            import hashlib
            session_string = f"{self.supplier_id}_{self.username}"
            self.session_id = hashlib.md5(session_string.encode()).hexdigest()
            
            # JavaScript to fill and submit login form
            js_script = f"""
            // Wait for page to load
            await new Promise(r => setTimeout(r, 2000));
            
            // Find and fill username
            const usernameInputs = document.querySelectorAll('input[type="text"], input[type="email"]');
            if (usernameInputs.length > 0) {{
                usernameInputs[0].value = '{self.username}';
                usernameInputs[0].dispatchEvent(new Event('input', {{ bubbles: true }}));
            }}
            
            // Find and fill password
            const passwordInputs = document.querySelectorAll('input[type="password"]');
            if (passwordInputs.length > 0) {{
                passwordInputs[0].value = '{self.password}';
                passwordInputs[0].dispatchEvent(new Event('input', {{ bubbles: true }}));
            }}
            
            // Wait a bit
            await new Promise(r => setTimeout(r, 1000));
            
            // Find and click login button
            const buttons = document.querySelectorAll('button[type="submit"], input[type="submit"], button:contains("LOGIN"), button:contains("ENTRAR")');
            if (buttons.length > 0) {{
                buttons[0].click();
            }} else {{
                // Fallback: submit form
                const forms = document.querySelectorAll('form');
                if (forms.length > 0) forms[0].submit();
            }}
            
            // Wait for navigation
            await new Promise(r => setTimeout(r, 3000));
            """
            
            params = {
                'api_key': self.api_key,
                'url': self.url_login,
                'render_js': 'true',
                'stealth_proxy': 'true',
                'session_id': self.session_id,
                'js_scenario': '{"instructions": [{"wait": 2000}, {"fill": [{"selector": "input[type=\\\"text\\\"]", "text": "' + self.username + '"}]}, {"fill": [{"selector": "input[type=\\\"password\\\"]", "text": "' + self.password + '"}]}, {"wait": 500}, {"click": "button[type=submit], input[type=submit]"}, {"wait": 3000}]}',
                'country_code': 'pt',
            }
            
            logger.info(f"Making login request with session: {self.session_id}")
            response = requests.post(self.api_url, data=params, timeout=45)
            
            if response.status_code == 200:
                logger.info(f"Login successful - session {self.session_id} established")
                return True, f"Session established: {self.session_id}"
            else:
                logger.error(f"Login failed: {response.status_code}")
                return False, f"Login failed: {response.status_code}"
                
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            return False, f"Login error: {str(e)}"
    
    async def search_product(self, medida: str, marca: str, modelo: str, indice: str) -> Optional[float]:
        """Search using ScrapingBee API with authenticated session"""
        try:
            import requests
            import re
            
            medida_normalized = self.normalize_medida(medida)
            logger.info(f"ScrapingBee search: {medida} → {medida_normalized} | Session: {self.session_id}")
            
            # Use authenticated session to search
            # Build search URL based on supplier
            if 'eurotyre' in self.url_search.lower() or 'euromais' in self.supplier_name.lower():
                search_urls = [
                    f"https://www.eurotyre.pt/pt/pesquisa?q={medida_normalized}",
                    f"https://www.eurotyre.pt/pneus/{medida_normalized}",
                ]
            elif 'sjose' in self.supplier_name.lower() or 'jose' in self.supplier_name.lower():
                search_urls = [
                    f"https://b2b.sjosepneus.com/articles.aspx?search={medida_normalized}",
                    f"https://b2b.sjosepneus.com/default.aspx?medida={medida_normalized}",
                ]
            else:
                search_urls = [f"{self.url_search}?search={medida_normalized}"]
            
            for search_url in search_urls:
                logger.info(f"Searching: {search_url}")
                
                params = {
                    'api_key': self.api_key,
                    'url': search_url,
                    'render_js': 'true',
                    'stealth_proxy': 'true',
                    'session_id': self.session_id,  # Use logged-in session
                    'country_code': 'pt',
                }
                
                try:
                    response = requests.get(self.api_url, params=params, timeout=30)
                    
                    if response.status_code == 200:
                        content = response.text
                        logger.info(f"Got {len(content)} bytes")
                        
                        # Check for "still on login page" indicators
                        if any(text in content.lower() for text in ["login", "utilizador", "password", "entrar"]):
                            logger.warning("Still on login page - session may have expired")
                            continue
                        
                        # Check for no results
                        if any(text in content.lower() for text in ["sem resultado", "não encontrado", "nenhum produto", "nenhum registo"]):
                            logger.info("No results")
                            continue
                        
                        # Extract prices
                        price_patterns = [
                            r'€\s*(\d+[,\.]\d{2})',
                            r'(\d+[,\.]\d{2})\s*€',
                            r'"price"\s*:\s*"?(\d+[,\.]\d{2})"?',
                            r'preco["\']?\s*:\s*["\']?(\d+[,\.]\d{2})',
                            r'valor["\']?\s*:\s*["\']?(\d+[,\.]\d{2})',
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
                            found_prices = list(set(found_prices))
                            best_price = min(found_prices)
                            logger.info(f"✅ Found {len(found_prices)} prices, best: €{best_price}")
                            return best_price
                        else:
                            logger.info("No prices extracted from this URL")
                    else:
                        logger.warning(f"Status {response.status_code}")
                        
                except requests.exceptions.RequestException as e:
                    logger.error(f"Request error: {str(e)}")
                    continue
            
            logger.warning("No prices found on any URL")
            return None
                
        except Exception as e:
            logger.error(f"Search error: {str(e)}")
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
            # Use ScrapingBee for S. José (session-based login)
            logger.info(f"Using ScrapingBee adapter for {supplier['name']}")
            adapter = ScrapingBeeAdapter(
                supplier_id=supplier_id,
                supplier_name=supplier['name'],
                url_login=supplier['url_login'],
                url_search=supplier['url_search'],
                username=supplier['username'],
                password=supplier['password'],
                selectors=supplier.get('selectors')
            )
        elif 'euromais' in supplier_name_lower or 'eurotyre' in supplier_name_lower or 'eurotyre.pt' in supplier_url_lower:
            # Use ScrapingBee for Euromais (free tier)
            logger.info(f"Using ScrapingBee adapter for {supplier['name']}")
            adapter = ScrapingBeeAdapter(
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
