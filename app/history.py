"""Persistent Bazaar price history (SQLite).

Every refresh cycle we append a compact snapshot of each product's instant
buy/sell price and weekly volume. This unlocks sparklines, trend filters, and
"was this profitable earlier?" features without any external service.

SQLite is used because it is zero-config and ships with Python. Old rows are
pruned on a retention window so the file stays bounded.
"""

import os
import sqlite3
import threading
import time

# Default to a repo-local data directory; override with HISTORY_DB_PATH.
_DEFAULT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_PATH = os.environ.get("HISTORY_DB_PATH", os.path.join(_DEFAULT_DIR, "bazaar_history.db"))
RETENTION_DAYS = int(os.environ.get("HISTORY_RETENTION_DAYS", "7"))

_lock = threading.Lock()


def _connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with _lock, _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS price_history (
                ts          INTEGER NOT NULL,
                product_id  TEXT    NOT NULL,
                buy_price   REAL,
                sell_price  REAL,
                buy_volume  INTEGER,
                sell_volume INTEGER
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_history_product_ts "
            "ON price_history (product_id, ts)"
        )


def record_snapshot(payload, ts=None):
    """Append one row per product from a Bazaar payload. Returns rows written."""
    products = (payload or {}).get("products") or {}
    if not products:
        return 0

    ts = int(ts if ts is not None else time.time())
    rows = []
    for product_id, product in products.items():
        status = product.get("quick_status") or {}
        rows.append(
            (
                ts,
                product_id,
                status.get("buyPrice"),
                status.get("sellPrice"),
                status.get("buyMovingWeek"),
                status.get("sellMovingWeek"),
            )
        )

    with _lock, _connect() as conn:
        conn.executemany(
            "INSERT INTO price_history "
            "(ts, product_id, buy_price, sell_price, buy_volume, sell_volume) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
    return len(rows)


def prune(retention_days=RETENTION_DAYS):
    """Delete rows older than the retention window. Returns rows removed."""
    cutoff = int(time.time() - retention_days * 86400)
    with _lock, _connect() as conn:
        cur = conn.execute("DELETE FROM price_history WHERE ts < ?", (cutoff,))
        return cur.rowcount


def get_history(product_id, hours=24):
    """Return time-ordered price points for a product over the last ``hours``."""
    since = int(time.time() - hours * 3600)
    with _lock, _connect() as conn:
        cur = conn.execute(
            "SELECT ts, buy_price, sell_price, buy_volume, sell_volume "
            "FROM price_history WHERE product_id = ? AND ts >= ? ORDER BY ts ASC",
            (product_id, since),
        )
        return [
            {
                "ts": ts,
                "buy_price": buy_price,
                "sell_price": sell_price,
                "buy_volume": buy_volume,
                "sell_volume": sell_volume,
            }
            for ts, buy_price, sell_price, buy_volume, sell_volume in cur.fetchall()
        ]


def _mid(buy, sell):
    if buy and sell:
        return (buy + sell) / 2
    return buy or sell or 0


def get_bulk_changes(hours=24):
    """Return {product_id: change_pct} for mid-price vs oldest snapshot in window."""
    since = int(time.time() - hours * 3600)
    changes = {}
    with _lock, _connect() as conn:
        cur = conn.execute(
            """
            SELECT product_id, buy_price, sell_price, ts
            FROM price_history
            WHERE ts >= ?
            ORDER BY product_id ASC, ts ASC
            """,
            (since,),
        )
        rows = cur.fetchall()

    by_product = {}
    for product_id, buy, sell, ts in rows:
        by_product.setdefault(product_id, []).append((ts, _mid(buy, sell)))

    for product_id, points in by_product.items():
        if len(points) < 2:
            continue
        old_mid = points[0][1]
        new_mid = points[-1][1]
        if old_mid and new_mid:
            changes[product_id] = round((new_mid - old_mid) / old_mid * 100, 2)
    return changes


def stats():
    """Summary for health endpoints: row count and time span."""
    with _lock, _connect() as conn:
        cur = conn.execute(
            "SELECT COUNT(*), MIN(ts), MAX(ts), COUNT(DISTINCT product_id) "
            "FROM price_history"
        )
        total, min_ts, max_ts, products = cur.fetchone()
    return {
        "rows": total or 0,
        "oldest_ts": min_ts,
        "newest_ts": max_ts,
        "distinct_products": products or 0,
        "db_path": DB_PATH,
        "retention_days": RETENTION_DAYS,
    }
