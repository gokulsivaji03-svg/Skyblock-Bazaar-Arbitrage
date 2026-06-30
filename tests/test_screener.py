import app.arb as arb


def _bazaar(products):
    return {"products": products}


def _product(buy_order, sell_offer, insta_buy, insta_sell, buy_week, sell_week):
    return {
        "quick_status": {
            "buyPrice": insta_buy,
            "sellPrice": insta_sell,
            "buyMovingWeek": buy_week,
            "sellMovingWeek": sell_week,
        },
        "sell_summary": [{"pricePerUnit": buy_order}],
        "buy_summary": [{"pricePerUnit": sell_offer}],
    }


def test_screener_includes_finviz_fields(monkeypatch):
    monkeypatch.setattr(arb, "getData", lambda *a, **k: _bazaar({
        "ENCHANTED_COBBLESTONE": _product(100, 120, 110, 115, 5000, 4000),
    }))
    monkeypatch.setattr(arb.history, "get_bulk_changes", lambda **k: {"ENCHANTED_COBBLESTONE": 2.5})
    row = arb.analyze_screener()["enchanted cobblestone"]
    assert row["instaBuy"] == 110
    assert row["instaSell"] == 115
    assert row["buyOrderPrice"] == 100
    assert row["sellOfferPrice"] == 120
    assert row["marketCap"] > 0
    assert row["change"] == 2.5
    assert row["pe"] is not None
    assert "ticker" not in row
    assert "sector" not in row
