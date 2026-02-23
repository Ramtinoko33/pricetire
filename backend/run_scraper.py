#!/usr/bin/env python3
"""
Standalone scraper that runs independently and saves results to MongoDB.
Can be triggered manually or via cron.

Usage:
  python3 run_scraper.py                    # Scrape all active suppliers
  python3 run_scraper.py --supplier MP24    # Scrape specific supplier
  python3 run_scraper.py --medida 2055516   # Scrape specific tire size
"""
import asyncio
import json
import os
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

# Setup environment
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '/pw-browsers'
sys.path.insert(0, '/app/backend')

from motor.motor_asyncio import AsyncIOMotorClient
from playwright.async_api import async_playwright
import re

# MongoDB connection
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'test_database')

# Results directory
RESULTS_DIR = Path('/app/tmp/scraper_results')
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

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
    return medida.replace('/', '').replace('R', '').replace('r', '')

async def scrape_mp24(page, username: str, password: str, medida: str) -> dict:
    """Scrape MP24"""
    result = {"supplier": "MP24", "price": None, "error": None, "timestamp": datetime.now(timezone.utc).isoformat()}
    
    try:
        await page.goto("https://pt.mp24.online/pt_PT", wait_until="networkidle", timeout=60000)
        await page.fill('input[name="_username"]', username)
        await page.fill('input[name="_password"]', password)
        await page.click('a:has-text("Início de sessão")')
        await asyncio.sleep(4)
        
        await page.goto("https://pt.mp24.online/pt_PT/tyres/", wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)
        
        medida_norm = normalize_medida(medida)
        
        matchcode = page.locator('#matchcodeField')
        if await matchcode.count() > 0:
            await matchcode.fill(medida_norm)
            await asyncio.sleep(1)
            await page.click('button[type="submit"]')
            await asyncio.sleep(5)
            
            content = await page.content()
            prices = extract_prices(content)
            if prices:
                result["price"] = min(prices)
                result["all_prices"] = sorted(prices)[:10]
        else:
            result["error"] = "Search field not found"
    except Exception as e:
        result["error"] = str(e)
    
    return result

async def scrape_prismanil(page, username: str, password: str, medida: str) -> dict:
    """Scrape Prismanil"""
    result = {"supplier": "Prismanil", "price": None, "error": None, "timestamp": datetime.now(timezone.utc).isoformat()}
    
    try:
        await page.goto("https://www.prismanil.pt/b2b/pesquisa", wait_until="networkidle", timeout=60000)
        await asyncio.sleep(2)
        
        content = await page.content()
        if "txtPesquisa" not in content:
            username_input = page.locator('input[type="text"]').first
            if await username_input.count() > 0:
                await username_input.fill(username)
            
            password_input = page.locator('input[type="password"]').first
            if await password_input.count() > 0:
                await password_input.fill(password)
            
            submit_btn = page.locator('button:has-text("Entrar")').first
            if await submit_btn.count() > 0:
                await submit_btn.click()
            await asyncio.sleep(5)
        
        medida_norm = normalize_medida(medida)
        
        search_input = page.locator('#txtPesquisa')
        if await search_input.count() > 0:
            await search_input.fill(medida_norm)
            await asyncio.sleep(1)
            
            search_btn = page.locator('#btnPesquisar')
            if await search_btn.count() > 0:
                await search_btn.click()
            await asyncio.sleep(5)
            
            content = await page.content()
            prices = extract_prices(content)
            if prices:
                result["price"] = min(prices)
                result["all_prices"] = sorted(prices)[:10]
        else:
            result["error"] = "Search field not found"
    except Exception as e:
        result["error"] = str(e)
    
    return result

async def scrape_dispnal(page, username: str, password: str, medida: str) -> dict:
    """Scrape Dispnal"""
    result = {"supplier": "Dispnal", "price": None, "error": None, "timestamp": datetime.now(timezone.utc).isoformat()}
    
    try:
        await page.goto("https://dispnal.pt/home/homepage", wait_until="networkidle", timeout=60000)
        await asyncio.sleep(3)
        
        content = await page.content()
        if 'Entrar' in content or 'Login' in content:
            login_link = page.locator('a:has-text("Entrar"), a:has-text("Login")')
            if await login_link.count() > 0:
                await login_link.first.click()
                await asyncio.sleep(2)
            
            email_input = page.locator('input[type="email"], input[name*="email"]').first
            if await email_input.count() > 0:
                await email_input.fill(username)
            
            password_input = page.locator('input[type="password"]').first
            if await password_input.count() > 0:
                await password_input.fill(password)
            
            submit_btn = page.locator('button[type="submit"]').first
            if await submit_btn.count() > 0:
                await submit_btn.click()
            await asyncio.sleep(5)
        
        medida_norm = normalize_medida(medida)
        
        medida_input = page.locator('#medida-normal')
        if await medida_input.count() > 0:
            await medida_input.fill(medida_norm)
            await asyncio.sleep(1)
            
            search_btn = page.locator('button[type="submit"], .btn-search').first
            if await search_btn.count() > 0:
                await search_btn.click()
            await asyncio.sleep(5)
            
            content = await page.content()
            prices = extract_prices(content)
            if prices:
                result["price"] = min(prices)
                result["all_prices"] = sorted(prices)[:10]
        else:
            result["error"] = "Search field not found"
    except Exception as e:
        result["error"] = str(e)
    
    return result

async def get_suppliers_from_db():
    """Get active suppliers from MongoDB"""
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    suppliers = []
    async for doc in db.suppliers.find({"is_active": {"$ne": False}}):
        suppliers.append({
            "id": str(doc["_id"]) if "_id" in doc else doc.get("id"),
            "name": doc["name"],
            "username": doc["username"],
            "password": doc["password"],
            "url_login": doc.get("url_login", ""),
        })
    
    client.close()
    return suppliers

async def save_price_to_db(supplier_name: str, medida: str, price: float, error: str = None):
    """Save scraping result to MongoDB"""
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    doc = {
        "supplier_name": supplier_name,
        "medida": medida,
        "price": price,
        "error": error,
        "scraped_at": datetime.now(timezone.utc),
    }
    
    # Upsert - update if exists, insert if not
    await db.scraped_prices.update_one(
        {"supplier_name": supplier_name, "medida": medida},
        {"$set": doc},
        upsert=True
    )
    
    client.close()

async def run_scraper(medidas: list, supplier_filter: str = None):
    """Main scraper function"""
    print(f"Starting scraper at {datetime.now()}")
    print(f"Medidas to scrape: {medidas}")
    
    suppliers = await get_suppliers_from_db()
    print(f"Found {len(suppliers)} suppliers")
    
    if supplier_filter:
        suppliers = [s for s in suppliers if supplier_filter.lower() in s['name'].lower()]
        print(f"Filtered to {len(suppliers)} suppliers matching '{supplier_filter}'")
    
    results = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled']
        )
        
        for supplier in suppliers:
            supplier_name = supplier['name'].lower()
            print(f"\n--- Scraping {supplier['name']} ---")
            
            for medida in medidas:
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080},
                    locale='pt-PT',
                )
                page = await context.new_page()
                await page.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
                
                try:
                    if 'mp24' in supplier_name:
                        result = await scrape_mp24(page, supplier['username'], supplier['password'], medida)
                    elif 'prismanil' in supplier_name:
                        result = await scrape_prismanil(page, supplier['username'], supplier['password'], medida)
                    elif 'dispnal' in supplier_name:
                        result = await scrape_dispnal(page, supplier['username'], supplier['password'], medida)
                    else:
                        result = {"supplier": supplier['name'], "price": None, "error": "Adapter not implemented"}
                    
                    result["medida"] = medida
                    results.append(result)
                    
                    # Save to database
                    await save_price_to_db(supplier['name'], medida, result.get('price'), result.get('error'))
                    
                    if result.get('price'):
                        print(f"  {medida}: €{result['price']}")
                    else:
                        print(f"  {medida}: {result.get('error', 'No price found')}")
                        
                except Exception as e:
                    print(f"  Error: {e}")
                    results.append({"supplier": supplier['name'], "medida": medida, "error": str(e)})
                finally:
                    await context.close()
        
        await browser.close()
    
    # Save results to file
    result_file = RESULTS_DIR / f"scrape_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(result_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\nResults saved to {result_file}")
    print(f"Scraper finished at {datetime.now()}")
    
    return results

async def main():
    parser = argparse.ArgumentParser(description='Run tire price scraper')
    parser.add_argument('--supplier', type=str, help='Filter by supplier name')
    parser.add_argument('--medida', type=str, help='Specific tire size (e.g., 2055516)')
    parser.add_argument('--medidas', type=str, help='Comma-separated list of tire sizes')
    
    args = parser.parse_args()
    
    # Default medida for testing
    if args.medida:
        medidas = [args.medida]
    elif args.medidas:
        medidas = [m.strip() for m in args.medidas.split(',')]
    else:
        medidas = ['2055516']  # Default test size
    
    await run_scraper(medidas, args.supplier)

if __name__ == "__main__":
    asyncio.run(main())
