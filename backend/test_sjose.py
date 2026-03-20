#!/usr/bin/env python3
"""
Test script for S. José Pneus scraper - step by step with screenshots
"""
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '/pw-browsers'

from playwright.async_api import async_playwright

# Config
URL = "https://b2b.sjosepneus.com"
USERNAME = "5010600251"
PASSWORD = "5010600251"
MEDIDA = "2055516"
SCREENSHOT_DIR = Path("/app/tmp")

async def test_sjose():
    print(f"=== Testing S. José Pneus Scraper ===")
    print(f"URL: {URL}")
    print(f"User: {USERNAME}")
    print(f"Medida: {MEDIDA}")
    print()
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        )
        
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='pt-PT',
        )
        
        page = await context.new_page()
        
        try:
            # Step 1: Navigate to login page
            print("Step 1: Navigating to login page...")
            await page.goto(URL, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(2)
            await page.screenshot(path=str(SCREENSHOT_DIR / "01_sjose_initial.png"))
            print(f"  Screenshot: 01_sjose_initial.png")
            
            # Get page URL after redirect
            current_url = page.url
            print(f"  Current URL: {current_url}")
            
            # Save HTML for analysis
            html = await page.content()
            with open(SCREENSHOT_DIR / "01_sjose_initial.html", "w") as f:
                f.write(html)
            
            # Step 2: Find login form elements
            print("\nStep 2: Analyzing login form...")
            
            # Try different username input selectors
            username_selectors = [
                '#ContentPlaceHolder1_ctrlLogin_Login_UserName',
                'input[name*="UserName"]',
                'input[name*="username"]',
                'input[type="text"]',
                '#txtUsername',
                '#username',
            ]
            
            username_input = None
            for selector in username_selectors:
                count = await page.locator(selector).count()
                if count > 0:
                    username_input = page.locator(selector).first
                    print(f"  Found username input: {selector}")
                    break
            
            # Try different password input selectors
            password_selectors = [
                '#ContentPlaceHolder1_ctrlLogin_Login_Password',
                'input[name*="Password"]',
                'input[name*="password"]',
                'input[type="password"]',
                '#txtPassword',
                '#password',
            ]
            
            password_input = None
            for selector in password_selectors:
                count = await page.locator(selector).count()
                if count > 0:
                    password_input = page.locator(selector).first
                    print(f"  Found password input: {selector}")
                    break
            
            # Try different login button selectors
            button_selectors = [
                '#ContentPlaceHolder1_ctrlLogin_Login_LoginButton',
                'input[type="submit"]',
                'button[type="submit"]',
                'input[value*="Entrar"]',
                'input[value*="Login"]',
                'button:has-text("Entrar")',
                'button:has-text("Login")',
                '.btn-login',
            ]
            
            login_button = None
            for selector in button_selectors:
                count = await page.locator(selector).count()
                if count > 0:
                    login_button = page.locator(selector).first
                    print(f"  Found login button: {selector}")
                    break
            
            if not username_input or not password_input:
                print("  ERROR: Could not find login form elements!")
                # List all inputs on page
                all_inputs = await page.locator('input').all()
                print(f"  Found {len(all_inputs)} input elements:")
                for inp in all_inputs[:10]:
                    inp_type = await inp.get_attribute('type')
                    inp_name = await inp.get_attribute('name')
                    inp_id = await inp.get_attribute('id')
                    print(f"    - type={inp_type}, name={inp_name}, id={inp_id}")
                return
            
            # Step 3: Fill login form
            print("\nStep 3: Filling login form...")
            await username_input.fill(USERNAME)
            await password_input.fill(PASSWORD)
            await asyncio.sleep(1)
            await page.screenshot(path=str(SCREENSHOT_DIR / "02_sjose_form_filled.png"))
            print(f"  Screenshot: 02_sjose_form_filled.png")
            
            # Step 4: Submit login
            print("\nStep 4: Submitting login...")
            if login_button:
                await login_button.click()
            else:
                await password_input.press('Enter')
            
            await asyncio.sleep(5)
            await page.screenshot(path=str(SCREENSHOT_DIR / "03_sjose_after_login.png"))
            print(f"  Screenshot: 03_sjose_after_login.png")
            
            # Check current URL
            current_url = page.url
            print(f"  Current URL: {current_url}")
            
            # Save HTML
            html = await page.content()
            with open(SCREENSHOT_DIR / "03_sjose_after_login.html", "w") as f:
                f.write(html)
            
            # Check for error messages
            error_texts = await page.locator('.error, .alert-danger, .msg-error, [class*="error"]').all_text_contents()
            if error_texts:
                print(f"  Errors found: {error_texts}")
            
            # Step 5: Look for search functionality
            print("\nStep 5: Looking for search/product functionality...")
            
            # Check if we're logged in by looking for common elements
            content = await page.content()
            logged_in_indicators = ['logout', 'sair', 'bem-vindo', 'carrinho', 'conta']
            is_logged_in = any(ind in content.lower() for ind in logged_in_indicators)
            print(f"  Appears logged in: {is_logged_in}")
            
            # Try to find main navigation/menu
            nav_links = await page.locator('nav a, .menu a, .navbar a, #menu a').all()
            print(f"  Found {len(nav_links)} navigation links")
            for link in nav_links[:10]:
                text = await link.text_content()
                href = await link.get_attribute('href')
                if text and text.strip():
                    print(f"    - {text.strip()}: {href}")
            
            # Look for search input
            search_selectors = [
                'input[type="search"]',
                'input[placeholder*="pesq"]',
                'input[placeholder*="search"]',
                'input[name*="search"]',
                'input[name*="pesq"]',
                '#txtPesquisa',
                '#searchBox',
                '.search-input',
            ]
            
            search_input = None
            for selector in search_selectors:
                count = await page.locator(selector).count()
                if count > 0:
                    search_input = page.locator(selector).first
                    print(f"  Found search input: {selector}")
                    break
            
            # Step 6: Navigate to products/tires section
            print("\nStep 6: Looking for tires/products section...")
            
            # Try common links
            tire_links = [
                'a:has-text("Pneus")',
                'a:has-text("Pneu")',
                'a:has-text("Turismo")',
                'a:has-text("Produtos")',
                'a:has-text("Catálogo")',
                'a[href*="pneu"]',
                'a[href*="tyre"]',
                'a[href*="product"]',
            ]
            
            for link_selector in tire_links:
                count = await page.locator(link_selector).count()
                if count > 0:
                    print(f"  Found tire link: {link_selector}")
                    await page.locator(link_selector).first.click()
                    await asyncio.sleep(3)
                    await page.screenshot(path=str(SCREENSHOT_DIR / "04_sjose_products.png"))
                    print(f"  Screenshot: 04_sjose_products.png")
                    
                    # Save HTML
                    html = await page.content()
                    with open(SCREENSHOT_DIR / "04_sjose_products.html", "w") as f:
                        f.write(html)
                    break
            
            # Current URL
            current_url = page.url
            print(f"  Current URL: {current_url}")
            
            # Step 7: Try to search for tire size
            print(f"\nStep 7: Searching for medida {MEDIDA}...")
            
            # Re-check for search input after navigation
            for selector in search_selectors:
                count = await page.locator(selector).count()
                if count > 0:
                    search_input = page.locator(selector).first
                    print(f"  Found search input: {selector}")
                    break
            
            if search_input:
                await search_input.fill(MEDIDA)
                await asyncio.sleep(1)
                
                # Try to find and click search button
                search_btn_selectors = [
                    'button[type="submit"]',
                    'input[type="submit"]',
                    '.btn-search',
                    'button:has-text("Pesquisar")',
                    'button:has-text("Buscar")',
                ]
                
                for btn_selector in search_btn_selectors:
                    count = await page.locator(btn_selector).count()
                    if count > 0:
                        await page.locator(btn_selector).first.click()
                        break
                else:
                    await search_input.press('Enter')
                
                await asyncio.sleep(5)
                await page.screenshot(path=str(SCREENSHOT_DIR / "05_sjose_search_results.png"))
                print(f"  Screenshot: 05_sjose_search_results.png")
                
                # Save HTML
                html = await page.content()
                with open(SCREENSHOT_DIR / "05_sjose_search_results.html", "w") as f:
                    f.write(html)
            else:
                # Try dimension filter dropdowns
                print("  No search input found, looking for dimension filters...")
                
                # Look for width/height/diameter selectors
                width_selectors = ['select[name*="width"]', 'select[name*="largura"]', '#width', '#largura']
                height_selectors = ['select[name*="height"]', 'select[name*="altura"]', '#height', '#altura']
                diameter_selectors = ['select[name*="diameter"]', 'select[name*="jante"]', '#diameter', '#jante']
                
                for selector in width_selectors + height_selectors + diameter_selectors:
                    count = await page.locator(selector).count()
                    if count > 0:
                        print(f"  Found dimension selector: {selector}")
            
            # Step 8: Extract prices from results
            print("\nStep 8: Extracting prices...")
            
            # Get page content
            content = await page.content()
            
            # Look for price patterns
            import re
            price_patterns = [
                r'€\s*(\d+[,\.]\d{2})',
                r'(\d+[,\.]\d{2})\s*€',
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
            
            found_prices = list(set(found_prices))
            if found_prices:
                print(f"  Found {len(found_prices)} prices: {sorted(found_prices)[:10]}")
                print(f"  Best price: €{min(found_prices)}")
            else:
                print("  No prices found")
            
            # Look for product elements
            product_selectors = [
                '.product', '.produto', '.item', 'tr.product-row',
                '[data-price]', '[data-preco]',
            ]
            
            for selector in product_selectors:
                count = await page.locator(selector).count()
                if count > 0:
                    print(f"  Found {count} elements with selector: {selector}")
            
            print("\n=== Test Complete ===")
            
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
            await page.screenshot(path=str(SCREENSHOT_DIR / "error_sjose.png"))
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test_sjose())
