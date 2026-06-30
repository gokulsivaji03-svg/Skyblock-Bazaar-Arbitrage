import app.forge as forge


def _qs(buy_price, sell_price):
    return {"quick_status": {"buyPrice": buy_price, "sellPrice": sell_price}}


def _bazaar(products):
    return {"products": products}


PRICES = {
    # Ingredient: cheaper to forge a Refined Diamond (2 x 100k = 200k) than buy (250k).
    "ENCHANTED_DIAMOND_BLOCK": _qs(100_000, 90_000),
    "REFINED_DIAMOND": _qs(250_000, 240_000),
    "ENCHANTED_GOLD_BLOCK": _qs(50_000, 45_000),
    "GOLDEN_PLATE": _qs(5_000_000, 2_000_000),
}


def test_recursive_costing_prefers_forge(monkeypatch):
    monkeypatch.setattr(forge, "getData", lambda *a, **k: _bazaar(PRICES))
    result = forge.analyze_forge()
    assert "golden plate" in result
    plate = result["golden plate"]

    methods = {row["name"]: row["method"] for row in plate["ingredients"]}
    # Refined Diamond should be forged (200k) rather than bought (250k).
    assert methods["refined diamond"] == "forge"

    # Cost = forge(refined diamond)=200k + 2 x enchanted gold block(50k)=100k => 300k.
    assert plate["buy_cost"] == 300_000


def test_buy_chosen_when_cheaper(monkeypatch):
    cheap_buy = dict(PRICES)
    cheap_buy["REFINED_DIAMOND"] = _qs(150_000, 140_000)  # cheaper to buy than forge (200k)
    monkeypatch.setattr(forge, "getData", lambda *a, **k: _bazaar(cheap_buy))
    plate = forge.analyze_forge()["golden plate"]
    methods = {row["name"]: row["method"] for row in plate["ingredients"]}
    assert methods["refined diamond"] == "buy"
    assert plate["buy_cost"] == 150_000 + 100_000


def test_effective_hotm_aggregates(monkeypatch):
    monkeypatch.setattr(forge, "getData", lambda *a, **k: _bazaar(PRICES))
    plate = forge.analyze_forge()["golden plate"]
    # Golden Plate recipe is HOTM 2; forged Refined Diamond is also HOTM 2.
    assert plate["hotm_required"] == 2


def test_profit_after_tax(monkeypatch):
    monkeypatch.setattr(forge, "getData", lambda *a, **k: _bazaar(PRICES))
    plate = forge.analyze_forge()["golden plate"]
    # Output sells (instant) at sellPrice 2,000,000 after tax, minus 300k cost.
    expected = int(round(2_000_000 * (1 - forge.TAX_RATE) - 300_000))
    assert plate["profit"] == expected
