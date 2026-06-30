"""Shared, thread-safe Bazaar snapshot cache.

The Hypixel Bazaar API updates roughly once a minute, but the dashboard polls
both Flip and Forge modes frequently. Hitting Hypixel on every request is slow
and wasteful, so we keep a single cached snapshot and refresh it on a TTL (or in
the background, see ``app.scheduler``).

If a refresh fails (network error, timeout, non-200, ``success: false``) we keep
the last good snapshot and record the error instead of crashing callers.
"""

import threading
import time

import requests

BAZAAR_URL = "https://api.hypixel.net/v2/skyblock/bazaar"
# Seconds before a cached snapshot is considered stale and eligible for refresh.
REFRESH_INTERVAL = 60
# Hard ceiling on the Hypixel request so a hung connection can't wedge the app.
FETCH_TIMEOUT = 10

_lock = threading.Lock()
_cond = threading.Condition(_lock)
_state = {
    "data": None,        # last good Bazaar payload (dict)
    "fetched_at": None,  # epoch seconds of the last successful fetch
    "error": None,       # last error message, if any
    "updating": False,   # a refresh is currently in flight
}


def _fetch_live():
    """Fetch a fresh Bazaar payload, raising on any failure."""
    response = requests.get(BAZAAR_URL, timeout=FETCH_TIMEOUT)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success", True):
        raise ValueError("Hypixel API returned success=false")
    if not payload.get("products"):
        raise ValueError("Hypixel API returned no products")
    return payload


def refresh(force=False):
    """Refresh the cached snapshot if it is stale (or ``force`` is set).

    Returns the current (possibly stale) payload. Never raises: on failure it
    preserves the previous snapshot and stores the error message in state.

    If another thread is already fetching and we have no snapshot yet, wait for
    that in-flight refresh instead of returning ``None``.
    """
    with _cond:
        while True:
            fresh_enough = (
                _state["data"] is not None
                and _state["fetched_at"] is not None
                and (time.time() - _state["fetched_at"]) < REFRESH_INTERVAL
            )
            if fresh_enough and not force:
                return _state["data"]
            if _state["updating"]:
                _cond.wait(timeout=FETCH_TIMEOUT + 5)
                continue
            _state["updating"] = True
            break

    try:
        payload = _fetch_live()
        with _cond:
            _state["data"] = payload
            _state["fetched_at"] = time.time()
            _state["error"] = None
    except Exception as exc:  # noqa: BLE001 - we want to swallow any fetch error
        with _cond:
            _state["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        with _cond:
            _state["updating"] = False
            _cond.notify_all()

    with _cond:
        return _state["data"]


def get_data(force=False):
    """Return the cached Bazaar payload, refreshing on demand when stale."""
    data = refresh(force=force)
    if data is None:
        # First call and the initial fetch failed; surface a clear error.
        raise RuntimeError(
            "Bazaar data is unavailable: " + (status().get("error") or "unknown error")
        )
    return data


def status():
    """Lightweight snapshot metadata for health/observability endpoints."""
    with _cond:
        fetched_at = _state["fetched_at"]
        age = (time.time() - fetched_at) if fetched_at else None
        return {
            "fetched_at": fetched_at,
            "age_seconds": round(age, 1) if age is not None else None,
            "stale": (age is None) or (age >= REFRESH_INTERVAL),
            "error": _state["error"],
            "has_data": _state["data"] is not None,
            "product_count": len((_state["data"] or {}).get("products") or {}),
        }


def reset_for_tests():
    """Reset in-memory cache state (unit tests only)."""
    with _cond:
        _state["data"] = None
        _state["fetched_at"] = None
        _state["error"] = None
        _state["updating"] = False
        _cond.notify_all()
