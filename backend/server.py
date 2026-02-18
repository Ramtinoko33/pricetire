from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from typing import List, Optional
import uuid
from datetime import datetime, timezone
import asyncio
from io import BytesIO

from models import (
    Supplier, SupplierCreate, SupplierUpdate, SupplierStatus,
    Job, JobCreate, JobItem, JobStatus, ItemStatus,
    Price, Log, TestLoginResponse, JobProgress
)
from scraper_service import ScraperService
from excel_service import ExcelService
from passlib.context import CryptContext

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Services
scraper_service = ScraperService()
excel_service = ExcelService()

# Create the main app
app = FastAPI(title="Pneu Price Scout API")
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============= SUPPLIERS =============

@api_router.get("/suppliers", response_model=List[Supplier])
async def get_suppliers():
    """Get all suppliers"""
    suppliers = await db.suppliers.find({}, {"_id": 0}).to_list(1000)
    # Don't return actual password
    for supplier in suppliers:
        supplier['password'] = "********"
    return suppliers

@api_router.post("/suppliers", response_model=Supplier)
async def create_supplier(supplier_data: SupplierCreate):
    """Create new supplier"""
    supplier_dict = supplier_data.model_dump()
    
    # Hash password
    supplier_dict['password'] = pwd_context.hash(supplier_dict['password'])
    
    # Add metadata
    supplier_dict['id'] = str(uuid.uuid4())
    supplier_dict['is_active'] = True
    supplier_dict['status'] = SupplierStatus.ACTIVE.value
    supplier_dict['last_test'] = None
    supplier_dict['created_at'] = datetime.now(timezone.utc).isoformat()
    
    await db.suppliers.insert_one(supplier_dict)
    
    supplier_dict['password'] = "********"
    return Supplier(**supplier_dict)

@api_router.put("/suppliers/{supplier_id}", response_model=Supplier)
async def update_supplier(supplier_id: str, supplier_data: SupplierUpdate):
    """Update supplier"""
    update_dict = {k: v for k, v in supplier_data.model_dump().items() if v is not None}
    
    # Hash password if provided
    if 'password' in update_dict:
        update_dict['password'] = pwd_context.hash(update_dict['password'])
    
    result = await db.suppliers.update_one(
        {"id": supplier_id},
        {"$set": update_dict}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Supplier not found")
    
    supplier = await db.suppliers.find_one({"id": supplier_id}, {"_id": 0})
    supplier['password'] = "********"
    return Supplier(**supplier)

@api_router.delete("/suppliers/{supplier_id}")
async def delete_supplier(supplier_id: str):
    """Delete supplier"""
    result = await db.suppliers.delete_one({"id": supplier_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return {"message": "Supplier deleted successfully"}

@api_router.post("/suppliers/{supplier_id}/test", response_model=TestLoginResponse)
async def test_supplier_login(supplier_id: str):
    """Test login for supplier"""
    supplier = await db.suppliers.find_one({"id": supplier_id}, {"_id": 0})
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    
    # Decrypt password for testing (in real scenario, password is hashed)
    # For testing, we'll need to store original password or use a test password
    # For now, we'll assume password is stored hashed and can't be decrypted
    # In production, you'd want a separate test_password field or use OAuth
    
    try:
        success, message, screenshot = await scraper_service.test_supplier_login(supplier)
        
        # Update last_test timestamp
        await db.suppliers.update_one(
            {"id": supplier_id},
            {"$set": {
                "last_test": datetime.now(timezone.utc).isoformat(),
                "status": SupplierStatus.ACTIVE.value if success else SupplierStatus.ERROR.value
            }}
        )
        
        # Log the test
        log_doc = {
            "id": str(uuid.uuid4()),
            "supplier_id": supplier_id,
            "level": "INFO" if success else "ERROR",
            "message": f"Login test: {message}",
            "screenshot_path": screenshot,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.logs.insert_one(log_doc)
        
        return TestLoginResponse(success=success, message=message, screenshot_path=screenshot)
        
    except Exception as e:
        logger.error(f"Test login error: {str(e)}\")\n        raise HTTPException(status_code=500, detail=str(e))\n\n# ============= JOBS =============\n\n@api_router.post(\"/jobs/upload\", response_model=Job)\nasync def upload_excel(file: UploadFile = File(...), threshold_euro: float = 5.0, threshold_percent: float = 10.0):\n    \"\"\"Upload Excel file and create job\"\"\"\n    if not file.filename.endswith(('.xlsx', '.xls')):\n        raise HTTPException(status_code=400, detail=\"File must be Excel format (.xlsx or .xls)\")\n    \n    try:\n        # Read file content\n        content = await file.read()\n        \n        # Parse Excel\n        items = excel_service.parse_upload(content, file.filename)\n        \n        if not items:\n            raise HTTPException(status_code=400, detail=\"No valid items found in Excel file\")\n        \n        # Create job\n        job_id = str(uuid.uuid4())\n        job_dict = {\n            \"id\": job_id,\n            \"filename\": file.filename,\n            \"status\": JobStatus.PENDING.value,\n            \"total_items\": len(items),\n            \"processed_items\": 0,\n            \"found_items\": 0,\n            \"total_savings\": 0.0,\n            \"threshold_euro\": threshold_euro,\n            \"threshold_percent\": threshold_percent,\n            \"created_at\": datetime.now(timezone.utc).isoformat(),\n            \"started_at\": None,\n            \"completed_at\": None,\n            \"error_message\": None\n        }\n        \n        await db.jobs.insert_one(job_dict)\n        \n        # Create job items\n        for item in items:\n            item_doc = {\n                \"id\": str(uuid.uuid4()),\n                \"job_id\": job_id,\n                \"ref_id\": item['ref_id'],\n                \"medida\": item['medida'],\n                \"marca\": item['marca'],\n                \"modelo\": item['modelo'],\n                \"indice\": item['indice'],\n                \"meu_preco\": item['meu_preco'],\n                \"melhor_preco\": None,\n                \"melhor_fornecedor\": None,\n                \"economia_euro\": None,\n                \"economia_percent\": None,\n                \"status\": ItemStatus.PENDING.value,\n                \"supplier_prices\": {},\n                \"created_at\": datetime.now(timezone.utc).isoformat()\n            }\n            await db.job_items.insert_one(item_doc)\n        \n        logger.info(f\"Created job {job_id} with {len(items)} items\")\n        return Job(**job_dict)\n        \n    except ValueError as e:\n        raise HTTPException(status_code=400, detail=str(e))\n    except Exception as e:\n        logger.error(f\"Upload error: {str(e)}\")\n        raise HTTPException(status_code=500, detail=f\"Failed to process file: {str(e)}\")\n\n@api_router.post(\"/jobs/{job_id}/run\")\nasync def run_job(job_id: str, background_tasks: BackgroundTasks):\n    \"\"\"Start scraping job\"\"\"\n    job = await db.jobs.find_one({\"id\": job_id}, {\"_id\": 0})\n    if not job:\n        raise HTTPException(status_code=404, detail=\"Job not found\")\n    \n    if job['status'] == JobStatus.RUNNING.value:\n        raise HTTPException(status_code=400, detail=\"Job is already running\")\n    \n    # Update job status\n    await db.jobs.update_one(\n        {\"id\": job_id},\n        {\"$set\": {\n            \"status\": JobStatus.RUNNING.value,\n            \"started_at\": datetime.now(timezone.utc).isoformat()\n        }}\n    )\n    \n    # Run scraping in background\n    background_tasks.add_task(run_scraping_job, job_id)\n    \n    return {\"message\": \"Job started\", \"job_id\": job_id}\n\nasync def run_scraping_job(job_id: str):\n    \"\"\"Background task to run scraping job\"\"\"\n    try:\n        logger.info(f\"Starting scraping job {job_id}\")\n        \n        # Get job and items\n        job = await db.jobs.find_one({\"id\": job_id}, {\"_id\": 0})\n        items = await db.job_items.find({\"job_id\": job_id}, {\"_id\": 0}).to_list(None)\n        \n        # Get active suppliers\n        suppliers = await db.suppliers.find({\"is_active\": True}, {\"_id\": 0}).to_list(None)\n        \n        if not suppliers:\n            await db.jobs.update_one(\n                {\"id\": job_id},\n                {\"$set\": {\n                    \"status\": JobStatus.FAILED.value,\n                    \"error_message\": \"No active suppliers found\",\n                    \"completed_at\": datetime.now(timezone.utc).isoformat()\n                }}\n            )\n            return\n        \n        processed = 0\n        found = 0\n        total_savings = 0.0\n        \n        # Process each item\n        for item in items:\n            logger.info(f\"Processing item {item['ref_id']}: {item['medida']} {item['marca']} {item['modelo']}\")\n            \n            # Update item status\n            await db.job_items.update_one(\n                {\"id\": item['id']},\n                {\"$set\": {\"status\": ItemStatus.PROCESSING.value}}\n            )\n            \n            supplier_prices = {}\n            best_price = None\n            best_supplier = None\n            \n            # Search in each supplier\n            for supplier in suppliers:\n                try:\n                    logger.info(f\"Searching in {supplier['name']}...\")\n                    \n                    price = await scraper_service.scrape_product(\n                        supplier,\n                        item['medida'],\n                        item['marca'],\n                        item['modelo'],\n                        item['indice']\n                    )\n                    \n                    if price is not None:\n                        supplier_prices[supplier['name']] = price\n                        \n                        # Track best price\n                        if best_price is None or price < best_price:\n                            best_price = price\n                            best_supplier = supplier['name']\n                        \n                        # Save price record\n                        price_doc = {\n                            \"id\": str(uuid.uuid4()),\n                            \"job_id\": job_id,\n                            \"item_id\": item['id'],\n                            \"supplier_id\": supplier['id'],\n                            \"supplier_name\": supplier['name'],\n                            \"price\": price,\n                            \"status\": ItemStatus.FOUND.value,\n                            \"found_at\": datetime.now(timezone.utc).isoformat()\n                        }\n                        await db.prices.insert_one(price_doc)\n                    else:\n                        supplier_prices[supplier['name']] = \"NAO_ENCONTRADO\"\n                        \n                        price_doc = {\n                            \"id\": str(uuid.uuid4()),\n                            \"job_id\": job_id,\n                            \"item_id\": item['id'],\n                            \"supplier_id\": supplier['id'],\n                            \"supplier_name\": supplier['name'],\n                            \"price\": None,\n                            \"status\": ItemStatus.NOT_FOUND.value,\n                            \"found_at\": datetime.now(timezone.utc).isoformat()\n                        }\n                        await db.prices.insert_one(price_doc)\n                    \n                    # Delay between searches\n                    await asyncio.sleep(0.7)\n                    \n                except Exception as e:\n                    logger.error(f\"Error searching {supplier['name']}: {str(e)}\")\n                    supplier_prices[supplier['name']] = \"ERRO\"\n                    \n                    # Log error\n                    log_doc = {\n                        \"id\": str(uuid.uuid4()),\n                        \"job_id\": job_id,\n                        \"supplier_id\": supplier['id'],\n                        \"level\": \"ERROR\",\n                        \"message\": f\"Error searching item {item['ref_id']}: {str(e)}\",\n                        \"created_at\": datetime.now(timezone.utc).isoformat()\n                    }\n                    await db.logs.insert_one(log_doc)\n            \n            # Calculate savings\n            economia_euro = None\n            economia_percent = None\n            item_status = ItemStatus.NOT_FOUND.value\n            \n            if best_price is not None:\n                economia_euro = item['meu_preco'] - best_price\n                economia_percent = (economia_euro / item['meu_preco']) * 100\n                \n                # Check if meets threshold\n                if economia_euro >= job['threshold_euro'] or economia_percent >= job['threshold_percent']:\n                    item_status = ItemStatus.FOUND.value\n                    found += 1\n                    total_savings += economia_euro\n            \n            # Update item with results\n            await db.job_items.update_one(\n                {\"id\": item['id']},\n                {\"$set\": {\n                    \"melhor_preco\": best_price,\n                    \"melhor_fornecedor\": best_supplier,\n                    \"economia_euro\": economia_euro,\n                    \"economia_percent\": economia_percent,\n                    \"status\": item_status,\n                    \"supplier_prices\": supplier_prices\n                }}\n            )\n            \n            processed += 1\n            \n            # Update job progress\n            await db.jobs.update_one(\n                {\"id\": job_id},\n                {\"$set\": {\n                    \"processed_items\": processed,\n                    \"found_items\": found,\n                    \"total_savings\": total_savings\n                }}\n            )\n        \n        # Cleanup - close all browser sessions\n        for supplier in suppliers:\n            await scraper_service.cleanup_supplier(supplier['id'])\n        \n        # Mark job as completed\n        await db.jobs.update_one(\n            {\"id\": job_id},\n            {\"$set\": {\n                \"status\": JobStatus.COMPLETED.value,\n                \"completed_at\": datetime.now(timezone.utc).isoformat()\n            }}\n        )\n        \n        logger.info(f\"Job {job_id} completed. Processed: {processed}, Found: {found}, Savings: \u20ac{total_savings:.2f}\")\n        \n    except Exception as e:\n        logger.error(f\"Job {job_id} failed: {str(e)}\")\n        await db.jobs.update_one(\n            {\"id\": job_id},\n            {\"$set\": {\n                \"status\": JobStatus.FAILED.value,\n                \"error_message\": str(e),\n                \"completed_at\": datetime.now(timezone.utc).isoformat()\n            }}\n        )\n\n@api_router.get(\"/jobs\", response_model=List[Job])\nasync def get_jobs():\n    \"\"\"Get all jobs\"\"\"\n    jobs = await db.jobs.find({}, {\"_id\": 0}).sort(\"created_at\", -1).to_list(100)\n    return [Job(**job) for job in jobs]\n\n@api_router.get(\"/jobs/{job_id}\", response_model=Job)\nasync def get_job(job_id: str):\n    \"\"\"Get job details\"\"\"\n    job = await db.jobs.find_one({\"id\": job_id}, {\"_id\": 0})\n    if not job:\n        raise HTTPException(status_code=404, detail=\"Job not found\")\n    return Job(**job)\n\n@api_router.get(\"/jobs/{job_id}/progress\", response_model=JobProgress)\nasync def get_job_progress(job_id: str):\n    \"\"\"Get job progress\"\"\"\n    job = await db.jobs.find_one({\"id\": job_id}, {\"_id\": 0})\n    if not job:\n        raise HTTPException(status_code=404, detail=\"Job not found\")\n    \n    progress_percent = (job['processed_items'] / job['total_items'] * 100) if job['total_items'] > 0 else 0\n    \n    return JobProgress(\n        job_id=job_id,\n        status=JobStatus(job['status']),\n        total_items=job['total_items'],\n        processed_items=job['processed_items'],\n        found_items=job['found_items'],\n        progress_percent=round(progress_percent, 1)\n    )\n\n@api_router.get(\"/jobs/{job_id}/results\")\nasync def get_job_results(job_id: str):\n    \"\"\"Get job results\"\"\"\n    items = await db.job_items.find({\"job_id\": job_id}, {\"_id\": 0}).to_list(None)\n    return items\n\n@api_router.get(\"/jobs/{job_id}/export\")\nasync def export_job_results(job_id: str):\n    \"\"\"Export job results as Excel\"\"\"\n    job = await db.jobs.find_one({\"id\": job_id}, {\"_id\": 0})\n    if not job:\n        raise HTTPException(status_code=404, detail=\"Job not found\")\n    \n    items = await db.job_items.find({\"job_id\": job_id}, {\"_id\": 0}).to_list(None)\n    suppliers = await db.suppliers.find({\"is_active\": True}, {\"_id\": 0}).to_list(None)\n    supplier_names = [s['name'] for s in suppliers]\n    \n    try:\n        excel_bytes = excel_service.generate_results(job, items, supplier_names)\n        \n        # Return as downloadable file\n        return StreamingResponse(\n            BytesIO(excel_bytes),\n            media_type=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\",\n            headers={\n                \"Content-Disposition\": f\"attachment; filename=results_{job_id[:8]}.xlsx\"\n            }\n        )\n    except Exception as e:\n        logger.error(f\"Export error: {str(e)}\")\n        raise HTTPException(status_code=500, detail=str(e))\n\n# ============= LOGS =============\n\n@api_router.get(\"/logs\")\nasync def get_logs(job_id: Optional[str] = None, limit: int = 100):\n    \"\"\"Get logs\"\"\"\n    query = {}\n    if job_id:\n        query[\"job_id\"] = job_id\n    \n    logs = await db.logs.find(query, {\"_id\": 0}).sort(\"created_at\", -1).limit(limit).to_list(limit)\n    return logs\n\n# ============= DASHBOARD STATS =============\n\n@api_router.get(\"/stats\")\nasync def get_stats():\n    \"\"\"Get dashboard statistics\"\"\"\n    total_jobs = await db.jobs.count_documents({})\n    completed_jobs = await db.jobs.count_documents({\"status\": JobStatus.COMPLETED.value})\n    active_suppliers = await db.suppliers.count_documents({\"is_active\": True})\n    \n    # Calculate total savings from completed jobs\n    pipeline = [\n        {\"$match\": {\"status\": JobStatus.COMPLETED.value}},\n        {\"$group\": {\"_id\": None, \"total\": {\"$sum\": \"$total_savings\"}}}\n    ]\n    savings_result = await db.jobs.aggregate(pipeline).to_list(None)\n    total_savings = savings_result[0]['total'] if savings_result else 0.0\n    \n    # Get recent jobs\n    recent_jobs = await db.jobs.find({}, {\"_id\": 0}).sort(\"created_at\", -1).limit(5).to_list(5)\n    \n    return {\n        \"total_jobs\": total_jobs,\n        \"completed_jobs\": completed_jobs,\n        \"active_suppliers\": active_suppliers,\n        \"total_savings\": round(total_savings, 2),\n        \"recent_jobs\": recent_jobs\n    }\n\n# Include router\napp.include_router(api_router)\n\napp.add_middleware(\n    CORSMiddleware,\n    allow_credentials=True,\n    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),\n    allow_methods=[\"*\"],\n    allow_headers=[\"*\"],\n)\n\n@app.on_event(\"shutdown\")\nasync def shutdown_db_client():\n    client.close()\n