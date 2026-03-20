#!/usr/bin/env python3
"""
Test S. José Pneus - click search link
"""
import asyncio
import os
import sys
import re
from datetime import datetime
from pathlib import Path

os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '/pw-browsers'

from playwright.async_api import async_playwright

URL = "https://b2b.sjosepneus.com"
USERNAME = "501060251"
PASSWORD = "501060251"
MEDIDA = "2055516"
SCREENSHOT_DIR = Path("/app/tmp")

async def test_sjose():
    print(f"=== Testing S. José Pneus ===")
    
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
            # Step 1: Login
            print("Step 1: Logging in...")
            await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(2)
            
            await page.locator('#ContentPlaceHolder1_ctrlLogin_Login_UserName').fill(USERNAME)
            await page.locator('#ContentPlaceHolder1_ctrlLogin_Login_Password').fill(PASSWORD)
            await page.locator('#ContentPlaceHolder1_ctrlLogin_Login_btnLogin').click()
            await asyncio.sleep(5)
            
            print(f"  URL: {page.url}")
            if "default.aspx" in page.url:
                print("  Login successful!")
            
            await page.screenshot(path=str(SCREENSHOT_DIR / "sjose_01_dashboard.png"))
            
            # Step 2: Click on "Pesquisa" link
            print("\nStep 2: Clicking 'Pesquisa' link...")
            pesquisa_link = page.locator('a:has-text("Pesquisa")').first
            
            if await pesquisa_link.count() > 0:
                await pesquisa_link.click()
                await asyncio.sleep(10)  # Wait longer for the page
                
                await page.screenshot(path=str(SCREENSHOT_DIR / "sjose_02_search_page.png"))
                print(f"  Screenshot: sjose_02_search_page.png")
                print(f"  URL: {page.url}")
                
                # Save HTML
                html = await page.content()
                with open(SCREENSHOT_DIR / "sjose_02_search_page.html", "w") as f:
                    f.write(html)
            else:
                print("  'Pesquisa' link not found!")
                return
            
            # Step 3: Analyze the search page
            print("\nStep 3: Analyzing search interface...")
            
            # Check for dropdowns (dimension selectors)
            selects = await page.locator('select').all()
            print(f"  Found {len(selects)} select elements")
            
            for sel in selects:
                sel_id = await sel.get_attribute('id')
                sel_name = await sel.get_attribute('name')
                
                # Get options
                options = await sel.locator('option').all()
                option_texts = []
                for opt in options[:5]:
                    text = await opt.text_content()
                    option_texts.append(text.strip() if text else '')
                
                print(f"    - id={sel_id}, options: {option_texts}")
            
            # Check for text inputs
            inputs = await page.locator('input[type="text"]:visible').all()
            print(f"\n  Found {len(inputs)} text inputs")
            for inp in inputs[:5]:
                inp_id = await inp.get_attribute('id')
                inp_placeholder = await inp.get_attribute('placeholder')
                print(f"    - id={inp_id}, placeholder={inp_placeholder}")
            
            # Step 4: Try to search
            print(f"\nStep 4: Searching for {MEDIDA}...")
            
            # Parse medida: 2055516 -> width=205, aspect=55, rim=16
            width = "205"
            aspect = "55"
            rim = "16"
            
            # Try to find and fill dimension dropdowns
            # Common patterns: ddlWidth, ddlLargura, ddlJante, etc.
            
            width_filled = False
            aspect_filled = False
            rim_filled = False
            
            for sel in selects:
                sel_id = (await sel.get_attribute('id') or '').lower()
                sel_name = (await sel.get_attribute('name') or '').lower()
                
                # Get options to analyze
                options = await sel.locator('option').all()
                option_texts = [await opt.text_content() for opt in options]
                
                # Width (largura) selector - usually has values like 155, 165, 175, 185, 195, 205...
                if any(w in sel_id for w in ['width', 'largura', 'larg']) or '205' in option_texts:
                    if not width_filled:
                        try:
                            await sel.select_option(value=width)
                            width_filled = True
                            print(f"    Selected width={width} in {sel_id}")
                        except:
                            try:
                                await sel.select_option(label=width)
                                width_filled = True
                                print(f"    Selected width={width} in {sel_id}")
                            except:
                                pass
                
                # Aspect ratio (altura/serie) - usually 30, 35, 40, 45, 50, 55, 60...
                elif any(a in sel_id for a in ['height', 'altura', 'serie', 'aspect']) or '55' in option_texts:
                    if not aspect_filled:
                        try:
                            await sel.select_option(value=aspect)
                            aspect_filled = True
                            print(f"    Selected aspect={aspect} in {sel_id}")
                        except:
                            try:
                                await sel.select_option(label=aspect)
                                aspect_filled = True
                                print(f"    Selected aspect={aspect} in {sel_id}")
                            except:
                                pass
                
                # Rim diameter (jante) - usually 13, 14, 15, 16, 17, 18...
                elif any(r in sel_id for r in ['rim', 'jante', 'aro', 'diameter']) or '16' in option_texts:
                    if not rim_filled:
                        try:
                            await sel.select_option(value=rim)
                            rim_filled = True
                            print(f"    Selected rim={rim} in {sel_id}")
                        except:
                            try:
                                await sel.select_option(label=rim)
                                rim_filled = True
                                print(f"    Selected rim={rim} in {sel_id}")
                            except:
                                pass
            
            await asyncio.sleep(2)
            await page.screenshot(path=str(SCREENSHOT_DIR / "sjose_03_dimensions.png"))
            
            # Look for search button
            search_btn = page.locator('input[type="submit"], button[type="submit"], input[value*="Pesquisar"], button:has-text("Pesquisar")').first
            if await search_btn.count() > 0:
                print("  Clicking search button...")
                await search_btn.click()
                await asyncio.sleep(10)
                
                await page.screenshot(path=str(SCREENSHOT_DIR / "sjose_04_results.png"))
                print(f"  Screenshot: sjose_04_results.png")
                
                # Save HTML
                html = await page.content()
                with open(SCREENSHOT_DIR / "sjose_04_results.html", "w") as f:
                    f.write(html)
            
            # Step 5: Extract prices
            print("\nStep 5: Extracting prices...")
            html = await page.content()
            
            # Find prices
            price_patterns = [
                r'€\s*(\d+[,\.]\d{2})',
                r'(\d+[,\.]\d{2})\s*€',
                r'"price"[:\s]+(\d+[,\.]\d+)',
            ]
            
            found_prices = []
            for pattern in price_patterns:
                matches = re.findall(pattern, html, re.IGNORECASE)
                for match in matches:
                    try:
                        price = float(match.replace(',', '.'))
                        if 15 < price < 500:
                            found_prices.append(price)
                    except:
                        pass
            
            found_prices = sorted(set(found_prices))
            if found_prices:
                print(f"  Found {len(found_prices)} prices")
                print(f"  Prices: {found_prices[:15]}")
                print(f"  Best price: €{min(found_prices)}")
            else:
                print("  No prices found")
            
            # Look for product data in HTML
            print("\n  Looking for product rows...")
            product_count = await page.locator('tr[class*="row"], .product, .article, [data-price]').count()
            print(f"  Found {product_count} potential product elements")
            
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
