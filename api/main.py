"""FastAPI application."""
from fastapi import FastAPI, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
import os
import logging

from api.routes import api_keys, proxy, balance, payment, webhooks, webapp
from api.dependencies import get_payment_engine

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="KikuAI Bot API",
    description="Backend API for KikuAI Telegram bot",
    version="0.1.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize shared Payment Engine (singleton from dependencies)
payment_engine = get_payment_engine()

# Set payment engine in routes
payment.set_payment_engine(payment_engine)
proxy.set_payment_engine(payment_engine)
webhooks.set_payment_engine(payment_engine)

# Serve webapp static files - use absolute path
webapp_path = "/app/webapp"

# Direct routes for webapp files (BEFORE routers to ensure they work)
@app.get("/webapp/dashboard.html")
async def dashboard_html():
    """Serve dashboard.html"""
    file_path = os.path.join(webapp_path, "dashboard.html")
    logger.info(f"Dashboard request: checking {file_path}, exists={os.path.exists(file_path)}")
    if os.path.exists(file_path):
        logger.info(f"Serving dashboard.html from {file_path}")
        return FileResponse(file_path, media_type="text/html")
    logger.error(f"dashboard.html not found at: {file_path}")
    raise HTTPException(status_code=404, detail=f"File not found at {file_path}")

@app.get("/webapp/manage_keys.html")
async def manage_keys_html():
    """Serve manage_keys.html"""
    file_path = os.path.join(webapp_path, "manage_keys.html")
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="text/html")
    raise HTTPException(status_code=404, detail="File not found")

@app.get("/webapp/payment.html")
async def payment_html():
    """Serve payment.html"""
    file_path = os.path.join(webapp_path, "payment.html")
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="text/html")
    raise HTTPException(status_code=404, detail="File not found")

# Note: We use direct routes instead of mount to have more control
# Mount would intercept all /webapp/* requests before our specific routes

# Register routers (AFTER webapp routes)
app.include_router(api_keys.router)
app.include_router(proxy.router)
app.include_router(balance.router)
app.include_router(payment.router)
app.include_router(webhooks.router)
app.include_router(webapp.router)

# Additional webhook mount to support /api/webhooks/paddle (without /v1)
app.add_api_route(
    "/api/webhooks/paddle",
    webhooks.handle_paddle_webhook,
    methods=["POST"],
)
app.add_api_route(
    "/api/webhooks/telegram_stars",
    webhooks.handle_telegram_stars_webhook,
    methods=["POST"],
)

@app.get("/healthz")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    # Log webapp status
    if os.path.exists(webapp_path):
        logger.info(f"Webapp available at: {webapp_path}")
        files = os.listdir(webapp_path)
        logger.info(f"Webapp files: {files}")
    else:
        logger.warning(f"Webapp directory not found at: {webapp_path}")
    # Set bot instance in notification service if available
    # (Bot instance will be set from bot/main.py if running together)
    pass
