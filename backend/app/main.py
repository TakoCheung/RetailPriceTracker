from datetime import datetime

from fastapi import FastAPI, WebSocket

from .database import init_db
from .routes import (
    alerts,
    analytics,
    auth,
    monitoring,
    notifications,
    preferences,
    price_records,
    products,
    providers,
    search,
    users,
)
from .utils.websocket import websocket_endpoint

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
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(
    price_records.router, prefix="/api/price-records", tags=["price-records"]
)
app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"])
app.include_router(preferences.router, prefix="/api/preferences", tags=["preferences"])
app.include_router(analytics.router, prefix="/api", tags=["analytics"])
app.include_router(search.router, prefix="/api/search", tags=["search"])
app.include_router(monitoring.router, tags=["monitoring"])
app.include_router(notifications.router, tags=["notifications"])
app.include_router(auth.router)


# Add WebSocket route
@app.websocket("/ws")
async def websocket_route(websocket: WebSocket, client_id: str = None):
    """WebSocket endpoint for real-time price updates."""
    await websocket_endpoint(websocket, client_id)


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    await init_db()
