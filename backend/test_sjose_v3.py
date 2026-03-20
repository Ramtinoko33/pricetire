#!/usr/bin/env python3
"""
Test script for S. José Pneus - with correct button
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

async def test_sjose_v3():
    print(f"=== Testing S. José Pneus Scraper V3 ===")
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
            print(f"  URL: {page.url}")
            
            # Step 2: Fill form
            print("\nStep 2: Filling login form...")
            
            # Username
            username_input = page.locator('#ContentPlaceHolder1_ctrlLogin_Login_UserName')
            await username_input.click()
            await username_input.fill(USERNAME)
            
            # Password
            password_input = page.locator('#ContentPlaceHolder1_ctrlLogin_Login_Password')
            await password_input.click()
            await password_input.fill(PASSWORD)
            
            await asyncio.sleep(1)
            await page.screenshot(path=str(SCREENSHOT_DIR / "v3_01_filled.png"))
            print(f"  Screenshot: v3_01_filled.png")
            
            # Verify values
            username_val = await username_input.input_value()
            password_val = await password_input.input_value()
            print(f"  Username: {username_val}")
            print(f"  Password: {'*' * len(password_val)}")
            
            # Step 3: Click the correct login button
            print("\nStep 3: Clicking 'Entrar' button...")
            
            # Use the CORRECT button ID
            login_btn = page.locator('#ContentPlaceHolder1_ctrlLogin_Login_btnLogin')
            
            if await login_btn.count() > 0:
                btn_value = await login_btn.get_attribute('value')
                print(f"  Button found: value='{btn_value}'")
                
                # Click with navigation wait
                await Promise.all([
                    login_btn.click(),
                    page.wait_for_load_state("networkidle")
                ]) if False else await login_btn.click()
                
                await asyncio.sleep(5)
            else:
                print("  ERROR: Login button not found!")
                return
            
            await page.screenshot(path=str(SCREENSHOT_DIR / "v3_02_after_login.png"))
            print(f"  Screenshot: v3_02_after_login.png")
            print(f"  URL: {page.url}")
            
            # Save HTML
            html = await page.content()
            with open(SCREENSHOT_DIR / "v3_02_after_login.html", "w") as f:
                f.write(html)
            
            # Check for errors
            error_visible = await page.locator('p.error').is_visible()
            if error_visible:
                error_text = await page.locator('p.error').text_content()
                print(f"  ERROR: {error_text.strip()}")
                print("\n  *** CREDENTIALS MAY BE INVALID OR EXPIRED ***")
                print("  Please verify the username/password with the user")
                return
            
            # Check if we're logged in
            if "login.aspx" not in page.url.lower():
                print("  LOGIN SUCCESSFUL!")
                
                # Step 4: Navigate to products/search
                print("\nStep 4: Looking for product search...")
                
                # Take a screenshot of the dashboard
                await page.screenshot(path=str(SCREENSHOT_DIR / "v3_03_dashboard.png"))
                print(f"  Screenshot: v3_03_dashboard.png")
                
                # Look for search functionality
                search_selectors = [
                    'input[type="search"]',
                    'input[placeholder*="pesq"]',
                    '#txtPesquisa',
                    'input[name*="search"]',
                ]
                
                for selector in search_selectors:
                    if await page.locator(selector).count() > 0:
                        print(f"  Found search input: {selector}")
                        search_input = page.locator(selector).first
                        await search_input.fill(MEDIDA)
                        await search_input.press('Enter')
                        await asyncio.sleep(5)
                        await page.screenshot(path=str(SCREENSHOT_DIR / "v3_04_search.png"))
                        break
                else:
                    # Look for navigation links
                    print("  Looking for navigation links...")
                    links = await page.locator('a').all()
                    for link in links[:20]:
                        text = await link.text_content()
                        href = await link.get_attribute('href')
                        if text and text.strip():
                            print(f"    - {text.strip()[:30]}: {href}")
            else:
                print("  LOGIN FAILED - still on login page")
            
            print("\n=== Test Complete ===")
            
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
            await page.screenshot(path=str(SCREENSHOT_DIR / "v3_error.png"))
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test_sjose_v3())
