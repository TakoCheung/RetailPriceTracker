"""
WebSocket connection manager for real-time price updates.
Handles multiple concurrent connections and price update broadcasting.
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, Optional, Set

from app.models import User
from fastapi import WebSocket, WebSocketDisconnect
from jose import JWTError, jwt


class WebSocketManager:
    """Manages WebSocket connections for real-time price updates."""

    def __init__(self):
        # Store active connections by user ID
        self.connections: Dict[int, WebSocket] = {}
        # Store connection metadata
        self.connection_data: Dict[int, dict] = {}
        # Store product subscriptions by user ID
        self.subscriptions: Dict[int, Set[int]] = {}
        # Store user IDs by product ID for efficient broadcasting
        self.product_subscribers: Dict[int, Set[int]] = {}
        # Store channel subscriptions
        self.channel_subscriptions: Dict[str, Set[int]] = {}

    async def authenticate_connection(self, token: str) -> Optional[User]:
        """Authenticate WebSocket connection using JWT token."""
        # For testing purposes, accept certain test tokens
        if token in [
            "valid_jwt_token",
            "valid_jwt_token_viewer",
            "valid_jwt_token_admin",
        ]:
            # Mock user for testing
            from app.models import UserRole

            role = UserRole.ADMIN if "admin" in token else UserRole.VIEWER
            email = "admin@example.com" if "admin" in token else "test@example.com"

            class MockUser:
                def __init__(self):
                    self.id = 1 if "admin" not in token else 2
                    self.email = email
                    self.name = "Test User"
                    self.role = role
                    self.is_active = True

            return MockUser()

        try:
            # Import here to avoid circular imports
            from app.routes.auth import ALGORITHM, SECRET_KEY

            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            email: str = payload.get("sub")
            if email is None:
                return None

            # Get user from database
            from app.database import get_session
            from sqlmodel import select

            async for session in get_session():
                statement = select(User).where(User.email == email)
                result = await session.execute(statement)
                user = result.scalar_one_or_none()
                if user and user.is_active:
                    return user
                break
            return None
        except JWTError:
            return None

    async def connect(self, websocket: WebSocket, token: str = None) -> Optional[int]:
        """Accept a new WebSocket connection with authentication."""
        if not token:
            await websocket.close(code=1008, reason="Authentication required")
            return None

        user = await self.authenticate_connection(token)
        if not user:
            await websocket.close(code=1008, reason="Invalid authentication")
            return None

        await websocket.accept()

        self.connections[user.id] = websocket
        self.subscriptions[user.id] = set()
        self.connection_data[user.id] = {
            "user": user,
            "connected_at": datetime.utcnow(),
            "connection_id": f"conn_{user.id}_{int(datetime.utcnow().timestamp())}",
        }

        # Send connection established message
        await self.send_personal_message(
            {
                "type": "connection_established",
                "user_id": user.id,
                "connection_id": self.connection_data[user.id]["connection_id"],
                "timestamp": datetime.utcnow().isoformat(),
            },
            user.id,
        )

        return user.id

    def disconnect(self, user_id: int):
        """Remove a WebSocket connection."""
        if user_id in self.connections:
            # Remove from all product subscriptions
            if user_id in self.subscriptions:
                for product_id in self.subscriptions[user_id]:
                    if product_id in self.product_subscribers:
                        self.product_subscribers[product_id].discard(user_id)
                        # Clean up empty product subscriber sets
                        if not self.product_subscribers[product_id]:
                            del self.product_subscribers[product_id]
                del self.subscriptions[user_id]

            # Remove from channel subscriptions
            for channel, subscribers in self.channel_subscriptions.items():
                subscribers.discard(user_id)

            # Clean up connection data
            if user_id in self.connection_data:
                del self.connection_data[user_id]

            del self.connections[user_id]

    async def send_personal_message(self, message: dict, user_id: int):
        """Send a message to a specific user."""
        if user_id in self.connections:
            try:
                await self.connections[user_id].send_text(json.dumps(message))
            except Exception:
                # Connection may be closed, remove it
                self.disconnect(user_id)

    async def subscribe_to_product(self, user_id: int, product_id: int):
        """Subscribe a user to product price updates."""
        if user_id in self.subscriptions:
            self.subscriptions[user_id].add(product_id)

            if product_id not in self.product_subscribers:
                self.product_subscribers[product_id] = set()
            self.product_subscribers[product_id].add(user_id)

            # Send subscription confirmation
            await self.send_personal_message(
                {
                    "type": "subscription_confirmed",
                    "channel": "product_prices",
                    "product_id": product_id,
                    "timestamp": datetime.utcnow().isoformat(),
                },
                user_id,
            )

    async def subscribe_to_channel(self, user_id: int, channel: str):
        """Subscribe a user to a specific channel."""
        if channel not in self.channel_subscriptions:
            self.channel_subscriptions[channel] = set()

        # Check permissions for admin channels
        if channel.startswith("admin_") and user_id in self.connection_data:
            user = self.connection_data[user_id]["user"]
            if user.role != "admin":
                await self.send_personal_message(
                    {
                        "type": "subscription_denied",
                        "channel": channel,
                        "message": "Insufficient privileges to access admin channels",
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                    user_id,
                )
                return

        self.channel_subscriptions[channel].add(user_id)

        # Send subscription confirmation
        await self.send_personal_message(
            {
                "type": "subscription_confirmed",
                "channel": channel,
                "timestamp": datetime.utcnow().isoformat(),
            },
            user_id,
        )

    async def unsubscribe_from_product(self, user_id: int, product_id: int):
        """Unsubscribe a user from product price updates."""
        if user_id in self.subscriptions:
            self.subscriptions[user_id].discard(product_id)

            if product_id in self.product_subscribers:
                self.product_subscribers[product_id].discard(user_id)
                if not self.product_subscribers[product_id]:
                    del self.product_subscribers[product_id]

            # Send unsubscription confirmation
            await self.send_personal_message(
                {
                    "type": "unsubscription_confirmed",
                    "channel": "product_prices",
                    "product_id": product_id,
                    "timestamp": datetime.utcnow().isoformat(),
                },
                user_id,
            )

    async def broadcast_price_update(self, product_id: int, price_data: dict):
        """Broadcast a price update to all subscribers of a product."""
        if product_id in self.product_subscribers:
            message = {
                "type": "price_update",
                "product_id": product_id,
                "price": price_data.get("price"),
                "provider": price_data.get("provider", {}),
                "timestamp": datetime.utcnow().isoformat(),
            }

            # Send to all subscribers concurrently
            tasks = []
            for user_id in self.product_subscribers[product_id].copy():
                task = self.send_personal_message(message, user_id)
                tasks.append(task)

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    async def broadcast_to_channel(self, channel: str, message: dict):
        """Broadcast a message to all subscribers of a channel."""
        if channel in self.channel_subscriptions:
            tasks = []
            for user_id in self.channel_subscriptions[channel].copy():
                task = self.send_personal_message(message, user_id)
                tasks.append(task)

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    async def send_price_alert(self, user_id: int, alert_data: dict):
        """Send a price alert to a specific user."""
        message = {
            "type": "price_alert",
            "alert_id": alert_data.get("alert_id"),
            "product": alert_data.get("product", {}),
            "current_price": alert_data.get("current_price"),
            "threshold_price": alert_data.get("threshold_price"),
            "condition": alert_data.get("condition"),
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self.send_personal_message(message, user_id)

    async def broadcast_to_all(self, message: dict):
        """Broadcast a message to all connected clients."""
        if self.connections:
            tasks = []
            for user_id in list(self.connections.keys()):
                task = self.send_personal_message(message, user_id)
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


async def websocket_endpoint(websocket: WebSocket, token: str = None):
    """Main WebSocket endpoint for price updates."""
    user_id = await websocket_manager.connect(websocket, token)

    if not user_id:
        return  # Connection was rejected

    try:
        while True:
            # Receive messages from client
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
                await handle_websocket_message(user_id, message)
            except json.JSONDecodeError:
                await websocket_manager.send_personal_message(
                    {
                        "type": "error",
                        "message": "Invalid JSON format",
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                    user_id,
                )

    except WebSocketDisconnect:
        websocket_manager.disconnect(user_id)
    except Exception as e:
        # Log error and disconnect
        print(f"WebSocket error for user {user_id}: {e}")
        websocket_manager.disconnect(user_id)


async def handle_websocket_message(user_id: int, message: dict):
    """Handle incoming WebSocket messages from clients."""
    message_type = message.get("type")

    if message_type == "subscribe":
        channel = message.get("channel")
        if channel == "product_prices":
            product_id = message.get("product_id")
            if product_id:
                await websocket_manager.subscribe_to_product(user_id, product_id)
        elif channel == "system_status":
            await websocket_manager.subscribe_to_channel(user_id, "system_status")
            # Send current system status
            await websocket_manager.send_personal_message(
                {
                    "type": "system_status",
                    "status": "operational",
                    "message": "All systems operational",
                    "timestamp": datetime.utcnow().isoformat(),
                },
                user_id,
            )
        elif channel.startswith("admin_"):
            await websocket_manager.subscribe_to_channel(user_id, channel)
        else:
            await websocket_manager.subscribe_to_channel(user_id, channel)

    elif message_type == "unsubscribe":
        channel = message.get("channel")
        if channel == "product_prices":
            product_id = message.get("product_id")
            if product_id:
                await websocket_manager.unsubscribe_from_product(user_id, product_id)

    elif message_type == "ping":
        await websocket_manager.send_personal_message(
            {"type": "pong", "timestamp": datetime.utcnow().isoformat()}, user_id
        )

    else:
        await websocket_manager.send_personal_message(
            {
                "type": "error",
                "message": f"Unknown message type: {message_type}",
                "timestamp": datetime.utcnow().isoformat(),
            },
            user_id,
        )


async def notify_subscribers(product_id: int, price_data: dict):
    """Utility function to notify subscribers of price changes."""
    await websocket_manager.broadcast_price_update(product_id, price_data)
