#!/usr/bin/env python3
"""
Capture raw MP24 API data using tyres2v0 endpoint
"""
import asyncio
import os
import json

os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '/pw-browsers'

from playwright.async_api import async_playwright

async def debug_mp24_prices():
    print("=== Capturing MP24 API Data (tyres2v0) ===")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        )
        
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            viewport={'width': 1920, 'height': 1080},
        )
        
        page = await context.new_page()
        
        captured_tyres = []
        
        async def handle_response(response):
            try:
                url = response.url
                content_type = response.headers.get('content-type', '')
                
                if ('tyres' in url or 'tyre' in url) and 'json' in content_type:
                    data = await response.json()
                    if isinstance(data, list) and len(data) > 0:
                        captured_tyres.extend(data)
                        print(f"  Captured {len(data)} items from {url[:60]}...")
            except:
                pass
        
        page.on('response', handle_response)
        
        try:
            # Login
            print("Logging in...")
            await page.goto("https://pt.mp24.online/pt_PT", wait_until="networkidle", timeout=60000)
            await asyncio.sleep(2)
            
            await page.locator('input[name="_username"]').fill("PTO02101")
            await page.locator('input[name="_password"]').fill("Sl6dBhGf")
            await page.locator('a:has-text("Início de sessão")').click()
            await asyncio.sleep(5)
            
            print(f"After login URL: {page.url}")
            
            # Navigate directly to tyres2v0 result page
            print("\nNavigating to tyres2v0...")
            await page.goto("https://pt.mp24.online/pt_PT/tyres2v0/car/result?matchcode=1956515", 
                          wait_until="networkidle", timeout=60000)
            await asyncio.sleep(10)
            
            print(f"\nTotal captured: {len(captured_tyres)} tyres")
            
            if captured_tyres:
                # Find HANKOOK VENTUS PRIME 3
                print("\n=== Finding HANKOOK VENTUS PRIME 3 K125 4PR ===")
                
                for tyre in captured_tyres:
                    brand = tyre.get('manufacturer', '').upper()
                    model = tyre.get('profile', '')
                    
                    if brand == 'HANKOOK' and 'VENTUS' in model.upper() and 'PRIME' in model.upper() and '4PR' in model.upper():
                        print(f"\nFound: {brand} {model}")
                        
                        # Save the full tyre data
                        with open('/app/tmp/ventus_prime_raw.json', 'w') as f:
                            json.dump(tyre, f, indent=2)
                        
                        # Check bestPricesBySource
                        print("\n=== bestPricesBySource ===")
                        best_prices = tyre.get('bestPricesBySource', {})
                        
                        all_prices = []
                        for source, source_data in best_prices.items():
                            print(f"\n  Source: {source}")
                            best_price = source_data.get('bestPrice', {})
                            if best_price:
                                purchase = best_price.get('purchasePrice')
                                retail = best_price.get('retailPrice')
                                net = best_price.get('netPurchasePrice')
                                gross = best_price.get('grossPurchasePrice')
                                
                                print(f"    purchasePrice: {purchase}")
                                print(f"    retailPrice: {retail}")
                                print(f"    netPurchasePrice: {net}")
                                print(f"    grossPurchasePrice: {gross}")
                                
                                # Collect all non-None prices
                                for price in [purchase, retail, net, gross]:
                                    if price and 15 < price < 500:
                                        all_prices.append(price)
                        
                        print(f"\n=== All prices found: {sorted(set(all_prices))} ===")
                        print(f"=== MIN price: {min(all_prices) if all_prices else 'N/A'} ===")
                        
                        break
                else:
                    print("VENTUS PRIME 3 K125 4PR not found!")
                    
                    # List all Hankook models
                    print("\n=== All Hankook models found ===")
                    for tyre in captured_tyres:
                        if tyre.get('manufacturer', '').upper() == 'HANKOOK':
                            print(f"  {tyre.get('profile')}")
            
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_mp24_prices())
