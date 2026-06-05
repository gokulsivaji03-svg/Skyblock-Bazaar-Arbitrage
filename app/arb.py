from .api import getData
TAX_RATE = 0.0125

#main method, holds the math behind the arb
def analyze():
    data = getData()
    product = data.get("products", {})

    items = {}
    for product in data["products"]:
        sellPrice = data["products"][product]["quick_status"]["sellPrice"]
        buyPrice = data["products"][product]["quick_status"]["buyPrice"]
        buyVolume = data["products"][product]["quick_status"]["buyMovingWeek"]
        sellVolume = data["products"][product]["quick_status"]["sellMovingWeek"]
        profit = (1-TAX_RATE) * sellPrice - buyPrice

        if (buyVolume + sellVolume) == 0:
            popularityScore = 0
        else:
            popularityScore = (2 * buyVolume * sellVolume) / (buyVolume + sellVolume)
        if(profit > 1000 and popularityScore > 1000):
            name = " ".join(product.lower().split("_")) 
            items[name] = int(round(profit, 0))

    return items
