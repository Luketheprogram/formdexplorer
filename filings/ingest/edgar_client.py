import time
import math
from io import BytesIO
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from threading import Lock

import requests
from django.conf import settings

BASE_URL = "https://www.sec.gov"


class RateLimiter:
    def __init__(self, rate_per_sec: float = 8.0):
        self.min_interval = 1.0 / rate_per_sec
        self._last = 0.0
        self._lock = Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delta = now - self._last
            if delta < self.min_interval:
                time.sleep(self.min_interval - delta)
            self._last = time.monotonic()


def retry_after_seconds(response):
    value = response.headers.get("Retry-After", "") if response is not None else ""
    try:
        seconds = float(value)
        return max(0, seconds) if math.isfinite(seconds) else 0
    except ValueError:
        try:
            return max(0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return 0


class EdgarClient:
    def __init__(self, user_agent: str | None = None, rate_per_sec: float = 8.0):
        self.user_agent = user_agent or settings.EDGAR_USER_AGENT
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept-Encoding": "gzip, deflate",
                "Host": "www.sec.gov",
            }
        )
        self.limiter = RateLimiter(rate_per_sec)

    def get(self, path: str, **kwargs) -> requests.Response:
        url = path if path.startswith("https://www.sec.gov/") else f"{BASE_URL}{path}"
        if not path.startswith(("/", "https://www.sec.gov/")) or path.startswith("//"):
            raise ValueError("Only SEC archive URLs are supported")
        # Bounded retry of transport/temporary server failures. Permanent failures
        # reach the durable queue immediately; do not hammer 403/404 responses.
        for attempt in range(3):
            self.limiter.wait()
            try:
                resp = self.session.get(url, timeout=30, **kwargs)
                resp.raise_for_status()
                return resp
            except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
                response = getattr(exc, "response", None)
                temporary = response is None or response.status_code in (408, 429, 500, 502, 503, 504)
                delay = max(2 ** attempt, retry_after_seconds(response))
                if response is not None:
                    response.close()
                if not temporary or attempt == 2 or delay > 60:
                    raise
                time.sleep(delay)

    def get_text(self, path: str) -> str:
        return self.get_bytes(path).decode("utf-8-sig")

    def get_bytes(self, path: str) -> bytes:
        # Large/malformed responses become visible held work instead of exhausting
        # a worker or filling the database. No truncation is stored as a filing.
        response = self.get(path, stream=True)
        content = BytesIO()
        try:
            for chunk in response.iter_content(chunk_size=65536):
                if content.tell() + len(chunk) > 64 * 1024 * 1024:
                    raise ValueError("SEC document exceeds the 64 MiB ingestion limit")
                content.write(chunk)
            return content.getvalue()
        finally:
            response.close()
