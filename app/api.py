import requests

def getData():
    data = requests.get("https://api.hypixel.net/v2/skyblock/bazaar")
    stats = data.json()
    return stats
