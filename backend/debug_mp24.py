#!/usr/bin/env python3
"""
Debug MP24 API response to understand price structure
"""
import asyncio
import os
import json
from datetime import datetime

os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '/pw-browsers'

from playwright.async_api import async_playwright

URL = "https://pt.mp24.online"
USERNAME = "PTO02101"
PASSWORD = "Sl6dBhGf"
MEDIDA = "1956515"

async def debug_mp24():
    print(f"=== Debugging MP24 API Response ===")
    print(f"Medida: {MEDIDA}")
    print()
    
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
        
        # Capture API responses
        captured_data = []
        
        async def handle_response(response):
            if 'tyres2v0' in response.url and 'json' in response.headers.get('content-type', ''):
                try:
                    data = await response.json()
                    if isinstance(data, list) and len(data) > 0:
                        captured_data.append(data)
                except:
                    pass
        
        page.on('response', handle_response)
        
        try:
            # Login - use exact same logic as scraper
            print("Logging in...")
            await page.goto(f"{URL}/login", wait_until="networkidle", timeout=60000)
            await asyncio.sleep(2)
            
            # Use specific selectors
            email_input = page.locator('input[formcontrolname="email"], input[name="email"]').first
            password_input = page.locator('input[formcontrolname="password"], input[name="password"]').first
            
            if await email_input.count() > 0:
                await email_input.fill(USERNAME)
            if await password_input.count() > 0:
                await password_input.fill(PASSWORD)
            
            # Find login button
            login_btn = page.locator('button.btn-primary:has-text("Entrar"), button:has-text("Login"), button[type="submit"]:visible').first
            if await login_btn.count() > 0:
                await login_btn.click()
            else:
                await password_input.press('Enter')
            
            await asyncio.sleep(5)
            print(f"After login URL: {page.url}")
            
            # Navigate to tyres
            print(f"\nNavigating to tyres page...")
            await page.goto(f"{URL}/pt_PT/tyres2v0/car/result?matchcode={MEDIDA}", wait_until="networkidle", timeout=60000)
            await asyncio.sleep(10)
            
            print(f"Captured {len(captured_data)} API responses")
            
            if captured_data:
                # Get the first response with data
                tyres = captured_data[0]
                
                # Find HANKOOK VENTUS PRIME 3
                print("\n=== Looking for Hankook VENTUS PRIME 3 ===")
                
                for tyre in tyres:
                    brand = tyre.get('manufacturer', '').upper()
                    model = tyre.get('profile', '')
                    
                    if brand == 'HANKOOK' and 'VENTUS' in model.upper() and 'PRIME' in model.upper():
                        print(f"\nFound: {brand} {model}")
                        
                        # Check bestPricesBySource
                        best_prices = tyre.get('bestPricesBySource', {})
                        print(f"\nbestPricesBySource sources: {list(best_prices.keys())}")
                        
                        for source, source_data in best_prices.items():
                            print(f"\n  === Source: {source} ===")
                            best_price = source_data.get('bestPrice', {})
                            if best_price:
                                print(f"    purchasePrice: {best_price.get('purchasePrice')}")
                                print(f"    retailPrice: {best_price.get('retailPrice')}")
                                print(f"    netPurchasePrice: {best_price.get('netPurchasePrice')}")
                                print(f"    grossPurchasePrice: {best_price.get('grossPurchasePrice')}")
                        
                        # Save full data
                        with open('/app/tmp/mp24_ventus.json', 'w') as f:
                            json.dump(tyre, f, indent=2)
                        print("\nFull tyre data saved to /app/tmp/mp24_ventus.json")
                        break
                
                # Also find KINERGY ECO K425 which should be €45.90
                print("\n=== Looking for Hankook KINERGY ECO K425 4PR VW (should be €45.90) ===")
                for tyre in tyres:
                    brand = tyre.get('manufacturer', '').upper()
                    model = tyre.get('profile', '')
                    
                    if brand == 'HANKOOK' and 'KINERGY' in model.upper() and 'K425' in model.upper() and 'VW' in model.upper():
                        print(f"\nFound: {brand} {model}")
                        
                        best_prices = tyre.get('bestPricesBySource', {})
                        for source, source_data in best_prices.items():
                            best_price = source_data.get('bestPrice', {})
                            if best_price:
                                print(f"  {source}: purchasePrice={best_price.get('purchasePrice')}")
                        break
            
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_mp24())
