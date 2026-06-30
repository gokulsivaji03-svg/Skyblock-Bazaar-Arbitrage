"""
Live integration tests — require running server + network.
Run: uvicorn main:app --port 8765 && pytest tests/test_integration_live.py -v
"""
import os
import re

import httpx
import pytest

BASE = os.environ.get("TEST_API_BASE", "http://127.0.0.1:8765")
TIMEOUT = 30.0


def _server_up():
    try:
        with httpx.Client(base_url=BASE, timeout=2.0) as c:
            return c.get("/api/status").status_code == 200
    except (httpx.HTTPError, OSError):
        return False


pytestmark = pytest.mark.skipif(not _server_up(), reason=f"API not reachable at {BASE}")


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, timeout=TIMEOUT) as c:
        yield c


def test_api_root(client):
    r = client.get("/api")
    assert r.status_code == 200
    body = r.json()
    assert "Forge & Flip" in body["message"]
    assert body["status"] == "/api/status"


def test_api_status(client):
    r = client.get("/api/status")
    assert r.status_code == 200
    body = r.json()
    cache = body["cache"]
    assert cache["has_data"] is True
    assert cache["product_count"] > 0
    assert "age_seconds" in cache
    assert "fetched_at" in cache
    hist = body["history"]
    assert "rows" in hist
    assert hist["rows"] >= 0
    assert "distinct_products" in hist
    assert body["auction"]["wip"] is True


def test_bazaar_screener(client):
    r = client.get("/api/bazaar", params={"min_volume": 1000, "tax_rate": 0.0125})
    assert r.status_code == 200
    data = r.json()
    assert len(data) > 0
    name, row = next(iter(data.items()))
    required = {
        "id", "instaBuy", "instaSell", "buyOrderPrice", "sellOfferPrice",
        "price", "volume", "marketCap", "profit", "profit_margin",
        "spread", "tax", "liquidity rating", "buyVolume", "sellVolume",
    }
    missing = required - set(row.keys())
    assert not missing, f"{name} missing {missing}"
    assert "ticker" not in row
    assert "sector" not in row


def test_flip_endpoints(client):
    for path in ("/api/flip", "/flip"):
        r = client.get(path, params={"min_volume": 1000, "min_profit": 0})
        assert r.status_code == 200
        data = r.json()
        if data:
            _, row = next(iter(data.items()))
            assert "profit" in row
            assert "buyOrderPrice" in row
            assert "sellOfferPrice" in row
            assert "weeklyVolume" in row


def test_forge_endpoints(client):
    for use_orders in (False, True):
        for path in ("/api/forge", "/forge"):
            r = client.get(path, params={"use_orders": use_orders, "min_profit": -1e12})
            assert r.status_code == 200
            data = r.json()
            assert len(data) > 0
            _, row = next(iter(data.items()))
            forge_fields = {
                "id", "profit", "profit_per_hour", "buy_cost", "sell_revenue",
                "hotm_required", "forge_time", "ingredients",
            }
            assert forge_fields <= set(row.keys())
            assert isinstance(row["ingredients"], list)


def test_history_endpoint(client):
    # Pick a common product from bazaar first
    bz = client.get("/api/bazaar", params={"min_volume": 100000}).json()
    assert bz
    product_id = next(iter(bz.values()))["id"]
    r = client.get(f"/api/history/{product_id}", params={"hours": 24})
    assert r.status_code == 200
    body = r.json()
    assert body["product_id"] == product_id
    assert body["hours"] == 24
    assert "points" in body
    if body["points"]:
        pt = body["points"][0]
        assert {"ts", "buy_price", "sell_price", "buy_volume", "sell_volume"} <= set(pt.keys())


def test_player_lookup_valid(client):
    r = client.get("/api/player/Technoblade")
    assert r.status_code == 200
    body = r.json()
    for key in ("username", "uuid", "profile", "skyblock_level", "purse", "bank", "hotm_tier"):
        assert key in body


def test_player_lookup_invalid(client):
    r = client.get("/api/player/thisusernamedoesnotexist12345xyz")
    assert r.status_code == 404


def test_spa_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    html = r.text
    assert 'id="app"' in html
    assert "Forge" in html or "forge" in html.lower()


def test_auction_not_wired(client):
    r = client.get("/api/auction")
    assert r.status_code == 404


def test_bazaar_tax_rate_affects_profit(client):
    r_low = client.get("/api/bazaar", params={"tax_rate": 0.01, "min_volume": 0})
    r_high = client.get("/api/bazaar", params={"tax_rate": 0.02, "min_volume": 0})
    assert r_low.status_code == 200 and r_high.status_code == 200
    low = r_low.json()
    high = r_high.json()
    # Find an item with positive profit in both
    for name in low:
        if name in high and low[name].get("profit", 0) > 0:
            assert low[name]["profit"] >= high[name]["profit"]
            break
    else:
        pytest.skip("No positive-profit item to compare tax rates")


def test_bazaar_min_volume_filter(client):
    r0 = client.get("/api/bazaar", params={"min_volume": 0})
    r1m = client.get("/api/bazaar", params={"min_volume": 1_000_000})
    assert len(r0.json()) >= len(r1m.json())


def test_flip_profit_formula(client):
    """Profit = sell_offer * (1 - tax_rate) - buy_order; tax field is coins not rate."""
    data = client.get("/api/flip", params={"min_volume": 0, "min_price": 0}).json()
    if not data:
        pytest.skip("No flip opportunities")
    row = next(iter(data.values()))
    tax_rate = row["tax"] / row["sellOfferPrice"] if row["sellOfferPrice"] else 0.0125
    expected = int(round(row["sellOfferPrice"] * (1 - tax_rate) - row["buyOrderPrice"]))
    assert row["profit"] == expected


def test_forge_ingredient_structure(client):
    data = client.get("/api/forge", params={"min_profit": -1e12}).json()
    plate = data.get("golden plate") or next(iter(data.values()))
    for ing in plate["ingredients"]:
        assert ing["method"] in ("buy", "forge")
        assert ing["quantity"] > 0
        assert abs(ing["line_cost"] - ing["unit_cost"] * ing["quantity"]) < 0.02


def test_history_case_insensitive(client):
    r = client.get("/api/history/enchanted_diamond", params={"hours": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["product_id"] == "ENCHANTED_DIAMOND"
    assert isinstance(body["points"], list)
