#!/usr/bin/env python3
"""
Fix script to add password_raw to existing suppliers.
Run once: python3 fix_passwords.py
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment
load_dotenv(Path('/app/backend/.env'))

from pymongo import MongoClient

MONGO_URL = os.environ.get('MONGO_URL')
DB_NAME = os.environ.get('DB_NAME')

if not MONGO_URL or not DB_NAME:
    print(f"ERROR: MONGO_URL or DB_NAME not set!")
    print(f"  MONGO_URL = {MONGO_URL}")
    print(f"  DB_NAME = {DB_NAME}")
    exit(1)

print(f"Connecting to MongoDB: {MONGO_URL}")
print(f"Database: {DB_NAME}")

client = MongoClient(MONGO_URL)
db = client[DB_NAME]

# Password mapping (from handoff summary)
passwords = {
    "mp24": "Sl6dBhGf",
    "prismanil": "dompedro4785",
    "dispnal": "501060251",
    "josé": "5010600251",
    "jose": "5010600251",
    "euromais": "5010600251",
    "eurotyre": "5010600251",
    "s. josé": "5010600251",
}

suppliers = list(db.suppliers.find({}))
print(f"\nFound {len(suppliers)} suppliers")

for supplier in suppliers:
    name = supplier.get('name', '').lower()
    updated = False
    
    for key, raw_pass in passwords.items():
        if key in name:
            result = db.suppliers.update_one(
                {"_id": supplier["_id"]},
                {"$set": {"password_raw": raw_pass}}
            )
            print(f"  Updated {supplier['name']}: password_raw = {raw_pass}")
            updated = True
            break
    
    if not updated:
        print(f"  SKIPPED {supplier['name']}: no matching password found")

print("\n=== Verification ===")
for supplier in db.suppliers.find({}):
    has_raw = 'password_raw' in supplier and supplier['password_raw']
    status = 'OK' if has_raw else 'MISSING'
    print(f"  {supplier.get('name')}: password_raw = {status}")

client.close()
print("\nDone!")
