#!/usr/bin/env python3
"""
Find ALL VENTUS PRIME variants
"""
import asyncio
import os
import json

os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '/pw-browsers'

from playwright.async_api import async_playwright

async def find_all_ventus():
    print("=== Finding ALL VENTUS PRIME variants ===")
    
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
            
            # Navigate to tyres2v0
            await page.goto("https://pt.mp24.online/pt_PT/tyres2v0/car/result?matchcode=1956515", 
                          wait_until="networkidle", timeout=60000)
            await asyncio.sleep(10)
            
            print(f"Total captured: {len(captured_tyres)} tyres\n")
            
            # Find ALL VENTUS PRIME variants
            print("=== ALL VENTUS PRIME variants ===")
            
            for tyre in captured_tyres:
                brand = tyre.get('manufacturer', '').upper()
                model = tyre.get('profile', '')
                
                if brand == 'HANKOOK' and 'VENTUS' in model.upper() and 'PRIME' in model.upper():
                    # Get best price
                    best_prices = tyre.get('bestPricesBySource', {})
                    min_price = None
                    
                    for source, source_data in best_prices.items():
                        best_price = source_data.get('bestPrice', {})
                        if best_price:
                            price = best_price.get('purchasePrice')
                            if price and (min_price is None or price < min_price):
                                min_price = price
                    
                    # Get additional identifiers
                    ean = tyre.get('ean', 'N/A')
                    tyre_id = tyre.get('id', 'N/A')
                    
                    print(f"  Model: {model}")
                    print(f"    ID: {tyre_id}, EAN: {ean}")
                    print(f"    MIN purchasePrice: €{min_price}")
                    print()
            
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(find_all_ventus())
