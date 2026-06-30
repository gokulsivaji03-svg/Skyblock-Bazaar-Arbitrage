"""Bazaar data access.

``getData`` is the single entry point used by the analyzers. It now reads from a
shared, thread-safe cache (see ``app.cache``) instead of hitting Hypixel on every
call, with a timeout and graceful handling of fetch failures.
"""

from .cache import get_data


def getData(force=False):
    return get_data(force=force)
