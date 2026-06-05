from .api import getData

TAX_RATE = 0.0125

def analyze():
    data = getData()
    products = data.get("products", {})

    items = {}

    for product_id, product_data in products.items():
        status = product_data.get("quick_status", {})

        sellPrice = status.get("sellPrice", 0)
        buyPrice = status.get("buyPrice", 0)
        buyVolume = status.get("buyMovingWeek", 0)
        sellVolume = status.get("sellMovingWeek", 0)

        profit = (1 - TAX_RATE) * sellPrice - buyPrice

        if buyVolume + sellVolume == 0:
            popularityScore = 0
        else:
            popularityScore = (2 * buyVolume * sellVolume) / (buyVolume + sellVolume)

        if profit > 1000 and popularityScore > 1000:
            name = " ".join(product_id.lower().split("_"))

            items[name] = {
                "profit": int(round(profit, 0)),
                "buyPrice": buyPrice,
                "sellPrice": sellPrice,
                "popularityScore": int(popularityScore),
            }

    return items