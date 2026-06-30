"""Forge arbitrage analysis.

Buy raw materials from the Bazaar, forge an item (which costs real time and a
Heart of the Mountain unlock), then sell the forged output back to the Bazaar.

The Hypixel API does not expose Forge recipes, so the recipe data below is a
curated dataset sourced from the Hypixel SkyBlock Wiki. Only prices come from
the live Bazaar API.
"""

from .api import getData

TAX_RATE = 0.0125
# Quick Forge (HOTM perk) reduces forge time by up to 30% at max level.
QUICK_FORGE_MULTIPLIER = 0.70

HOUR = 3600
MINUTE = 60

# Each recipe maps a Bazaar-sellable output to its ingredients, base forge
# duration, the Heart of the Mountain tier required, and any extra unlock
# (e.g. a collection milestone). Ingredients reference live Bazaar product ids.
# Nested intermediates (e.g. a Refined Diamond inside a Golden Plate) are
# themselves recipes, so the analyzer can pick the cheaper of "buy it" vs
# "forge it" for every component.
RECIPES = {
    "REFINED_DIAMOND": {
        "output_qty": 1,
        "hotm": 2,
        "time_seconds": 8 * HOUR,
        "collection": None,
        "ingredients": [("ENCHANTED_DIAMOND_BLOCK", 2)],
    },
    "REFINED_MITHRIL": {
        "output_qty": 1,
        "hotm": 2,
        "time_seconds": 6 * HOUR,
        "collection": None,
        "ingredients": [("ENCHANTED_MITHRIL", 160)],
    },
    "REFINED_TITANIUM": {
        "output_qty": 1,
        "hotm": 2,
        "time_seconds": 12 * HOUR,
        "collection": None,
        "ingredients": [("ENCHANTED_TITANIUM", 16)],
    },
    "REFINED_TUNGSTEN": {
        "output_qty": 1,
        "hotm": 7,
        "time_seconds": 1 * HOUR,
        "collection": "Tungsten Collection III",
        "ingredients": [("ENCHANTED_TUNGSTEN", 160)],
    },
    "REFINED_UMBER": {
        "output_qty": 1,
        "hotm": 7,
        "time_seconds": 1 * HOUR,
        "collection": "Umber Collection III",
        "ingredients": [("ENCHANTED_UMBER", 160)],
    },
    "GOLDEN_PLATE": {
        "output_qty": 1,
        "hotm": 2,
        "time_seconds": 6 * HOUR,
        "collection": None,
        "ingredients": [
            ("REFINED_DIAMOND", 1),
            ("ENCHANTED_GOLD_BLOCK", 2),
        ],
    },
    "MITHRIL_PLATE": {
        "output_qty": 1,
        "hotm": 3,
        "time_seconds": 18 * HOUR,
        "collection": None,
        "ingredients": [
            ("REFINED_TITANIUM", 1),
            ("REFINED_MITHRIL", 5),
            ("GOLDEN_PLATE", 1),
        ],
    },
    "TUNGSTEN_PLATE": {
        "output_qty": 1,
        "hotm": 7,
        "time_seconds": 3 * HOUR,
        "collection": "Tungsten Collection VI",
        "ingredients": [
            ("REFINED_TUNGSTEN", 4),
            ("GLACITE_AMALGAMATION", 1),
        ],
    },
    "UMBER_PLATE": {
        "output_qty": 1,
        "hotm": 7,
        "time_seconds": 3 * HOUR,
        "collection": "Umber Collection VI",
        "ingredients": [
            ("REFINED_UMBER", 4),
            ("GLACITE_AMALGAMATION", 1),
        ],
    },
    "PERFECT_PLATE": {
        "output_qty": 1,
        "hotm": 10,
        "time_seconds": 30 * MINUTE,
        "collection": None,
        "ingredients": [
            ("UMBER_PLATE", 1),
            ("TUNGSTEN_PLATE", 1),
            ("MITHRIL_PLATE", 1),
        ],
    },
    "GEMSTONE_MIXTURE": {
        "output_qty": 1,
        "hotm": 4,
        "time_seconds": 4 * HOUR,
        "collection": None,
        "ingredients": [
            ("FINE_JADE_GEM", 4),
            ("FINE_AMBER_GEM", 4),
            ("FINE_AMETHYST_GEM", 4),
            ("FINE_SAPPHIRE_GEM", 4),
        ],
    },
    "GLACITE_AMALGAMATION": {
        "output_qty": 1,
        "hotm": 7,
        "time_seconds": 4 * HOUR,
        "collection": "Glacite Collection III",
        "ingredients": [
            ("FINE_ONYX_GEM", 4),
            ("FINE_CITRINE_GEM", 4),
            ("FINE_PERIDOT_GEM", 4),
            ("FINE_AQUAMARINE_GEM", 4),
            ("ENCHANTED_GLACITE", 256),
        ],
    },
    "BEJEWELED_HANDLE": {
        "output_qty": 1,
        "hotm": 2,
        "time_seconds": 30,
        "collection": None,
        "ingredients": [("GLACITE_JEWEL", 3)],
    },
}


def _quick_status(prices, item_id):
    product = prices.get(item_id)
    if not product:
        return None
    return product.get("quick_status") or {}


def _unit_buy_cost(prices, item_id, use_orders):
    """Cost to acquire one unit of an ingredient.

    use_orders=False -> instant buy (pay the higher buyPrice).
    use_orders=True  -> place a buy order (pay the lower sellPrice).
    """
    status = _quick_status(prices, item_id)
    if status is None:
        return None
    price = status.get("sellPrice") if use_orders else status.get("buyPrice")
    return price if price and price > 0 else None


def _unit_sell_revenue(prices, item_id, use_orders):
    """Revenue from selling one unit of the forged output (pre-tax).

    use_orders=False -> instant sell (receive the lower sellPrice).
    use_orders=True  -> place a sell order (receive the higher buyPrice).
    """
    status = _quick_status(prices, item_id)
    if status is None:
        return None
    price = status.get("buyPrice") if use_orders else status.get("sellPrice")
    return price if price and price > 0 else None


def _obtain(item_id, prices, use_orders, memo, _stack=None):
    """Cheapest way to obtain one unit of ``item_id``: buy it or forge it.

    Recurses into nested recipes (e.g. a Refined Diamond inside a Golden Plate)
    and picks, per component, the cheaper of "buy from the Bazaar" vs. "forge it
    yourself". Results are memoized; a ``_stack`` guards against recipe cycles.

    Returns ``{"cost", "method", "hotm", "collections"}`` or ``None`` if the
    item can be neither priced nor forged.
      - ``method``  : "buy" or "forge"
      - ``hotm``    : highest HOTM tier needed along the chosen forge chain (0 if bought)
      - ``collections`` : set of collection unlocks needed along the chosen chain
    """
    if item_id in memo:
        return memo[item_id]

    _stack = _stack or set()
    if item_id in _stack:
        return None  # recipe cycle; bail on this branch

    buy_cost = _unit_buy_cost(prices, item_id, use_orders)

    forge_option = None
    recipe = RECIPES.get(item_id)
    if recipe is not None:
        total = 0.0
        hotm = recipe["hotm"]
        collections = set()
        if recipe["collection"]:
            collections.add(recipe["collection"])
        ok = True
        for ingredient_id, quantity in recipe["ingredients"]:
            sub = _obtain(ingredient_id, prices, use_orders, memo, _stack | {item_id})
            if sub is None:
                ok = False
                break
            total += sub["cost"] * quantity
            if sub["method"] == "forge":
                hotm = max(hotm, sub["hotm"])
                collections |= sub["collections"]
        if ok:
            forge_option = {
                "cost": total / recipe["output_qty"],
                "method": "forge",
                "hotm": hotm,
                "collections": collections,
            }

    buy_option = (
        {"cost": buy_cost, "method": "buy", "hotm": 0, "collections": set()}
        if buy_cost is not None
        else None
    )

    options = [o for o in (buy_option, forge_option) if o is not None]
    result = min(options, key=lambda o: o["cost"]) if options else None
    memo[item_id] = result
    return result


def _forge_cost(item_id, prices, use_orders, memo):
    """Cost, HOTM tier, and collections to forge one unit of ``item_id``.

    The output itself is always forged (that's the opportunity we evaluate), but
    each ingredient is obtained the cheapest way via :func:`_obtain`. Returns
    ``{"cost", "hotm", "collections"}`` or ``None`` if any component cannot be
    priced.
    """
    recipe = RECIPES.get(item_id)
    if recipe is None:
        return None

    total = 0.0
    hotm = recipe["hotm"]
    collections = set()
    if recipe["collection"]:
        collections.add(recipe["collection"])
    for ingredient_id, quantity in recipe["ingredients"]:
        sub = _obtain(ingredient_id, prices, use_orders, memo, {item_id})
        if sub is None:
            return None
        total += sub["cost"] * quantity
        if sub["method"] == "forge":
            hotm = max(hotm, sub["hotm"])
            collections |= sub["collections"]

    return {
        "cost": total / recipe["output_qty"],
        "hotm": hotm,
        "collections": collections,
    }


def _ingredient_breakdown(recipe, prices, use_orders, memo):
    """Per-ingredient cost rows so the total is fully auditable.

    Each row shows the quantity, the chosen acquisition method (buy vs. forge),
    the effective per-unit cost, and the line cost (quantity * unit).
    """
    rows = []
    for ingredient_id, quantity in recipe["ingredients"]:
        sub = _obtain(ingredient_id, prices, use_orders, memo)
        unit_cost = sub["cost"] if sub else None
        method = sub["method"] if sub else None
        rows.append(
            {
                "id": ingredient_id,
                "name": " ".join(ingredient_id.lower().split("_")),
                "quantity": quantity,
                "method": method,
                "unit_cost": round(unit_cost, 2) if unit_cost is not None else None,
                "line_cost": round(unit_cost * quantity, 2) if unit_cost is not None else None,
            }
        )
    return rows


def _format_duration(seconds):
    seconds = int(round(seconds))
    parts = []
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds and not days and not hours:
        parts.append(f"{seconds}s")
    return " ".join(parts) or "0m"


def analyze_forge(min_profit=0, use_orders=False, tax_rate=TAX_RATE):
    data = getData()
    prices = data.get("products") or {}

    # Shared memo so nested intermediates are priced once across all recipes.
    memo = {}

    items = {}

    for output_id, recipe in RECIPES.items():
        cost_info = _forge_cost(output_id, prices, use_orders, memo)
        if cost_info is None:
            continue

        revenue_unit = _unit_sell_revenue(prices, output_id, use_orders)
        if revenue_unit is None:
            continue

        buy_cost = cost_info["cost"]
        sell_revenue = revenue_unit * (1 - tax_rate)
        profit = sell_revenue - buy_cost

        if profit < min_profit:
            continue

        hours = recipe["time_seconds"] / HOUR
        profit_per_hour = profit / hours if hours > 0 else profit
        quick_forge_seconds = recipe["time_seconds"] * QUICK_FORGE_MULTIPLIER

        collections = sorted(cost_info["collections"])
        name = " ".join(output_id.lower().split("_"))
        items[name] = {
            "id": output_id,
            "profit": int(round(profit)),
            "profit_per_hour": int(round(profit_per_hour)),
            "buy_cost": round(buy_cost, 2),
            "sell_revenue": round(sell_revenue, 2),
            "hotm_required": cost_info["hotm"],
            "forge_time": _format_duration(recipe["time_seconds"]),
            "forge_time_quick": _format_duration(quick_forge_seconds),
            "forge_time_seconds": recipe["time_seconds"],
            "collection_req": recipe["collection"],
            "collections_required": collections,
            "ingredients": _ingredient_breakdown(recipe, prices, use_orders, memo),
        }

    return items


if __name__ == "__main__":
    for item, stats in analyze_forge().items():
        print(
            f"{item}: profit {stats['profit']:,} "
            f"({stats['profit_per_hour']:,}/hr), "
            f"HOTM {stats['hotm_required']}, {stats['forge_time']}"
        )
