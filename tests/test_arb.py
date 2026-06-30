import app.arb as arb


def _bazaar(products):
    return {"products": products}


def _product(buy_order, sell_offer, buy_week, sell_week):
    # sell_summary[0] = highest buy order (acquire price)
    # buy_summary[0]  = lowest sell offer (exit price)
    return {
        "quick_status": {"buyMovingWeek": buy_week, "sellMovingWeek": sell_week},
        "sell_summary": [{"pricePerUnit": buy_order}],
        "buy_summary": [{"pricePerUnit": sell_offer}],
    }


def test_profit_is_after_tax(monkeypatch):
    monkeypatch.setattr(arb, "getData", lambda *a, **k: _bazaar({
        "WIDGET": _product(100, 200, 5000, 4000),
    }))
    result = arb.analyze()
    assert "widget" in result
    item = result["widget"]
    expected = int(round(200 * (1 - arb.TAX_RATE) - 100))
    assert item["profit"] == expected
    assert item["id"] == "WIDGET"
    assert item["weeklyVolume"] == 4000  # min(buy, sell)


def test_low_volume_filtered(monkeypatch):
    monkeypatch.setattr(arb, "getData", lambda *a, **k: _bazaar({
        "THIN": _product(100, 9999, 5, 5),  # huge spread but no volume
    }))
    assert arb.analyze() == {}


def test_min_profit_filter(monkeypatch):
    monkeypatch.setattr(arb, "getData", lambda *a, **k: _bazaar({
        "SMALL": _product(100, 101, 5000, 5000),
    }))
    assert arb.analyze(min_profit=1_000_000) == {}


def test_custom_tax_rate(monkeypatch):
    monkeypatch.setattr(arb, "getData", lambda *a, **k: _bazaar({
        "WIDGET": _product(1_000_000, 2_000_000, 5000, 5000),
    }))
    lower = arb.analyze(tax_rate=0.01)["widget"]["profit"]
    higher = arb.analyze(tax_rate=0.0125)["widget"]["profit"]
    assert lower > higher  # less tax => more profit


def test_liquidity_rating_monotonic():
    assert arb.get_liquidity_rating(0) == 0.0
    assert arb.get_liquidity_rating(5_000_000) >= 4.9
    assert arb.get_liquidity_rating(100) < arb.get_liquidity_rating(100_000)
