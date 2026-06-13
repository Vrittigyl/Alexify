"""
main.py — SAATHI FastAPI Application
======================================
Entry point for the SAATHI backend.
Phase 1: Health endpoint only. Additional endpoints added in Phase 10.

Run:
    uvicorn main:app --reload --port 8000
"""

import logging
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from db.dynamo_client import health_check

# Logging 
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("saathi")

# App 
app = FastAPI(
    title="SAATHI",
    description=(
        "Smart Anticipatory Automation for The Home Intelligence — "
        "Two-Path Architecture: Rule Engine + AWS Bedrock"
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS (allow frontend dev server)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup 
@app.on_event("startup")
async def on_startup():
    logger.info("=" * 60)
    logger.info("  SAATHI v2.0 — Starting up")
    logger.info(f"  Household ID    : {settings.household_id}")
    logger.info(f"  AWS Region      : {settings.aws_region}")
    logger.info(f"  Bedrock Mock    : {settings.bedrock_mock_mode}")
    logger.info(f"  Complexity Thr  : {settings.bedrock_complexity_threshold}")
    logger.info("=" * 60)

    dynamo_status = health_check()
    logger.info(f"  DynamoDB status : {dynamo_status['status']}")
    if dynamo_status["status"] == "connected":
        logger.info(f"  DynamoDB region : {dynamo_status['region']}")
    else:
        logger.warning(f"  DynamoDB detail : {dynamo_status.get('detail', '')}")

    logger.info("  SAATHI ready.")


# Health 
@app.get("/health", tags=["System"])
async def health():
    """
    System health check.
    Returns DynamoDB connectivity status and core configuration.
    This is the Phase 1 exit check endpoint.
    """
    dynamo = health_check()
    return {
        "status": "ok",
        "version": "2.0.0",
        "household_id": settings.household_id,
        "aws_region": settings.aws_region,
        "bedrock_mock_mode": settings.bedrock_mock_mode,
        "dynamo": dynamo["status"],
        "dynamo_detail": dynamo.get("detail") or dynamo.get("region"),
    }


# Entrypoint 
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
