"""Background refresher.

Runs in a daemon thread for the lifetime of the app: refreshes the Bazaar cache
and appends a history snapshot once per interval, and prunes old history
periodically. Keeping this server-side means every client request is served from
a warm cache instead of triggering its own Hypixel fetch.
"""

import threading
import time

from . import cache, history

# How often to refresh + snapshot. Matches the Bazaar's ~60s update cadence.
INTERVAL_SECONDS = cache.REFRESH_INTERVAL
# Prune old history roughly once an hour.
PRUNE_EVERY_SECONDS = 3600

_thread = None
_stop = threading.Event()


def _loop():
    last_prune = 0.0
    while not _stop.is_set():
        try:
            payload = cache.refresh(force=True)
            if payload is not None:
                history.record_snapshot(payload)
            now = time.time()
            if now - last_prune >= PRUNE_EVERY_SECONDS:
                history.prune()
                last_prune = now
        except Exception:  # noqa: BLE001 - the loop must never die
            pass
        _stop.wait(INTERVAL_SECONDS)


def start():
    """Initialize history storage and launch the background loop (idempotent)."""
    global _thread
    history.init_db()
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="bazaar-refresher", daemon=True)
    _thread.start()


def stop():
    _stop.set()
