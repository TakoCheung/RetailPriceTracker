"""
Redis-based caching service for performance optimization.
Provides a unified interface for caching frequently accessed data.
"""

import json
import logging
import os
from typing import Any, Optional

import redis.asyncio as redis

logger = logging.getLogger(__name__)

# Redis configuration from environment variables
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Module-level redis client for testing purposes
redis_client = None


class CacheService:
    """Redis-based caching service with configurable TTL and serialization."""

    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self._connected = False

    async def connect(self):
        """Establish connection to Redis."""
        try:
            # Use module-level client if available (for testing), otherwise create new one
            global redis_client
            if redis_client is not None:
                self.redis_client = redis_client
            else:
                self.redis_client = redis.from_url(REDIS_URL, decode_responses=True)
            # Test the connection
            await self.redis_client.ping()
            self._connected = True
            logger.info("Connected to Redis cache service")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self._connected = False

    async def disconnect(self):
        """Close Redis connection."""
        if self.redis_client:
            await self.redis_client.aclose()
            self._connected = False
            logger.info("Disconnected from Redis cache service")

    async def set(self, key: str, value: Any, expire: int = 3600) -> None:
        """Set a value in cache with expiration time"""
        try:
            await self.connect()
            if hasattr(value, "model_dump"):
                # Handle Pydantic models
                serializable_value = value.model_dump(mode="json")
            else:
                serializable_value = value
            await self.redis_client.set(
                key, json.dumps(serializable_value, default=str), ex=expire
            )
        except Exception as e:
            logger.error(f"Error setting cache: {e}")
        finally:
            await self.disconnect()

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        try:
            await self.connect()
            value = await self.redis_client.get(key)
            if value:
                # Ensure we're working with string data
                if isinstance(value, bytes):
                    value = value.decode("utf-8")
                # Parse JSON
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Error getting from cache: {e}")
            return None
        finally:
            await self.disconnect()

    async def delete(self, key: str) -> bool:
        """Delete a key from cache"""
        try:
            await self.connect()
            result = await self.redis_client.delete(key)
            return bool(result)
        except Exception as e:
            logger.error(f"Error deleting from cache: {e}")
            return False
        finally:
            await self.disconnect()

    async def exists(self, key: str) -> bool:
        """Check if a key exists in cache"""
        try:
            await self.connect()
            result = await self.redis_client.exists(key)
            return bool(result)
        except Exception as e:
            logger.error(f"Error checking key existence: {e}")
            return False
        finally:
            await self.disconnect()

    async def flush_all(self) -> bool:
        """Clear all cached data"""
        try:
            await self.connect()
            await self.redis_client.flushall()
            return True
        except Exception as e:
            logger.error(f"Error flushing cache: {e}")
            return False
        finally:
            await self.disconnect()

    async def set_many(self, data: dict[str, Any], expire: int = 3600) -> None:
        """Set multiple key-value pairs in cache"""
        try:
            await self.connect()
            pipe = self.redis_client.pipeline()
            for key, value in data.items():
                if hasattr(value, "model_dump"):
                    serializable_value = value.model_dump(mode="json")
                else:
                    serializable_value = value
                pipe.set(key, json.dumps(serializable_value, default=str), ex=expire)
            await pipe.execute()
        except Exception as e:
            logger.error(f"Error setting multiple cache values: {e}")
        finally:
            await self.disconnect()

    # Product-specific cache methods
    async def get_cached_product(self, product_id: int) -> dict | None:
        """Get cached product data by ID"""
        cache_key = f"product:{product_id}"
        return await self.get(cache_key)

    async def cache_product(
        self, product_id: int, product_data: dict, ttl_seconds: int = 1800
    ) -> None:
        """Cache product data with TTL"""
        cache_key = f"product:{product_id}"
        await self.set(cache_key, product_data, expire=ttl_seconds)

    async def invalidate_product(self, product_id: int) -> None:
        """Invalidate cached product data"""
        cache_key = f"product:{product_id}"
        await self.delete(cache_key)

    # Search-specific cache methods
    async def get_cached_search_results(self, cache_key: str) -> dict | None:
        """Get cached search results by key"""
        return await self.get(f"search:{cache_key}")

    async def cache_search_results(
        self, cache_key: str, results: dict, ttl_seconds: int = 300
    ) -> None:
        """Cache search results with TTL (shorter TTL for search results)"""
        await self.set(f"search:{cache_key}", results, expire=ttl_seconds)

    async def invalidate_search_cache(self, pattern: str = "search:*") -> None:
        """Invalidate cached search results matching pattern"""
        try:
            await self.connect()
            keys = await self.redis_client.keys(pattern)
            if keys:
                await self.redis_client.delete(*keys)
        except Exception as e:
            logger.error(f"Error invalidating search cache: {e}")
        finally:
            await self.disconnect()

    # Monitoring and statistics methods
    async def get_cache_stats(self) -> dict:
        """Get Redis cache statistics for monitoring"""
        try:
            await self.connect()
            info = await self.redis_client.info()

            # Extract relevant cache statistics
            stats = {
                "connected_clients": info.get("connected_clients", 0),
                "used_memory": info.get("used_memory", 0),
                "used_memory_human": info.get("used_memory_human", "0B"),
                "used_memory_peak": info.get("used_memory_peak", 0),
                "used_memory_peak_human": info.get("used_memory_peak_human", "0B"),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "expired_keys": info.get("expired_keys", 0),
                "evicted_keys": info.get("evicted_keys", 0),
                "total_commands_processed": info.get("total_commands_processed", 0),
                "instantaneous_ops_per_sec": info.get("instantaneous_ops_per_sec", 0),
                "uptime_in_seconds": info.get("uptime_in_seconds", 0),
                "redis_version": info.get("redis_version", "unknown"),
                "redis_mode": info.get("redis_mode", "standalone"),
                "role": info.get("role", "master"),
            }

            # Calculate hit ratio
            hits = stats["keyspace_hits"]
            misses = stats["keyspace_misses"]
            total_requests = hits + misses
            if total_requests > 0:
                stats["hit_ratio"] = hits / total_requests
            else:
                stats["hit_ratio"] = 0.0

            return stats
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {
                "connected_clients": 0,
                "used_memory": 0,
                "used_memory_human": "0B",
                "used_memory_peak": 0,
                "used_memory_peak_human": "0B",
                "keyspace_hits": 0,
                "keyspace_misses": 0,
                "expired_keys": 0,
                "evicted_keys": 0,
                "total_commands_processed": 0,
                "instantaneous_ops_per_sec": 0,
                "uptime_in_seconds": 0,
                "hit_ratio": 0.0,
                "redis_version": "unknown",
                "redis_mode": "standalone",
                "role": "master",
                "error": str(e),
            }
        finally:
            await self.disconnect()

    async def get_cache_info(self) -> dict:
        """Get detailed cache information for monitoring"""
        try:
            await self.connect()

            # Get database info
            db_info = await self.redis_client.info("keyspace")

            # Get memory info
            memory_info = await self.redis_client.info("memory")

            # Get server info
            server_info = await self.redis_client.info("server")

            # Count keys by pattern
            product_keys = len(await self.redis_client.keys("product:*"))
            search_keys = len(await self.redis_client.keys("search:*"))
            total_keys = await self.redis_client.dbsize()

            return {
                "database": db_info,
                "memory": memory_info,
                "server": server_info,
                "key_counts": {
                    "product_keys": product_keys,
                    "search_keys": search_keys,
                    "total_keys": total_keys,
                    "other_keys": max(0, total_keys - product_keys - search_keys),
                },
                "connection_status": "connected" if self._connected else "disconnected",
            }
        except Exception as e:
            logger.error(f"Error getting cache info: {e}")
            return {"error": str(e), "connection_status": "error"}
        finally:
            await self.disconnect()


# Global cache service instance
cache_service = CacheService()

# Export the class for imports
__all__ = ["CacheService", "cache_service"]
