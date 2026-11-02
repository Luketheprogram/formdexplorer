"""Bounded background maintenance inside the existing application trust boundary.

No credentials are copied into another service. Each WSGI process can start one
daemon; the PostgreSQL maintenance lock elects a single active cycle. Durable
job leases recover work after a web-worker restart. Management commands and
tests never start this runtime unless WSGI is explicitly imported and enabled.
"""

import logging
import threading
import time

from django.conf import settings
from django.core.management import call_command
from django.db import close_old_connections

logger = logging.getLogger(__name__)
_thread = None
_guard = threading.Lock()


def cycle():
    close_old_connections()
    try:
        call_command("research_maintenance", verbosity=0)
    finally:
        close_old_connections()


def _loop():
    time.sleep(10)  # Let the web worker finish booting first.
    while True:
        started = time.monotonic()
        try:
            cycle()
        except Exception as exc:
            # Operational details are retained in staff-only job records. Do
            # not put connection strings, SQL parameters or customer data here.
            logger.error("Research maintenance cycle failed (%s)", type(exc).__name__)
        time.sleep(max(5, 300 - (time.monotonic() - started)))


def start():
    global _thread
    if not settings.RESEARCH_MAINTENANCE_ENABLED:
        return None
    with _guard:
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(
                target=_loop, name="research-maintenance", daemon=True
            )
            _thread.start()
    return _thread
