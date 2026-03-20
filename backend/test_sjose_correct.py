#!/usr/bin/env python3
"""
Test S. José Pneus with correct credentials
"""
import asyncio
import os
import sys
import re
from datetime import datetime
from pathlib import Path

os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '/pw-browsers'

from playwright.async_api import async_playwright

# CORRECTED credentials (9 digits, not 10)
URL = "https://b2b.sjosepneus.com"
USERNAME = "501060251"
PASSWORD = "501060251"
MEDIDA = "2055516"
SCREENSHOT_DIR = Path("/app/tmp")

async def test_sjose():
    print(f"=== Testing S. José Pneus ===")
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
            # Step 1: Navigate and login
            print("Step 1: Navigating to login page...")
            await page.goto(URL, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(2)
            await page.screenshot(path=str(SCREENSHOT_DIR / "sjose_01_login.png"))
            print(f"  Screenshot: sjose_01_login.png")
            
            # Step 2: Fill form
            print("\nStep 2: Filling login form...")
            await page.locator('#ContentPlaceHolder1_ctrlLogin_Login_UserName').fill(USERNAME)
            await page.locator('#ContentPlaceHolder1_ctrlLogin_Login_Password').fill(PASSWORD)
            await asyncio.sleep(1)
            await page.screenshot(path=str(SCREENSHOT_DIR / "sjose_02_filled.png"))
            print(f"  Screenshot: sjose_02_filled.png")
            
            # Step 3: Click login
            print("\nStep 3: Clicking 'Entrar'...")
            await page.locator('#ContentPlaceHolder1_ctrlLogin_Login_btnLogin').click()
            await asyncio.sleep(5)
            await page.screenshot(path=str(SCREENSHOT_DIR / "sjose_03_after_login.png"))
            print(f"  Screenshot: sjose_03_after_login.png")
            print(f"  URL: {page.url}")
            
            # Check for error
            error_visible = await page.locator('p.error').is_visible()
            if error_visible:
                error_text = await page.locator('p.error').text_content()
                print(f"  ERROR: {error_text.strip()}")
                return
            
            # Check if logged in
            if "login.aspx" in page.url.lower():
                print("  Still on login page - checking for other issues...")
                html = await page.content()
                with open(SCREENSHOT_DIR / "sjose_03_after_login.html", "w") as f:
                    f.write(html)
                return
            
            print("  LOGIN SUCCESSFUL!")
            
            # Step 4: Explore the dashboard
            print("\nStep 4: Exploring dashboard...")
            html = await page.content()
            with open(SCREENSHOT_DIR / "sjose_04_dashboard.html", "w") as f:
                f.write(html)
            
            # Look for navigation/menu
            nav_links = await page.locator('nav a, .menu a, .navbar a, #menu a, .nav a').all()
            print(f"  Found {len(nav_links)} nav links")
            
            # List all visible links
            all_links = await page.locator('a:visible').all()
            print(f"  Found {len(all_links)} visible links")
            for link in all_links[:15]:
                text = (await link.text_content() or '').strip()
                href = await link.get_attribute('href')
                if text:
                    print(f"    - {text[:40]}: {href}")
            
            # Step 5: Look for tire/product section
            print("\nStep 5: Looking for tire section...")
            
            # Try different selectors for product/tire links
            tire_selectors = [
                'a:has-text("Pneus")',
                'a:has-text("Turismo")',
                'a:has-text("Produtos")',
                'a:has-text("Pesquisa")',
                'a:has-text("Catálogo")',
                'a[href*="pneu"]',
                'a[href*="product"]',
                'a[href*="search"]',
                'a[href*="pesq"]',
            ]
            
            for selector in tire_selectors:
                count = await page.locator(selector).count()
                if count > 0:
                    text = await page.locator(selector).first.text_content()
                    print(f"  Found: {selector} -> '{text.strip() if text else ''}'")
                    await page.locator(selector).first.click()
                    await asyncio.sleep(3)
                    await page.screenshot(path=str(SCREENSHOT_DIR / "sjose_05_products.png"))
                    print(f"  Screenshot: sjose_05_products.png")
                    print(f"  URL: {page.url}")
                    break
            
            # Step 6: Search for tire size
            print(f"\nStep 6: Searching for medida {MEDIDA}...")
            
            # Look for search inputs
            search_selectors = [
                'input[type="search"]',
                'input[placeholder*="pesq"]',
                'input[placeholder*="search"]',
                'input[name*="search"]',
                'input[name*="pesq"]',
                'input[id*="search"]',
                'input[id*="pesq"]',
                '#txtPesquisa',
                '#searchBox',
            ]
            
            search_found = False
            for selector in search_selectors:
                count = await page.locator(selector).count()
                if count > 0:
                    print(f"  Found search input: {selector}")
                    search_input = page.locator(selector).first
                    await search_input.fill(MEDIDA)
                    await search_input.press('Enter')
                    search_found = True
                    await asyncio.sleep(5)
                    await page.screenshot(path=str(SCREENSHOT_DIR / "sjose_06_search.png"))
                    print(f"  Screenshot: sjose_06_search.png")
                    break
            
            if not search_found:
                # Look for dimension dropdowns
                print("  No search input, looking for dimension selectors...")
                
                # Save current page for analysis
                html = await page.content()
                with open(SCREENSHOT_DIR / "sjose_05_page.html", "w") as f:
                    f.write(html)
                
                # List all input elements
                inputs = await page.locator('input:visible').all()
                print(f"  Found {len(inputs)} visible inputs:")
                for inp in inputs[:10]:
                    inp_type = await inp.get_attribute('type')
                    inp_name = await inp.get_attribute('name')
                    inp_id = await inp.get_attribute('id')
                    inp_placeholder = await inp.get_attribute('placeholder')
                    print(f"    - type={inp_type}, name={inp_name}, id={inp_id}, placeholder={inp_placeholder}")
                
                # List select elements
                selects = await page.locator('select:visible').all()
                print(f"  Found {len(selects)} visible selects:")
                for sel in selects[:10]:
                    sel_name = await sel.get_attribute('name')
                    sel_id = await sel.get_attribute('id')
                    print(f"    - name={sel_name}, id={sel_id}")
            
            # Step 7: Extract prices
            print("\nStep 7: Extracting prices...")
            html = await page.content()
            
            # Find prices
            price_patterns = [
                r'€\s*(\d+[,\.]\d{2})',
                r'(\d+[,\.]\d{2})\s*€',
            ]
            
            found_prices = []
            for pattern in price_patterns:
                matches = re.findall(pattern, html)
                for match in matches:
                    try:
                        price = float(match.replace(',', '.'))
                        if 15 < price < 500:
                            found_prices.append(price)
                    except:
                        pass
            
            found_prices = sorted(set(found_prices))
            if found_prices:
                print(f"  Found {len(found_prices)} prices: {found_prices[:10]}")
                print(f"  Best price: €{min(found_prices)}")
            else:
                print("  No prices found on current page")
            
            print("\n=== Test Complete ===")
            
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
            await page.screenshot(path=str(SCREENSHOT_DIR / "sjose_error.png"))
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test_sjose())
