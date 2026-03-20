#!/usr/bin/env python3
"""
Test S. José Pneus - navigate to search page
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
    print(f"=== Testing S. José Pneus - Search Page ===")
    
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
            await page.goto(URL, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(2)
            
            await page.locator('#ContentPlaceHolder1_ctrlLogin_Login_UserName').fill(USERNAME)
            await page.locator('#ContentPlaceHolder1_ctrlLogin_Login_Password').fill(PASSWORD)
            await page.locator('#ContentPlaceHolder1_ctrlLogin_Login_btnLogin').click()
            await asyncio.sleep(3)
            
            print(f"  URL after login: {page.url}")
            
            if "login.aspx" in page.url.lower():
                print("  ERROR: Login failed!")
                return
            
            print("  Login successful!")
            
            # Step 2: Navigate to search page
            print("\nStep 2: Navigating to search page...")
            await page.goto("https://b2b.sjosepneus.com/articles/articles.aspx", wait_until="networkidle", timeout=60000)
            await asyncio.sleep(3)
            await page.screenshot(path=str(SCREENSHOT_DIR / "sjose_search_page.png"))
            print(f"  Screenshot: sjose_search_page.png")
            print(f"  URL: {page.url}")
            
            # Save HTML
            html = await page.content()
            with open(SCREENSHOT_DIR / "sjose_search_page.html", "w") as f:
                f.write(html)
            
            # Step 3: Analyze search page
            print("\nStep 3: Analyzing search page...")
            
            # List all inputs
            inputs = await page.locator('input:visible').all()
            print(f"  Found {len(inputs)} visible inputs:")
            for inp in inputs[:15]:
                inp_type = await inp.get_attribute('type')
                inp_name = await inp.get_attribute('name')
                inp_id = await inp.get_attribute('id')
                inp_placeholder = await inp.get_attribute('placeholder')
                if inp_type != 'hidden':
                    print(f"    - type={inp_type}, id={inp_id}, placeholder={inp_placeholder}")
            
            # List selects (dropdowns)
            selects = await page.locator('select:visible').all()
            print(f"\n  Found {len(selects)} visible selects:")
            for sel in selects[:10]:
                sel_name = await sel.get_attribute('name')
                sel_id = await sel.get_attribute('id')
                print(f"    - name={sel_name}, id={sel_id}")
            
            # Step 4: Try to find and use search
            print(f"\nStep 4: Searching for {MEDIDA}...")
            
            # Look for text search field
            search_input = None
            search_selectors = [
                'input[type="text"]',
                'input[type="search"]',
                'input[placeholder*="pesq"]',
                '#txtSearch',
                '#txtPesquisa',
            ]
            
            for selector in search_selectors:
                count = await page.locator(selector).count()
                if count > 0:
                    search_input = page.locator(selector).first
                    inp_id = await search_input.get_attribute('id')
                    print(f"  Found search input: {selector} (id={inp_id})")
                    break
            
            if search_input:
                await search_input.fill(MEDIDA)
                await asyncio.sleep(1)
                
                # Try to submit
                await search_input.press('Enter')
                await asyncio.sleep(5)
                
                await page.screenshot(path=str(SCREENSHOT_DIR / "sjose_search_results.png"))
                print(f"  Screenshot: sjose_search_results.png")
            else:
                # Try dimension dropdowns
                print("  No text search, looking for dimension dropdowns...")
                
                # Parse medida: 205/55R16 -> width=205, aspect=55, rim=16
                # MEDIDA is already "2055516" -> need to split
                width = MEDIDA[:3]  # 205
                aspect = MEDIDA[3:5]  # 55
                rim = MEDIDA[5:]  # 16
                
                print(f"  Parsed medida: width={width}, aspect={aspect}, rim={rim}")
                
                # Look for dimension selectors by common patterns
                dimension_selectors = await page.evaluate('''() => {
                    const selects = document.querySelectorAll('select');
                    const result = [];
                    selects.forEach(sel => {
                        const options = Array.from(sel.options).map(o => o.text.trim());
                        result.push({
                            id: sel.id,
                            name: sel.name,
                            optionCount: options.length,
                            sampleOptions: options.slice(0, 5)
                        });
                    });
                    return result;
                }''')
                
                print(f"  Select elements analysis:")
                for sel in dimension_selectors:
                    print(f"    - id={sel['id']}, options={sel['optionCount']}, samples={sel['sampleOptions']}")
            
            # Step 5: Look for products/prices
            print("\nStep 5: Looking for products...")
            
            # Find product rows/items
            product_selectors = [
                'tr.product-row',
                '.product-item',
                '.article-row',
                '[data-price]',
                'table tr',
            ]
            
            for selector in product_selectors:
                count = await page.locator(selector).count()
                if count > 0:
                    print(f"  Found {count} elements with: {selector}")
            
            # Extract any visible prices
            html = await page.content()
            price_patterns = [r'€\s*(\d+[,\.]\d{2})', r'(\d+[,\.]\d{2})\s*€']
            
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
            else:
                print("  No prices found yet")
            
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
