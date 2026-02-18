#!/usr/bin/env python3
"""
Isolated scraper runner - executes scraping in a separate process
This bypasses anti-bot detection that affects the FastAPI server context
"""
import asyncio
import json
import re
import sys
import os
from pathlib import Path

os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '/pw-browsers'

from playwright.async_api import async_playwright

def extract_prices(content: str) -> list:
    """Extract prices from HTML content"""
    price_patterns = [
        r'€\s*(\d+[,\.]\d{2})',
        r'(\d+[,\.]\d{2})\s*€',
        r'"price"\s*:\s*"?(\d+[,\.]\d{2})"?',
        r'"preco"\s*:\s*"?(\d+[,\.]\d{2})"?',
        r'"purchasePrice"\s*:\s*"?(\d+\.?\d*)"?',
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
    
    return list(set(found_prices))

def normalize_medida(medida: str) -> str:
    """Normalize tire size"""
    return medida.replace('/', '').replace('R', '').replace('r', '')

async def scrape_mp24(username: str, password: str, medida: str) -> dict:
    """Scrape MP24 in isolated context"""
    result = {"supplier": "MP24", "price": None, "error": None}
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled']
        )
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='pt-PT',
        )
        page = await context.new_page()
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
        
        try:
            # Login
            await page.goto("https://pt.mp24.online/pt_PT", wait_until="networkidle", timeout=60000)
            await page.locator('input[name="_username"]').fill(username)
            await page.locator('input[name="_password"]').fill(password)
            await page.locator('a:has-text("Início de sessão")').click()
            await asyncio.sleep(3)
            
            # Navigate to tyres page
            await page.goto("https://pt.mp24.online/pt_PT/tyres/", wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)
            
            medida_normalized = normalize_medida(medida)
            
            # Use matchcode search
            matchcode_input = page.locator('#matchcodeField')
            if await matchcode_input.count() > 0:
                await matchcode_input.fill(medida_normalized)
                await asyncio.sleep(1)
                
                submit_btn = page.locator('button[type="submit"]').first
                if await submit_btn.count() > 0:
                    await submit_btn.click()
                else:
                    await matchcode_input.press("Enter")
                
                await asyncio.sleep(5)
                await page.wait_for_load_state("networkidle")
                
                content = await page.content()
                prices = extract_prices(content)
                
                if prices:
                    result["price"] = min(prices)
            else:
                result["error"] = "matchcodeField not found"
                
        except Exception as e:
            result["error"] = str(e)
        finally:
            await browser.close()
    
    return result

async def scrape_prismanil(username: str, password: str, medida: str) -> dict:
    """Scrape Prismanil in isolated context"""
    result = {"supplier": "Prismanil", "price": None, "error": None}
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled']
        )
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='pt-PT',
        )
        page = await context.new_page()
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
        
        try:
            # Login
            await page.goto("https://www.prismanil.pt/b2b/pesquisa", wait_until="networkidle", timeout=60000)
            await asyncio.sleep(2)
            
            # Check if need to login
            content = await page.content()
            if "txtPesquisa" not in content:
                # Need to login
                username_input = page.locator('input[type="text"]').first
                if await username_input.count() > 0:
                    await username_input.fill(username)
                
                password_input = page.locator('input[type="password"]').first
                if await password_input.count() > 0:
                    await password_input.fill(password)
                
                submit_btn = page.locator('button:has-text("Entrar")').first
                if await submit_btn.count() > 0:
                    await submit_btn.click()
                else:
                    await password_input.press("Enter")
                
                await asyncio.sleep(5)
                await page.wait_for_load_state("networkidle")
            
            medida_normalized = normalize_medida(medida)
            
            # Search
            search_input = page.locator('#txtPesquisa')
            if await search_input.count() > 0:
                await search_input.fill(medida_normalized)
                await asyncio.sleep(1)
                
                search_btn = page.locator('#btnPesquisar')
                if await search_btn.count() > 0:
                    await search_btn.click()
                else:
                    await search_input.press("Enter")
                
                await asyncio.sleep(5)
                await page.wait_for_load_state("networkidle")
                
                content = await page.content()
                prices = extract_prices(content)
                
                if prices:
                    result["price"] = min(prices)
            else:
                result["error"] = "txtPesquisa not found"
                
        except Exception as e:
            result["error"] = str(e)
        finally:
            await browser.close()
    
    return result

async def scrape_dispnal(username: str, password: str, medida: str) -> dict:
    """Scrape Dispnal in isolated context"""
    result = {"supplier": "Dispnal", "price": None, "error": None}
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled']
        )
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='pt-PT',
        )
        page = await context.new_page()
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
        
        try:
            # Login
            await page.goto("https://dispnal.pt/home/homepage", wait_until="networkidle", timeout=60000)
            await asyncio.sleep(3)
            
            # Save initial page for debugging
            content = await page.content()
            
            # Look for login form
            # Try common login selectors
            login_selectors = [
                'input[type="email"]',
                'input[name="email"]',
                'input[name="username"]',
                'input[type="text"]',
            ]
            
            username_filled = False
            for selector in login_selectors:
                elem = page.locator(selector).first
                if await elem.count() > 0 and await elem.is_visible():
                    await elem.fill(username)
                    username_filled = True
                    break
            
            if not username_filled:
                # Maybe need to click a login button first
                login_btn = page.locator('a:has-text("Login"), a:has-text("Entrar"), button:has-text("Login")')
                if await login_btn.count() > 0:
                    await login_btn.first.click()
                    await asyncio.sleep(2)
                    
                    # Try again
                    for selector in login_selectors:
                        elem = page.locator(selector).first
                        if await elem.count() > 0 and await elem.is_visible():
                            await elem.fill(username)
                            username_filled = True
                            break
            
            # Fill password
            password_input = page.locator('input[type="password"]').first
            if await password_input.count() > 0:
                await password_input.fill(password)
            
            await asyncio.sleep(1)
            
            # Submit
            submit_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Login")',
                'button:has-text("Entrar")',
            ]
            
            for selector in submit_selectors:
                elem = page.locator(selector).first
                if await elem.count() > 0 and await elem.is_visible():
                    await elem.click()
                    break
            
            await asyncio.sleep(5)
            await page.wait_for_load_state("networkidle")
            
            # Save post-login page for debugging
            current_url = page.url
            content = await page.content()
            
            # Debug output
            debug_path = f"/app/tmp/dispnal_debug.html"
            with open(debug_path, 'w') as f:
                f.write(content)
            
            medida_normalized = normalize_medida(medida)
            
            # Look for search functionality
            search_selectors = [
                'input[type="search"]',
                'input[placeholder*="pesqui"]',
                'input[placeholder*="search"]',
                'input[name*="search"]',
                'input[name*="medida"]',
            ]
            
            search_found = False
            for selector in search_selectors:
                elem = page.locator(selector).first
                if await elem.count() > 0 and await elem.is_visible():
                    await elem.fill(medida_normalized)
                    await elem.press("Enter")
                    search_found = True
                    break
            
            if search_found:
                await asyncio.sleep(5)
                content = await page.content()
                prices = extract_prices(content)
                
                if prices:
                    result["price"] = min(prices)
            else:
                result["error"] = f"Search not found. URL: {current_url}"
                
        except Exception as e:
            result["error"] = str(e)
        finally:
            await browser.close()
    
    return result

async def scrape_sjose(username: str, password: str, medida: str) -> dict:
    """Scrape S. José in isolated context"""
    result = {"supplier": "S. José Pneus", "price": None, "error": None}
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled']
        )
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='pt-PT',
        )
        page = await context.new_page()
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
        
        try:
            await page.goto("https://b2b.sjosepneus.com/default.aspx", wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(3)
            
            # Fill login
            username_input = page.locator('input[type="text"]').first
            if await username_input.count() > 0:
                await username_input.fill(username)
            
            password_input = page.locator('input[type="password"]').first
            if await password_input.count() > 0:
                await password_input.fill(password)
                await password_input.press("Enter")
            
            await asyncio.sleep(5)
            
            medida_normalized = normalize_medida(medida)
            
            # Search
            search_input = page.locator('input[type="text"]').first
            if await search_input.count() > 0:
                await search_input.fill(medida_normalized)
                await search_input.press("Enter")
                
                await asyncio.sleep(5)
                
                content = await page.content()
                prices = extract_prices(content)
                
                if prices:
                    result["price"] = min(prices)
                    
        except Exception as e:
            result["error"] = str(e)
        finally:
            await browser.close()
    
    return result

async def scrape_euromais(username: str, password: str, medida: str) -> dict:
    """Scrape Euromais in isolated context"""
    result = {"supplier": "euromais", "price": None, "error": None}
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled']
        )
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='pt-PT',
        )
        page = await context.new_page()
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
        
        try:
            await page.goto("https://www.eurotyre.pt/", wait_until="networkidle", timeout=60000)
            await asyncio.sleep(3)
            
            # Login - Euromais uses specific form
            username_input = page.locator('input[type="text"], input[type="email"]').first
            if await username_input.count() > 0:
                await username_input.fill(username)
            
            password_input = page.locator('input[type="password"]').first
            if await password_input.count() > 0:
                await password_input.fill(password)
                await password_input.press("Enter")
            
            await asyncio.sleep(5)
            
            # Check for search
            medida_normalized = normalize_medida(medida)
            
            search_input = page.locator('input[type="search"], input[name*="search"]').first
            if await search_input.count() > 0:
                await search_input.fill(medida_normalized)
                await search_input.press("Enter")
                
                await asyncio.sleep(5)
                
                content = await page.content()
                prices = extract_prices(content)
                
                if prices:
                    result["price"] = min(prices)
            else:
                result["error"] = "Search not found"
                    
        except Exception as e:
            result["error"] = str(e)
        finally:
            await browser.close()
    
    return result

async def main():
    """Main entry point - expects JSON config from stdin"""
    # Read config from stdin
    config = json.loads(sys.stdin.read())
    
    supplier = config.get('supplier', '').lower()
    username = config.get('username', '')
    password = config.get('password', '')
    medida = config.get('medida', '')
    
    if 'mp24' in supplier:
        result = await scrape_mp24(username, password, medida)
    elif 'prismanil' in supplier:
        result = await scrape_prismanil(username, password, medida)
    elif 'dispnal' in supplier:
        result = await scrape_dispnal(username, password, medida)
    elif 'sjose' in supplier or 'josé' in supplier:
        result = await scrape_sjose(username, password, medida)
    elif 'euromais' in supplier or 'eurotyre' in supplier:
        result = await scrape_euromais(username, password, medida)
    else:
        result = {"supplier": supplier, "price": None, "error": f"Unknown supplier: {supplier}"}
    
    # Output result as JSON
    print(json.dumps(result))

if __name__ == "__main__":
    asyncio.run(main())
