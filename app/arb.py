import math

from .api import getData
from . import history

# Hypixel charges 1.25% tax on every Bazaar sale (collected from the sell side).
# The Bazaar Flipper community perk can reduce this to 1.125% / 1.0%.
TAX_RATE = 0.0125
# Weekly traded volume (per side) that earns a full 5.0 liquidity rating.
LIQUIDITY_BENCHMARK = 5_000_000


def get_price_per_unit(summary):
    first_order = summary[0] if summary else {}
    return first_order.get("pricePerUnit", 0)


def get_weekly_volume(buy_volume, sell_volume):
    # A round-trip flip can only complete as fast as the *slower* side trades,
    # so the binding liquidity constraint is the smaller weekly volume.
    return min(buy_volume, sell_volume)


def get_liquidity_rating(weekly_volume):
    # Clean, interpretable 0-5 scale: ~5.0 once an item moves the benchmark
    # number of units per week, log-scaled so small items still differentiate.
    if weekly_volume <= 0:
        return 0.0

    rating = 5 * math.log10(weekly_volume + 1) / math.log10(LIQUIDITY_BENCHMARK)
    return round(min(5.0, max(0.0, rating)), 1)


def analyze(min_profit=0, min_liquidity_rating=0, min_price=1, min_volume=1000, tax_rate=TAX_RATE):
    """Rank "buy order -> sell offer" Bazaar flips.

    The profitable Bazaar method is to provide liquidity, not cross the spread.
    We price off the *top of the order book* (what the in-game menu shows), not
    the ``quick_status`` weighted averages, which smear across many orders and
    invent fake spreads on thin/expensive items:
      1. Acquire by placing a BUY ORDER at the current highest buy order
         (``sell_summary[0]`` = the instant-sell price).
      2. Exit by placing a SELL OFFER at the current lowest sell offer
         (``buy_summary[0]`` = the instant-buy price).
      3. Hypixel taxes the sale by ``tax_rate``.

    Net profit per unit = sell_offer_price * (1 - tax_rate) - buy_order_price.

    ``min_volume`` enforces that *both* sides actually trade each week. Without
    it the rankings are dominated by manipulation traps: lone 1-unit orders on
    items that never trade, which show enormous fake spreads but cannot be
    flipped.
    """
    data = getData()
    products = data.get("products") or {}

    items = {}

    for product_id, product_data in products.items():
        status = product_data.get("quick_status") or {}
        sell_summary = product_data.get("sell_summary") or []
        buy_summary = product_data.get("buy_summary") or []

        # Top-of-book order prices (match what the player sees in-game):
        #   highest buy order  = sell_summary[0]  (where you place a buy order)
        #   lowest sell offer  = buy_summary[0]   (where you place a sell offer)
        buy_order_price = get_price_per_unit(sell_summary)
        sell_offer_price = get_price_per_unit(buy_summary)
        buy_volume = status.get("buyMovingWeek", 0)
        sell_volume = status.get("sellMovingWeek", 0)

        if buy_order_price < min_price or sell_offer_price <= 0:
            continue

        weekly_volume = get_weekly_volume(buy_volume, sell_volume)
        if weekly_volume < min_volume:
            continue

        tax = sell_offer_price * tax_rate
        profit = (sell_offer_price - tax) - buy_order_price
        spread = sell_offer_price - buy_order_price
        margin = (profit / buy_order_price * 100) if buy_order_price else 0

        name = " ".join(product_id.lower().split("_"))
        liquidity_rating = get_liquidity_rating(weekly_volume)

        if liquidity_rating >= min_liquidity_rating and profit >= min_profit:
            items[name] = {
                "id": product_id,
                "profit": int(round(profit)),
                "profit_margin": round(margin, 2),
                "buyOrderPrice": round(buy_order_price, 1),
                "sellOfferPrice": round(sell_offer_price, 1),
                "spread": round(spread, 1),
                "tax": int(round(tax)),
                "weeklyVolume": int(weekly_volume),
                "buyVolume": int(buy_volume),
                "sellVolume": int(sell_volume),
                "liquidity rating": liquidity_rating,
            }
    return items


def analyze_screener(min_volume=0, tax_rate=TAX_RATE):
    """Finviz-style Bazaar screener: all products with market metrics."""
    data = getData()
    products = data.get("products") or {}
    changes = {}
    try:
        changes = history.get_bulk_changes(hours=24)
    except Exception:  # noqa: BLE001 - history is optional until first snapshots exist
        changes = {}

    items = {}
    for product_id, product_data in products.items():
        status = product_data.get("quick_status") or {}
        sell_summary = product_data.get("sell_summary") or []
        buy_summary = product_data.get("buy_summary") or []

        insta_buy = status.get("buyPrice") or 0
        insta_sell = status.get("sellPrice") or 0
        buy_order = get_price_per_unit(sell_summary)
        sell_offer = get_price_per_unit(buy_summary)
        buy_volume = status.get("buyMovingWeek", 0)
        sell_volume = status.get("sellMovingWeek", 0)
        weekly_volume = get_weekly_volume(buy_volume, sell_volume)

        if weekly_volume < min_volume:
            continue

        mid = (insta_buy + insta_sell) / 2 if insta_buy and insta_sell else insta_buy or insta_sell or 0
        if mid <= 0 and buy_order <= 0:
            continue

        tax = sell_offer * tax_rate if sell_offer else 0
        profit = (sell_offer - tax - buy_order) if sell_offer and buy_order else 0
        margin = (profit / buy_order * 100) if buy_order else 0
        # P/E analog: mid price divided by per-unit flip profit (lower = better value).
        pe = round(mid / profit, 2) if profit > 0 else None
        market_cap = int(round(weekly_volume * mid)) if mid else 0
        change_pct = changes.get(product_id)

        name = " ".join(product_id.lower().split("_"))
        liquidity_rating = get_liquidity_rating(weekly_volume)

        items[name] = {
            "id": product_id,
            "instaBuy": round(insta_buy, 1),
            "instaSell": round(insta_sell, 1),
            "buyOrderPrice": round(buy_order, 1),
            "sellOfferPrice": round(sell_offer, 1),
            "price": round(mid, 1),
            "change": change_pct,
            "volume": int(weekly_volume),
            "buyVolume": int(buy_volume),
            "sellVolume": int(sell_volume),
            "marketCap": market_cap,
            "pe": pe,
            "profit": int(round(profit)),
            "profit_margin": round(margin, 2),
            "spread": round(sell_offer - buy_order, 1) if sell_offer and buy_order else 0,
            "tax": int(round(tax)) if tax else 0,
            "liquidity rating": liquidity_rating,
        }
    return items


if __name__ == "__main__":
    print(analyze())
