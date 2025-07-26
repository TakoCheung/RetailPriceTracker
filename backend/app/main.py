from datetime import datetime

from fastapi import FastAPI

from .database import init_db
from .routes import alerts, preferences, price_records, products, providers
from .utils import websocket

app = FastAPI(title="Retail Price Tracker", version="1.0.0")


# Health check endpoint
@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
    }


app.include_router(products.router, prefix="/api/products", tags=["products"])
app.include_router(providers.router, prefix="/api/providers", tags=["providers"])
app.include_router(
    price_records.router, prefix="/api/price-records", tags=["price-records"]
)
app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"])
app.include_router(preferences.router, prefix="/api/preferences", tags=["preferences"])

app.add_api_websocket_route("/ws", websocket.websocket_endpoint)


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    await init_db()
