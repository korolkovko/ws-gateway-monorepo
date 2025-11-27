import redis.asyncio as redis
from typing import Optional, Dict, Any, List
import json
from datetime import datetime
import structlog

from src.config import settings

logger = structlog.get_logger()


class RedisClient:
    def __init__(self):
        self.redis: Optional[redis.Redis] = None

    async def connect(self):
        """Initialize Redis connection"""
        self.redis = await redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True
        )

    async def disconnect(self):
        """Close Redis connection"""
        if self.redis:
            await self.redis.close()

    async def is_connected(self) -> bool:
        """Check if Redis is connected"""
        try:
            await self.redis.ping()
            return True
        except:
            return False

    # Kiosk info methods
    async def create_kiosk(self, kiosk_id: str, token: str, name: str = "") -> bool:
        """Create a new kiosk"""
        kiosk_info = {
            "id": kiosk_id,
            "name": name or kiosk_id,
            "enabled": "true",
            "created_at": datetime.utcnow().isoformat()
        }

        await self.redis.hset(f"kiosk:{kiosk_id}:info", mapping=kiosk_info)
        await self.redis.set(f"kiosk:{kiosk_id}:token", token)
        await self.redis.set(f"kiosk:{kiosk_id}:status", "offline")
        # Add to all_kiosks SET for efficient listing
        await self.redis.sadd("all_kiosks", kiosk_id)
        return True

    async def get_kiosk_info(self, kiosk_id: str) -> Optional[Dict[str, Any]]:
        """Get kiosk information"""
        info = await self.redis.hgetall(f"kiosk:{kiosk_id}:info")
        if not info:
            return None
        return info

    async def get_kiosk_token(self, kiosk_id: str) -> Optional[str]:
        """Get kiosk JWT token"""
        return await self.redis.get(f"kiosk:{kiosk_id}:token")

    async def update_kiosk_token(self, kiosk_id: str, token: str) -> bool:
        """Update kiosk JWT token"""
        exists = await self.redis.exists(f"kiosk:{kiosk_id}:info")
        if not exists:
            return False
        await self.redis.set(f"kiosk:{kiosk_id}:token", token)
        return True

    async def delete_kiosk(self, kiosk_id: str) -> bool:
        """Delete a kiosk and all its data"""
        pipe = self.redis.pipeline()
        pipe.delete(f"kiosk:{kiosk_id}:info")
        pipe.delete(f"kiosk:{kiosk_id}:token")
        pipe.delete(f"kiosk:{kiosk_id}:status")
        pipe.delete(f"kiosk:{kiosk_id}:connection_status")
        pipe.delete(f"kiosk:{kiosk_id}:connected_at")
        pipe.srem("active_kiosks", kiosk_id)
        pipe.srem("all_kiosks", kiosk_id)  # Remove from all_kiosks SET
        await pipe.execute()
        return True

    async def enable_kiosk(self, kiosk_id: str) -> bool:
        """Enable a kiosk"""
        exists = await self.redis.exists(f"kiosk:{kiosk_id}:info")
        if not exists:
            return False
        await self.redis.hset(f"kiosk:{kiosk_id}:info", "enabled", "true")
        return True

    async def disable_kiosk(self, kiosk_id: str) -> bool:
        """Disable a kiosk"""
        exists = await self.redis.exists(f"kiosk:{kiosk_id}:info")
        if not exists:
            return False
        await self.redis.hset(f"kiosk:{kiosk_id}:info", "enabled", "false")
        return True

    async def update_kiosk_name(self, kiosk_id: str, name: str) -> bool:
        """Update kiosk name"""
        exists = await self.redis.exists(f"kiosk:{kiosk_id}:info")
        if not exists:
            return False
        await self.redis.hset(f"kiosk:{kiosk_id}:info", "name", name)
        return True

    async def is_kiosk_enabled(self, kiosk_id: str) -> bool:
        """Check if kiosk is enabled"""
        enabled = await self.redis.hget(f"kiosk:{kiosk_id}:info", "enabled")
        return enabled == "true"

    async def kiosk_exists(self, kiosk_id: str) -> bool:
        """Check if kiosk exists"""
        key = f"kiosk:{kiosk_id}:info"
        exists_count = await self.redis.exists(key)
        logger.debug("kiosk_exists_check", kiosk_id=kiosk_id, key=key, exists_count=exists_count)
        return exists_count > 0

    # Kiosk status methods
    async def set_kiosk_online(self, kiosk_id: str):
        """Mark kiosk as online"""
        await self.redis.set(f"kiosk:{kiosk_id}:status", "online")
        await self.redis.set(f"kiosk:{kiosk_id}:connection_status", "online")
        await self.redis.sadd("active_kiosks", kiosk_id)

    async def set_kiosk_offline(self, kiosk_id: str):
        """Mark kiosk as offline"""
        await self.redis.set(f"kiosk:{kiosk_id}:status", "offline")
        await self.redis.delete(f"kiosk:{kiosk_id}:connection_status")
        await self.redis.srem("active_kiosks", kiosk_id)

    async def set_kiosk_stale(self, kiosk_id: str):
        """Mark kiosk connection as stale (not responding to ping)"""
        await self.redis.set(f"kiosk:{kiosk_id}:connection_status", "stale")

    async def get_kiosk_connection_status(self, kiosk_id: str) -> str:
        """Get kiosk connection status (online|stale|None)"""
        status = await self.redis.get(f"kiosk:{kiosk_id}:connection_status")
        return status if status else "offline"

    async def is_kiosk_online(self, kiosk_id: str) -> bool:
        """Check if kiosk is online"""
        status = await self.redis.get(f"kiosk:{kiosk_id}:status")
        return status == "online"

    async def get_online_kiosks(self) -> List[str]:
        """Get list of online kiosks"""
        kiosks = await self.redis.smembers("active_kiosks")
        return list(kiosks) if kiosks else []

    async def get_all_kiosks(self) -> List[Dict[str, Any]]:
        """Get all kiosks with their info and status"""
        # Use all_kiosks SET instead of KEYS for better performance
        kiosk_ids = await self.redis.smembers("all_kiosks")
        kiosks = []

        for kiosk_id in kiosk_ids:
            info = await self.get_kiosk_info(kiosk_id)
            if info:
                status = await self.redis.get(f"kiosk:{kiosk_id}:status")
                info['status'] = status or 'offline'
                kiosks.append(info)

        return kiosks

    # Stats methods
    async def increment_requests(self):
        """Increment total requests counter"""
        await self.redis.incr("stats:requests_total")

    async def increment_errors(self):
        """Increment total errors counter"""
        await self.redis.incr("stats:errors_total")

    async def add_latency(self, latency: float):
        """Add latency sample for averaging"""
        pipe = self.redis.pipeline()
        pipe.incrbyfloat("stats:latency_sum", latency)
        pipe.incr("stats:latency_count")
        await pipe.execute()

    async def get_stats(self) -> Dict[str, Any]:
        """Get server statistics"""
        pipe = self.redis.pipeline()
        pipe.get("stats:requests_total")
        pipe.get("stats:errors_total")
        pipe.get("stats:latency_sum")
        pipe.get("stats:latency_count")
        results = await pipe.execute()

        requests_total = int(results[0] or 0)
        errors_total = int(results[1] or 0)
        latency_sum = float(results[2] or 0)
        latency_count = int(results[3] or 0)

        avg_latency = (latency_sum / latency_count) if latency_count > 0 else 0

        return {
            "requests_total": requests_total,
            "errors_total": errors_total,
            "avg_latency": round(avg_latency, 3),
        }

    async def log_connection_event(self, kiosk_id: str, event: str):
        """Log kiosk connection/disconnection event"""
        import time
        import json

        event_data = json.dumps({
            "kiosk_id": kiosk_id,
            "event": event,  # "connected" or "disconnected"
            "timestamp": time.time()
        })

        # Add to sorted set with timestamp as score (keeps last 100 events)
        await self.redis.zadd("connection_history", {event_data: time.time()})

        # Keep only last 100 events
        await self.redis.zremrangebyrank("connection_history", 0, -101)

    async def get_connection_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent connection history"""
        import json

        # Get last N events (most recent first)
        events = await self.redis.zrevrange("connection_history", 0, limit - 1)

        history = []
        for event_str in events:
            try:
                event = json.loads(event_str)
                history.append(event)
            except:
                pass

        return history


# Global Redis client instance
redis_client = RedisClient()
