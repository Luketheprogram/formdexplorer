"""Simple IP-based rate limit for auth endpoints, backed by the Django cache.

Good enough for signup/login brute-force resistance on a single-node deploy.
Bypass: if Django cache is the dummy (local tests), the limit is a no-op."""

import time
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse


def _client_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def rate_limit(name: str, max_hits: int, window_seconds: int):
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if settings.DEBUG:
                return view(request, *args, **kwargs)
            ip = _client_ip(request)
            key = f"ratelimit:{name}:{ip}"
            now = int(time.time())
            bucket = cache.get(key) or {"start": now, "count": 0}
            if now - bucket["start"] > window_seconds:
                bucket = {"start": now, "count": 0}
            bucket["count"] += 1
            cache.set(key, bucket, timeout=window_seconds)
            if bucket["count"] > max_hits:
                resp = HttpResponse(
                    "Too many requests. Slow down and try again in a minute.",
                    status=429,
                    content_type="text/plain",
                )
                resp["Retry-After"] = str(window_seconds)
                return resp
            return view(request, *args, **kwargs)

        return wrapper

    return decorator
