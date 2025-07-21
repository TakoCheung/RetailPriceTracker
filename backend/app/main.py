from fastapi import FastAPI
from .routes import products, providers, alerts, preferences
from .utils import websocket

app = FastAPI(title="Retail Price Tracker")

app.include_router(products.router, prefix="/products", tags=["products"])
app.include_router(providers.router, prefix="/providers", tags=["providers"])
app.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
app.include_router(preferences.router, prefix="/preferences", tags=["preferences"])

app.add_api_websocket_route("/ws", websocket.websocket_endpoint)
