#!/usr/bin/env python3
"""
S. José Pneus - Complete Scraper Test
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
    print(f"=== S. José Pneus Complete Test ===")
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
            # Step 1: Login
            print("Step 1: Logging in...")
            await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(2)
            
            await page.locator('#ContentPlaceHolder1_ctrlLogin_Login_UserName').fill(USERNAME)
            await page.locator('#ContentPlaceHolder1_ctrlLogin_Login_Password').fill(PASSWORD)
            await page.locator('#ContentPlaceHolder1_ctrlLogin_Login_btnLogin').click()
            await asyncio.sleep(5)
            
            if "default.aspx" not in page.url:
                print("  ERROR: Login failed!")
                await page.screenshot(path=str(SCREENSHOT_DIR / "sjose_login_fail.png"))
                return
            
            print("  Login successful!")
            await page.screenshot(path=str(SCREENSHOT_DIR / "sjose_01_dashboard.png"))
            
            # Step 2: Navigate to search page
            print("\nStep 2: Going to search page...")
            await page.locator('a:has-text("Pesquisa")').first.click()
            await asyncio.sleep(10)
            
            print(f"  URL: {page.url}")
            await page.screenshot(path=str(SCREENSHOT_DIR / "sjose_02_search.png"))
            
            # Step 3: Fill search field and submit
            print(f"\nStep 3: Searching for {MEDIDA}...")
            
            # Fill the size field
            size_input = page.locator('#ContentPlaceHolder1_txtSize')
            await size_input.fill(MEDIDA)
            await asyncio.sleep(1)
            
            await page.screenshot(path=str(SCREENSHOT_DIR / "sjose_03_filled.png"))
            print(f"  Screenshot: sjose_03_filled.png")
            
            # Click search button
            search_btn = page.locator('#ContentPlaceHolder1_btnSearch, input[value*="Pesquisar"], button:has-text("Pesquisar")').first
            if await search_btn.count() > 0:
                print("  Clicking search button...")
                await search_btn.click()
            else:
                # Try pressing Enter
                print("  Pressing Enter...")
                await size_input.press('Enter')
            
            # Wait for results
            await asyncio.sleep(10)
            
            await page.screenshot(path=str(SCREENSHOT_DIR / "sjose_04_results.png"))
            print(f"  Screenshot: sjose_04_results.png")
            print(f"  URL: {page.url}")
            
            # Save HTML
            html = await page.content()
            with open(SCREENSHOT_DIR / "sjose_04_results.html", "w") as f:
                f.write(html)
            
            # Step 4: Extract products and prices
            print("\nStep 4: Extracting products...")
            
            # Try to extract from table rows
            products = await page.evaluate('''() => {
                const products = [];
                
                // Try finding table rows
                const rows = document.querySelectorAll('tr');
                
                rows.forEach(row => {
                    const cells = row.querySelectorAll('td');
                    const text = row.textContent || '';
                    
                    // Look for price patterns in the row
                    const priceMatch = text.match(/(\d+[,\.]\d{2})\s*€|€\s*(\d+[,\.]\d{2})/);
                    
                    if (priceMatch && cells.length >= 2) {
                        const priceStr = priceMatch[1] || priceMatch[2];
                        const price = parseFloat(priceStr.replace(',', '.'));
                        
                        if (price > 15 && price < 500) {
                            // Try to extract brand from row
                            let brand = '';
                            let description = '';
                            
                            cells.forEach(cell => {
                                const cellText = cell.textContent.trim();
                                // Check for known tire brands
                                const brands = ['MICHELIN', 'BRIDGESTONE', 'CONTINENTAL', 'PIRELLI', 'GOODYEAR', 
                                               'DUNLOP', 'YOKOHAMA', 'HANKOOK', 'KUMHO', 'NEXEN', 'TOYO',
                                               'FIRESTONE', 'FULDA', 'SEMPERIT', 'BARUM', 'UNIROYAL',
                                               'GOODRIDE', 'WESTLAKE', 'LINGLONG', 'TRIANGLE', 'FORTUNE'];
                                               
                                for (const b of brands) {
                                    if (cellText.toUpperCase().includes(b)) {
                                        brand = b;
                                        break;
                                    }
                                }
                                
                                // Get description (usually contains model info)
                                if (cellText.length > 10 && !description) {
                                    description = cellText.substring(0, 100);
                                }
                            });
                            
                            products.push({
                                brand: brand,
                                description: description,
                                price: price,
                                rowText: text.substring(0, 200)
                            });
                        }
                    }
                });
                
                return products;
            }''')
            
            if products and len(products) > 0:
                print(f"  Found {len(products)} products")
                for p in products[:10]:
                    print(f"    - {p['brand'] or 'Unknown'}: €{p['price']}")
                    if p['description']:
                        print(f"      {p['description'][:60]}...")
            else:
                print("  No products found via table extraction")
                
                # Fallback: simple price extraction
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
                    print(f"  Fallback: Found {len(found_prices)} prices")
                    print(f"  Prices: {found_prices[:10]}")
                    print(f"  Best price: €{min(found_prices)}")
                else:
                    print("  No prices found at all")
                    
                    # Debug: show page structure
                    print("\n  Debug: Page elements...")
                    tables = await page.locator('table').count()
                    print(f"    Tables: {tables}")
                    trs = await page.locator('tr').count()
                    print(f"    Table rows: {trs}")
                    divs = await page.locator('div[class*="product"], div[class*="item"], div[class*="result"]').count()
                    print(f"    Product divs: {divs}")
            
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
