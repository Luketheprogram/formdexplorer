import time
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
        url = path if path.startswith("http") else f"{BASE_URL}{path}"
        self.limiter.wait()
        resp = self.session.get(url, timeout=30, **kwargs)
        resp.raise_for_status()
        return resp

    def get_text(self, path: str) -> str:
        return self.get(path).text

    def get_bytes(self, path: str) -> bytes:
        return self.get(path).content
