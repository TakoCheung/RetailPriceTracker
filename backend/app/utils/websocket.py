"""
WebSocket connection manager for real-time price updates.
Handles multiple concurrent connections and price update broadcasting.
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, Set

from fastapi import WebSocket, WebSocketDisconnect


class WebSocketManager:
    """Manages WebSocket connections for real-time price updates."""

    def __init__(self):
        # Store active connections by client ID
        self.connections: Dict[str, WebSocket] = {}
        # Store product subscriptions by client ID
        self.subscriptions: Dict[str, Set[int]] = {}
        # Store client IDs by product ID for efficient broadcasting
        self.product_subscribers: Dict[int, Set[str]] = {}

    async def connect(self, websocket: WebSocket, client_id: str = None):
        """Accept a new WebSocket connection."""
        await websocket.accept()

        if client_id is None:
            client_id = f"client_{datetime.utcnow().timestamp()}"

        self.connections[client_id] = websocket
        self.subscriptions[client_id] = set()

        # Send welcome message
        await self.send_personal_message(
            {
                "type": "connected",
                "client_id": client_id,
                "message": "Connected to price updates",
                "timestamp": datetime.utcnow().isoformat(),
            },
            client_id,
        )

        return client_id

    def disconnect(self, client_id: str):
        """Remove a WebSocket connection."""
        if client_id in self.connections:
            # Remove from all product subscriptions
            if client_id in self.subscriptions:
                for product_id in self.subscriptions[client_id]:
                    if product_id in self.product_subscribers:
                        self.product_subscribers[product_id].discard(client_id)
                        # Clean up empty product subscriber sets
                        if not self.product_subscribers[product_id]:
                            del self.product_subscribers[product_id]
                del self.subscriptions[client_id]

            del self.connections[client_id]

    async def send_personal_message(self, message: dict, client_id: str):
        """Send a message to a specific client."""
        if client_id in self.connections:
            try:
                await self.connections[client_id].send_text(json.dumps(message))
            except Exception:
                # Connection may be closed, remove it
                self.disconnect(client_id)

    async def subscribe_to_product(self, client_id: str, product_id: int):
        """Subscribe a client to product price updates."""
        if client_id in self.subscriptions:
            self.subscriptions[client_id].add(product_id)

            if product_id not in self.product_subscribers:
                self.product_subscribers[product_id] = set()
            self.product_subscribers[product_id].add(client_id)

            # Send subscription confirmation
            await self.send_personal_message(
                {
                    "type": "subscription_confirmed",
                    "product_id": product_id,
                    "timestamp": datetime.utcnow().isoformat(),
                },
                client_id,
            )

    async def unsubscribe_from_product(self, client_id: str, product_id: int):
        """Unsubscribe a client from product price updates."""
        if client_id in self.subscriptions:
            self.subscriptions[client_id].discard(product_id)

            if product_id in self.product_subscribers:
                self.product_subscribers[product_id].discard(client_id)
                if not self.product_subscribers[product_id]:
                    del self.product_subscribers[product_id]

    async def broadcast_price_update(self, product_id: int, price_data: dict):
        """Broadcast a price update to all subscribers of a product."""
        if product_id in self.product_subscribers:
            message = {
                "type": "price_update",
                "product_id": product_id,
                "data": price_data,
                "timestamp": datetime.utcnow().isoformat(),
            }

            # Send to all subscribers concurrently
            tasks = []
            for client_id in self.product_subscribers[product_id].copy():
                task = self.send_personal_message(message, client_id)
                tasks.append(task)

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    async def broadcast_to_all(self, message: dict):
        """Broadcast a message to all connected clients."""
        if self.connections:
            tasks = []
            for client_id in list(self.connections.keys()):
                task = self.send_personal_message(message, client_id)
                tasks.append(task)

            await asyncio.gather(*tasks, return_exceptions=True)

    def get_connection_count(self) -> int:
        """Get the number of active connections."""
        return len(self.connections)

    def get_product_subscriber_count(self, product_id: int) -> int:
        """Get the number of subscribers for a specific product."""
        return len(self.product_subscribers.get(product_id, set()))


# Global WebSocket manager instance
websocket_manager = WebSocketManager()


async def websocket_endpoint(websocket: WebSocket, client_id: str = None):
    """Main WebSocket endpoint for price updates."""
    client_id = await websocket_manager.connect(websocket, client_id)

    try:
        while True:
            # Receive messages from client
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
                await handle_websocket_message(client_id, message)
            except json.JSONDecodeError:
                await websocket_manager.send_personal_message(
                    {
                        "type": "error",
                        "message": "Invalid JSON format",
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                    client_id,
                )

    except WebSocketDisconnect:
        websocket_manager.disconnect(client_id)
    except Exception as e:
        # Log error and disconnect
        print(f"WebSocket error for client {client_id}: {e}")
        websocket_manager.disconnect(client_id)


async def handle_websocket_message(client_id: str, message: dict):
    """Handle incoming WebSocket messages from clients."""
    action = message.get("action")

    if action == "subscribe":
        product_id = message.get("product_id")
        if product_id:
            await websocket_manager.subscribe_to_product(client_id, product_id)

    elif action == "unsubscribe":
        product_id = message.get("product_id")
        if product_id:
            await websocket_manager.unsubscribe_from_product(client_id, product_id)

    elif action == "ping":
        await websocket_manager.send_personal_message(
            {"type": "pong", "timestamp": datetime.utcnow().isoformat()}, client_id
        )

    else:
        await websocket_manager.send_personal_message(
            {
                "type": "error",
                "message": f"Unknown action: {action}",
                "timestamp": datetime.utcnow().isoformat(),
            },
            client_id,
        )


async def notify_subscribers(product_id: int, price_data: dict):
    """Utility function to notify subscribers of price changes."""
    await websocket_manager.broadcast_price_update(product_id, price_data)
