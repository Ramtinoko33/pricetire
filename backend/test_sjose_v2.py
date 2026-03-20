#!/usr/bin/env python3
"""
Test script for S. José Pneus - with better form handling
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

async def test_sjose_v2():
    print(f"=== Testing S. José Pneus Scraper V2 ===")
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
        
        # Capture network requests
        requests_log = []
        async def log_request(request):
            if 'login' in request.url.lower():
                requests_log.append({
                    'url': request.url,
                    'method': request.method,
                    'post_data': request.post_data
                })
        
        page.on('request', log_request)
        
        try:
            # Step 1: Navigate to login page
            print("Step 1: Navigating to login page...")
            await page.goto(URL, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(3)  # Wait more for ASP.NET viewstate
            await page.screenshot(path=str(SCREENSHOT_DIR / "v2_01_initial.png"))
            print(f"  Screenshot: v2_01_initial.png")
            print(f"  URL: {page.url}")
            
            # Step 2: Get all form data first
            print("\nStep 2: Analyzing form...")
            form_data = await page.evaluate('''() => {
                const form = document.querySelector('form');
                const inputs = form.querySelectorAll('input');
                const data = {};
                inputs.forEach(input => {
                    data[input.name || input.id] = {
                        type: input.type,
                        value: input.value ? input.value.substring(0, 50) : '',
                        id: input.id,
                        name: input.name
                    };
                });
                return data;
            }''')
            
            print(f"  Form has {len(form_data)} inputs")
            for name, info in list(form_data.items())[:10]:
                if info['type'] not in ['hidden']:
                    print(f"    - {name}: type={info['type']}, id={info['id']}")
            
            # Step 3: Fill form using type() instead of fill()
            print("\nStep 3: Filling login form with type()...")
            
            # Clear and type username
            username_input = page.locator('#ContentPlaceHolder1_ctrlLogin_Login_UserName')
            await username_input.click()
            await username_input.fill('')  # Clear first
            await asyncio.sleep(0.5)
            await username_input.type(USERNAME, delay=100)  # Type slowly like human
            
            # Clear and type password
            password_input = page.locator('#ContentPlaceHolder1_ctrlLogin_Login_Password')
            await password_input.click()
            await password_input.fill('')
            await asyncio.sleep(0.5)
            await password_input.type(PASSWORD, delay=100)
            
            await asyncio.sleep(1)
            await page.screenshot(path=str(SCREENSHOT_DIR / "v2_02_filled.png"))
            print(f"  Screenshot: v2_02_filled.png")
            
            # Verify values were set
            username_val = await username_input.input_value()
            password_val = await password_input.input_value()
            print(f"  Username value: {username_val}")
            print(f"  Password value: {'*' * len(password_val) if password_val else 'EMPTY'}")
            
            # Step 4: Find and click login button
            print("\nStep 4: Submitting login...")
            
            # Look for login button
            login_btn = page.locator('#ContentPlaceHolder1_ctrlLogin_Login_LoginButton')
            if await login_btn.count() == 0:
                login_btn = page.locator('input[type="submit"][value*="Entrar"]')
            if await login_btn.count() == 0:
                login_btn = page.locator('input[type="submit"]').first
            
            print(f"  Found login button: {await login_btn.count() > 0}")
            
            # Click the button
            await login_btn.click()
            
            # Wait for navigation or response
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except:
                pass
            
            await asyncio.sleep(3)
            await page.screenshot(path=str(SCREENSHOT_DIR / "v2_03_after_login.png"))
            print(f"  Screenshot: v2_03_after_login.png")
            print(f"  URL: {page.url}")
            
            # Save HTML
            html = await page.content()
            with open(SCREENSHOT_DIR / "v2_03_after_login.html", "w") as f:
                f.write(html)
            
            # Check for errors
            error_el = page.locator('.error:visible, p.error')
            if await error_el.count() > 0:
                error_text = await error_el.first.text_content()
                print(f"  ERROR: {error_text.strip()}")
            
            # Check network requests
            print(f"\n  Login requests captured: {len(requests_log)}")
            for req in requests_log:
                print(f"    - {req['method']} {req['url'][:60]}")
                if req['post_data']:
                    # Parse post data
                    print(f"      Post data length: {len(req['post_data'])}")
            
            # Check if login was successful
            is_logged_in = "login.aspx" not in page.url.lower()
            print(f"\n  Logged in (based on URL): {is_logged_in}")
            
            # Check page content for login indicators
            content = await page.content()
            if 'sair' in content.lower() or 'logout' in content.lower():
                print("  Found logout link - login successful!")
                is_logged_in = True
            
            if is_logged_in:
                # Continue with search...
                print("\nStep 5: Searching for products...")
                # ... rest of search logic
            else:
                print("\n  Login failed - trying alternative approach...")
                
                # Try submitting form via JavaScript
                print("\nStep 5: Trying JavaScript form submit...")
                await page.evaluate('''() => {
                    const form = document.querySelector('form');
                    if (form) {
                        // Trigger ASP.NET postback
                        __doPostBack('ctl00$ContentPlaceHolder1$ctrlLogin$Login$LoginButton', '');
                    }
                }''')
                
                await asyncio.sleep(5)
                await page.screenshot(path=str(SCREENSHOT_DIR / "v2_04_js_submit.png"))
                print(f"  Screenshot: v2_04_js_submit.png")
                print(f"  URL: {page.url}")
            
            print("\n=== Test Complete ===")
            
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
            await page.screenshot(path=str(SCREENSHOT_DIR / "v2_error.png"))
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test_sjose_v2())
