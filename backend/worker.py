#!/usr/bin/env python3
"""
Worker process for scraping jobs.
Runs independently from the FastAPI server.

Usage:
    python3 worker.py
"""
import sys
print("=== WORKER STARTING ===", flush=True)
sys.stdout.flush()
import os
print("=== OS imported ===", flush=True)
import time
print("=== TIME imported ===", flush=True)
from datetime import datetime, timedelta
print("=== DATETIME imported ===", flush=True)
from pymongo import MongoClient, ReturnDocument
print("=== PYMONGO imported ===", flush=True)
from bson import ObjectId
print("=== BSON imported ===", flush=True)
from dotenv import load_dotenv
print("=== DOTENV imported ===", flush=True)
import sys
import time
from datetime import datetime, timedelta
from pymongo import MongoClient, ReturnDocument
from bson import ObjectId

# Load environment
from dotenv import load_dotenv
load_dotenv()

MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'test_database')

client = MongoClient(MONGO_URL)
db = client[DB_NAME]

def claim_job():
    """Claim the next queued job"""
    return db.jobs.find_one_and_update(
        {"status": "queued", "type": "scrape"},
        {"$set": {"status": "running", "started_at": datetime.utcnow()}},
        sort=[("created_at", 1)],
        return_document=ReturnDocument.AFTER
    )

def acquire_lock(supplier_id: str, ttl_minutes: int = 10) -> bool:
    """Acquire a lock for a supplier to prevent concurrent scraping"""
    now = datetime.utcnow()
    expires = now + timedelta(minutes=ttl_minutes)
    
    try:
        doc = db.locks.find_one_and_update(
            {
                "_id": supplier_id,
                "$or": [
                    {"expires_at": {"$lte": now}},
                    {"expires_at": {"$exists": False}},
                    {"locked": {"$ne": True}},
                ],
            },
            {"$set": {"locked": True, "expires_at": expires, "updated_at": now}},
            upsert=True,
            return_document=ReturnDocument.AFTER
        )
        # Lock acquired if expires_at > now
        return doc and doc.get("expires_at") and doc["expires_at"] > now
    except Exception as e:
        print(f"Error acquiring lock: {e}")
        return False

def release_lock(supplier_id: str):
    """Release the lock for a supplier"""
    db.locks.update_one(
        {"_id": supplier_id}, 
        {"$set": {"locked": False, "updated_at": datetime.utcnow()}}
    )

def run_supplier_scrape(supplier_id: str, sizes: list, job_id: str):
    """Run the scraper for a supplier"""
    from run_scraper import run_supplier
    run_supplier(supplier_id=supplier_id, sizes=sizes, job_id=job_id)

def main():
    """Main worker loop"""
    print(f"Worker started at {datetime.now()}")
    print(f"MongoDB: {MONGO_URL}")
    print(f"Database: {DB_NAME}")
    print("-" * 50)
    
    while True:
        try:
            job = claim_job()
            
            if not job:
                # No jobs in queue, wait
                time.sleep(2)
                continue
            
            supplier_id = job["supplier_id"]
            job_id = str(job["_id"])
            sizes = job["payload"]["sizes"]
            
            print(f"\n[{datetime.now()}] Processing job {job_id}")
            print(f"  Supplier: {supplier_id}")
            print(f"  Sizes: {sizes}")
            
            # Try to acquire lock
            if not acquire_lock(supplier_id):
                print(f"  Could not acquire lock for {supplier_id}, returning to queue")
                # Return job to queue
                db.jobs.update_one(
                    {"_id": job["_id"]}, 
                    {"$set": {"status": "queued", "started_at": None}}
                )
                time.sleep(1)
                continue
            
            try:
                print(f"  Lock acquired, running scraper...")
                run_supplier_scrape(supplier_id, sizes, job_id)
                
                # Mark job as done
                db.jobs.update_one(
                    {"_id": job["_id"]},
                    {"$set": {
                        "status": "done", 
                        "finished_at": datetime.utcnow(), 
                        "last_error": None
                    }}
                )
                print(f"  Job {job_id} completed successfully")
                
            except Exception as e:
                print(f"  Job {job_id} failed: {e}")
                # Mark job as failed
                db.jobs.update_one(
                    {"_id": job["_id"]},
                    {"$set": {
                        "status": "failed", 
                        "finished_at": datetime.utcnow(), 
                        "last_error": str(e)
                    }}
                )
            finally:
                release_lock(supplier_id)
                print(f"  Lock released for {supplier_id}")
                
        except KeyboardInterrupt:
            print("\nWorker stopped by user")
            break
        except Exception as e:
            print(f"Worker error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
