from __future__ import annotations

import copy
import hashlib
import os
import re
import time
from typing import Any


def normalized_cache_key(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class CacheStore:
    def __init__(self) -> None:
        self.backend = "memory"
        self._store: dict[str, dict[str, Any]] = {}
        self._hits = 0
        self._misses = 0
        self._redis = None
        redis_url = os.getenv("REDIS_URL") or os.getenv("KMP_REDIS_URL")
        if redis_url:
            try:
                import redis  # type: ignore

                client = redis.from_url(redis_url, decode_responses=True)
                client.ping()
                self._redis = client
                self.backend = "redis"
            except Exception:
                self.backend = "memory"

    def make_key(self, text: str) -> str:
        return normalized_cache_key(text)

    def get(self, key: str) -> dict[str, Any] | None:
        if self._redis is not None:
            import json

            raw = self._redis.get(key)
            if raw:
                self._hits += 1
                return json.loads(raw)
            self._misses += 1
            return None

        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None
        self._hits += 1
        return copy.deepcopy(entry["value"])

    def set(self, key: str, value: dict[str, Any]) -> None:
        if self._redis is not None:
            import json

            self._redis.set(key, json.dumps(value), ex=60 * 60)
            return

        self._store[key] = {
            "created_at": time.time(),
            "value": copy.deepcopy(value),
        }

    def stats(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "entries": len(self._store) if self._redis is None else None,
            "hits": self._hits,
            "misses": self._misses,
        }

