import math

from .api import getData

TAX_RATE = 0.0125
LIQUIDITY_BENCHMARK = 250000


def get_price_per_unit(summary):
    first_order = summary[0] if summary else {}
    return first_order.get("pricePerUnit", 0)


def get_liquidity_score(buy_volume, sell_volume):
    if buy_volume + sell_volume == 0:
        return 0

    return (2 * buy_volume * sell_volume) / (buy_volume + sell_volume)


def get_liquidity_rating(liquidity_score):
    if liquidity_score <= 0:
        return 0.0

    scaled_score = math.log1p(liquidity_score) / math.log1p(LIQUIDITY_BENCHMARK)
    return round(min(5.0, 5 * scaled_score), 1)


def analyze(min_profit=0, min_liquidity_rating=0, min_buy_price=1):
    data = getData()
    products = data.get("products") or {}

    items = {}

    for product_id, product_data in products.items():
        status = product_data.get("quick_status") or {}
        sell_summary = product_data.get("sell_summary") or []
        buy_summary = product_data.get("buy_summary") or []

        sellPrice = status.get("sellPrice", 0)
        buyPrice = status.get("buyPrice", 0)
        buyVolume = status.get("buyMovingWeek", 0)
        sellVolume = status.get("sellMovingWeek", 0)
        topSellPrice = get_price_per_unit(sell_summary)
        topBuyPrice = get_price_per_unit(buy_summary)

        profit = (1 - TAX_RATE) * buyPrice - sellPrice
        name = " ".join(product_id.lower().split("_"))
        liquidity_score = get_liquidity_score(buyVolume, sellVolume)
        liquidity_rating = get_liquidity_rating(liquidity_score)

        if (
            liquidity_rating >= min_liquidity_rating
            and profit >= min_profit
            and buyPrice >= min_buy_price
        ):
            items[name] = {
                "profit": int(round(profit, 0)),
                "liquidity score": int(liquidity_score),
                "liquidity rating": liquidity_rating,
                "buyPrice": round(buyPrice, 2),
                "sellPrice": round(sellPrice, 2),
                "topBuyPrice": round(topBuyPrice, 2),
                "topSellPrice": round(topSellPrice, 2),
                "spread": round(topBuyPrice - topSellPrice, 2),
            }
    return items


if __name__ == "__main__":
    print(analyze())
