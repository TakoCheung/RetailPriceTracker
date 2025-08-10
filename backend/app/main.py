import os
from datetime import datetime

from fastapi import FastAPI, WebSocket, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .database import init_db
from .middleware.error_handler import ErrorHandlerMiddleware
from .routes import (
    admin,
    alerts,
    analytics,
    auth,
    cache,
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


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle FastAPI validation errors with custom format."""
    # Format validation error message
    error_details = []
    for error in exc.errors():
        field = " -> ".join(str(loc) for loc in error["loc"])
        message = error["msg"]
        error_details.append(f"{field}: {message}")
    
    detail_message = f"Product validation error: {'; '.join(error_details)}"
    
    return JSONResponse(
        status_code=422,
        content={
            "error_code": "VALIDATION_ERROR",
            "message": detail_message,
            "detail": detail_message,  # FastAPI standard field
            "validation_errors": [
                {
                    "loc": list(error["loc"]),
                    "msg": error["msg"],
                    "type": error["type"]
                }
                for error in exc.errors()
            ],
            "timestamp": datetime.utcnow().isoformat(),
        }
    )


# Add error handling middleware
app.add_middleware(ErrorHandlerMiddleware)


# Health check endpoint
@app.get("/api/health")
async def health_check():
    """Basic health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
    }


# Enhanced health check endpoint
@app.get("/api/health/detailed")
async def detailed_health_check():
    """Detailed health check endpoint using HealthCheckService."""
    from .database import get_session
    from .utils.health_check import HealthCheckService

    health_service = HealthCheckService()

    # Get database session (simplified for health check)
    try:
        async for session in get_session():
            result = await health_service.run_all_checks(session)
            break
    except Exception as e:
        result = {
            "timestamp": datetime.utcnow().isoformat(),
            "overall_status": "unhealthy",
            "error": str(e),
            "components": [],
        }

    status_code = 200 if result.get("overall_status") == "healthy" else 503

    from fastapi import Response

    return Response(
        content=str(result), status_code=status_code, media_type="application/json"
    )


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
app.include_router(cache.router, tags=["cache"])
app.include_router(monitoring.router, tags=["monitoring"])
app.include_router(notifications.router, tags=["notifications"])
app.include_router(auth.router)
app.include_router(admin.router)


# Add WebSocket route
@app.websocket("/ws")
async def websocket_route(websocket: WebSocket, token: str = None):
    """WebSocket endpoint for real-time price updates."""
    await websocket_endpoint(websocket, token)


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup (skip in test mode)."""
    if os.getenv("TESTING") != "1":
        await init_db()
