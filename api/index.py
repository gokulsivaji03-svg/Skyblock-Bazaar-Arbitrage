import base64
from io import BytesIO
import json
from pathlib import Path
import re
from time import time
from urllib.parse import quote

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, Response
from PIL import Image, ImageDraw

TAX_RATE = 0.0125
MIN_COIN_BALANCE_SCORE = 0.90
MIN_MATCHED_COIN_VOLUME = 100000000
ITEMS_URL = "https://api.hypixel.net/v2/resources/skyblock/items"
BAZAAR_URL = "https://api.hypixel.net/v2/skyblock/bazaar"
NEU_ITEM_URL = (
    "https://raw.githubusercontent.com/NotEnoughUpdates/NotEnoughUpdates-REPO/"
    "master/items/{item_id}.json"
)
TEXTURE_BASE_URL = (
    "https://raw.githubusercontent.com/InventivetalentDev/minecraft-assets/1.8.9/"
    "assets/minecraft/textures"
)
WIKI_API_URL = "https://hypixelskyblock.minecraft.wiki/api.php"
WIKI_FILEPATH_URL = "https://hypixelskyblock.minecraft.wiki/w/Special:FilePath/"
WIKI_USER_AGENT = "bazaar-lens/2.0 (Hypixel SkyBlock market scanner)"
METADATA_TTL_SECONDS = 60 * 60
MARKET_TTL_SECONDS = 30
SKIN_VALUE_PATTERN = re.compile(r'Value:"([^"]+)"')
ENCHANTMENT_ID_PATTERN = re.compile(r"^ENCHANTMENT_(.+)_(\d+)$")
ENCHANTED_BOOK_FILENAME = "Enchanted Book.png"

app = FastAPI(
    title="Bazaar Lens API",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    swagger_ui_oauth2_redirect_url="/api/docs/oauth2-redirect",
)

_item_metadata_cache = {}
_item_metadata_cache_expires_at = 0.0
_icon_cache = {}
_neu_item_cache = {}
_wiki_url_cache = {}
_market_cache = {}
_market_cache_expires_at = 0.0
_bazaar_products_cache = {}
_bazaar_products_cache_expires_at = 0.0
_forge_market_cache = []
_forge_market_cache_expires_at = 0.0

with Path(__file__).with_name("forge_recipes.json").open(encoding="utf-8") as recipe_file:
    _forge_recipe_snapshot = json.load(recipe_file)

FORGE_RECIPES = {
    recipe["item"]: recipe for recipe in _forge_recipe_snapshot["recipes"]
}

ITEM_TEXTURE_OVERRIDES = {
    "CACTUS": ("blocks", "cactus_side"),
    "CLAY_BALL": ("items", "clay_ball"),
    "COAL": ("items", "coal"),
    "COBBLESTONE": ("blocks", "cobblestone"),
    "COOKIE": ("items", "cookie"),
    "DIAMOND": ("items", "diamond"),
    "DIAMOND_BLOCK": ("blocks", "diamond_block"),
    "EMERALD": ("items", "emerald"),
    "EMERALD_BLOCK": ("blocks", "emerald_block"),
    "ENDER_PEARL": ("items", "ender_pearl"),
    "EYE_OF_ENDER": ("items", "ender_eye"),
    "BAKED_POTATO": ("items", "potato_baked"),
    "BOOK": ("items", "book_normal"),
    "DIAMOND_BARDING": ("items", "diamond_horse_armor"),
    "DOUBLE_PLANT": ("blocks", "double_plant_sunflower_front"),
    "FERMENTED_SPIDER_EYE": ("items", "spider_eye_fermented"),
    "GLOWSTONE_DUST": ("items", "glowstone_dust"),
    "GOLD_BLOCK": ("blocks", "gold_block"),
    "GOLD_INGOT": ("items", "gold_ingot"),
    "GOLDEN_CARROT": ("items", "carrot_golden"),
    "IRON_BLOCK": ("blocks", "iron_block"),
    "IRON_INGOT": ("items", "iron_ingot"),
    "INK_SACK": ("items", "dye_powder_white"),
    "LAPIS_BLOCK": ("blocks", "lapis_block"),
    "LEASH": ("items", "lead"),
    "LOG": ("blocks", "log_oak"),
    "LOG_2": ("blocks", "log_acacia"),
    "MELON": ("items", "melon"),
    "MELON_BLOCK": ("blocks", "melon_side"),
    "HUGE_MUSHROOM_1": ("blocks", "mushroom_block_skin_brown"),
    "HUGE_MUSHROOM_2": ("blocks", "mushroom_block_skin_red"),
    "MYCEL": ("blocks", "mycelium_side"),
    "NETHER_BRICK_ITEM": ("items", "netherbrick"),
    "NETHER_STALK": ("items", "nether_wart"),
    "PACKED_ICE": ("blocks", "ice_packed"),
    "PORK": ("items", "porkchop_raw"),
    "POTATO_ITEM": ("items", "potato"),
    "PRISMARINE_CRYSTALS": ("items", "prismarine_crystals"),
    "PRISMARINE_SHARD": ("items", "prismarine_shard"),
    "QUARTZ": ("items", "quartz"),
    "QUARTZ_BLOCK": ("blocks", "quartz_block_side"),
    "REDSTONE": ("items", "redstone_dust"),
    "REDSTONE_BLOCK": ("blocks", "redstone_block"),
    "RED_MUSHROOM": ("blocks", "mushroom_red"),
    "ROTTEN_FLESH": ("items", "rotten_flesh"),
    "RAW_FISH": ("items", "fish_cod_raw"),
    "SLIME_BALL": ("items", "slimeball"),
    "SPECKLED_MELON": ("items", "melon_speckled"),
    "SULPHUR": ("items", "gunpowder"),
    "SUGAR_CANE": ("items", "reeds"),
    "TNT": ("blocks", "tnt_side"),
    "TRIPWIRE_HOOK": ("items", "trip_wire_source"),
    "WATER_LILY": ("blocks", "waterlily"),
    "WHEAT": ("items", "wheat"),
    "WOOL": ("blocks", "wool_colored_brown"),
}

NEU_TEXTURE_OVERRIDES = {
    "baked_potato": ("items", "potato_baked"),
    "dye": ("items", "dye_powder_white"),
    "fermented_spider_eye": ("items", "spider_eye_fermented"),
    "fish": ("items", "fish_cod_raw"),
    "golden_carrot": ("items", "carrot_golden"),
    "nether_wart": ("items", "nether_wart"),
    "skull": None,
    "tripwire_hook": ("items", "trip_wire_source"),
    "waterlily": ("blocks", "waterlily"),
}


@app.get("/api")
async def root():
    return {
        "name": "Bazaar Lens API",
        "status": "ok",
        "endpoints": [
            "/api/items",
            "/api/forge",
            "/api/size",
            "/api/icons/{item_id}",
            "/api/health",
        ],
    }


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "cached_markets": len(_market_cache),
        "forge_recipes": len(FORGE_RECIPES),
    }


@app.get("/api/items")
def items():
    return JSONResponse(
        content=build_good_items(),
        headers={
            "Cache-Control": "public, max-age=0, must-revalidate",
            "Vercel-CDN-Cache-Control": (
                "public, s-maxage=30, stale-while-revalidate=30, stale-if-error=300"
            ),
        },
    )


@app.get("/api/size")
def size():
    good_items = build_good_items()
    return f"{len(good_items)}: items"


@app.get("/api/forge")
def forge_items():
    return JSONResponse(
        content=build_forge_items(),
        headers={
            "Cache-Control": "public, max-age=0, must-revalidate",
            "Vercel-CDN-Cache-Control": (
                "public, s-maxage=30, stale-while-revalidate=30, stale-if-error=300"
            ),
        },
    )


@app.get("/api/icons/{item_id}")
def icon(item_id: str):
    metadata = get_item_metadata()
    item = metadata.get(item_id) or {
        "display_name": item_id_to_display_name(item_id),
        "material": None,
    }

    icon_bytes = get_icon_bytes(item_id, item)
    if icon_bytes is None:
        raise HTTPException(status_code=404, detail="Icon not found")

    return Response(
        content=icon_bytes,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=86400",
            "Vercel-CDN-Cache-Control": (
                "public, s-maxage=2592000, stale-while-revalidate=86400"
            ),
        },
    )


def calculate_volume_balance_score(buy_volume, sell_volume):
    total_volume = buy_volume + sell_volume
    if total_volume == 0:
        return 0
    return 1 - abs(buy_volume - sell_volume) / total_volume


def calculate_good_volume_score(buy_volume, sell_volume):
    return 2 * min(buy_volume, sell_volume)


def calculate_coin_volume(unit_volume, unit_price):
    if unit_price is None:
        return 0
    return unit_volume * unit_price


def decode_skin_url(skin_value):
    if not skin_value:
        return None
    try:
        decoded = base64.b64decode(skin_value).decode("utf-8")
        payload = json.loads(decoded)
        texture_url = payload["textures"]["SKIN"]["url"]
        return texture_url.replace("http://", "https://", 1)
    except (ValueError, KeyError, TypeError):
        return None


def decode_skin_url_from_nbt(nbt_tag):
    if not nbt_tag:
        return None

    match = SKIN_VALUE_PATTERN.search(nbt_tag)
    if match is None:
        return None

    return decode_skin_url(match.group(1))


def get_texture_key(material):
    return ITEM_TEXTURE_OVERRIDES.get(material, ("items", material.lower()))


def get_neu_texture_key(neu_item):
    item_id = neu_item.get("itemid", "")
    if not item_id.startswith("minecraft:"):
        return None

    texture_name = item_id.split(":", 1)[1]
    override = NEU_TEXTURE_OVERRIDES.get(texture_name)
    if texture_name in NEU_TEXTURE_OVERRIDES:
        return override

    return ("items", texture_name)


def wiki_request_headers():
    return {"User-Agent": WIKI_USER_AGENT}


def fetch_png(url, headers=None):
    response = requests.get(
        url,
        timeout=15,
        headers=headers,
        allow_redirects=True,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return Image.open(BytesIO(response.content)).convert("RGBA")


def item_id_to_display_name(item_id):
    return " ".join(part.capitalize() for part in item_id.split("_"))


def format_display_name(name, item_id=None):
    if not name:
        return item_id_to_display_name(item_id) if item_id else "Unknown"
    if name == item_id or ("_" in name and name == name.upper()):
        return item_id_to_display_name(name if "_" in name else item_id or name)
    return name


def wiki_page_thumbnail_url(page_title):
    try:
        response = requests.get(
            WIKI_API_URL,
            params={
                "action": "query",
                "titles": page_title,
                "prop": "pageimages",
                "piprop": "thumbnail",
                "pithumbsize": 32,
                "format": "json",
            },
            headers=wiki_request_headers(),
            timeout=15,
        )
        response.raise_for_status()
        pages = response.json().get("query", {}).get("pages", {})
    except (requests.RequestException, ValueError, KeyError):
        return None

    for page in pages.values():
        if page.get("missing") is not None:
            continue
        thumbnail = page.get("thumbnail", {})
        if thumbnail.get("source"):
            return thumbnail["source"]
    return None


def wiki_filepath_url(filename):
    return f"{WIKI_FILEPATH_URL}{quote(filename)}?width=32"


def wiki_filepath_exists(filename):
    try:
        response = requests.head(
            wiki_filepath_url(filename),
            headers=wiki_request_headers(),
            timeout=15,
            allow_redirects=True,
        )
        return response.status_code == 200
    except requests.RequestException:
        return False


def parse_enchantment_name(item_id):
    match = ENCHANTMENT_ID_PATTERN.match(item_id)
    if match is None:
        return None
    return item_id_to_display_name(match.group(1))


def wiki_title_candidates(display_name, item_id):
    candidates = []

    def add(value):
        if value and value not in candidates:
            candidates.append(value)

    add(format_display_name(display_name, item_id))
    add(item_id_to_display_name(item_id))

    if item_id.startswith("ENCHANTMENT_"):
        enchantment_name = parse_enchantment_name(item_id)
        if enchantment_name:
            add(enchantment_name)
            add(f"{enchantment_name} Enchantment")
            if enchantment_name.startswith("Ultimate "):
                short_name = enchantment_name[len("Ultimate ") :]
                add(short_name)
                add(f"{short_name} Enchantment")

    if item_id.startswith("SHARD_"):
        shard_name = item_id_to_display_name(item_id[len("SHARD_") :])
        add(f"{shard_name} Shard")

    id_parts = item_id.split("_")
    if len(id_parts) == 2:
        add(item_id_to_display_name(f"{id_parts[1]}_{id_parts[0]}"))

    return candidates


def wiki_filename_candidates(display_name, item_id):
    filenames = []
    for title in wiki_title_candidates(display_name, item_id):
        for filename in (f"{title}.png", f"Invicon {title}.png"):
            if filename not in filenames:
                filenames.append(filename)

    if item_id.startswith("ENCHANTMENT_") and ENCHANTED_BOOK_FILENAME not in filenames:
        filenames.append(ENCHANTED_BOOK_FILENAME)

    return filenames


def resolve_wiki_image_url(display_name, item_id):
    cache_key = f"{display_name}|{item_id}"
    if cache_key in _wiki_url_cache:
        return _wiki_url_cache[cache_key]

    image_url = None
    for title in wiki_title_candidates(display_name, item_id):
        image_url = wiki_page_thumbnail_url(title)
        if image_url:
            break

    if image_url is None:
        for filename in wiki_filename_candidates(display_name, item_id):
            if wiki_filepath_exists(filename):
                image_url = wiki_filepath_url(filename)
                break

    _wiki_url_cache[cache_key] = image_url
    return image_url


def build_wiki_icon(display_name, item_id):
    image_url = resolve_wiki_image_url(display_name, item_id)
    if image_url is None:
        return None

    image = fetch_png(image_url, headers=wiki_request_headers())
    if image is None:
        return None

    return resize_icon(image)


def resize_icon(image):
    resized = image.resize((32, 32), Image.Resampling.NEAREST)
    output = BytesIO()
    resized.save(output, format="PNG")
    return output.getvalue()


def build_fallback_icon(label):
    initials = "".join(part[0] for part in label.split()[:2] if part).upper() or "?"
    colors = [
        ((51, 65, 85), (15, 23, 42)),
        ((22, 101, 52), (20, 83, 45)),
        ((30, 64, 175), (30, 58, 138)),
        ((146, 64, 14), (124, 45, 18)),
        ((88, 28, 135), (76, 29, 149)),
    ]
    color_pair = colors[sum(ord(char) for char in label) % len(colors)]
    image = Image.new("RGBA", (32, 32), color_pair[0])
    draw = ImageDraw.Draw(image)
    for y in range(32):
        ratio = y / 31
        color = tuple(
            round(color_pair[0][index] * (1 - ratio) + color_pair[1][index] * ratio)
            for index in range(3)
        )
        draw.line((0, y, 31, y), fill=color + (255,))

    bbox = draw.textbbox((0, 0), initials)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    draw.text(
        ((32 - text_width) / 2, (32 - text_height) / 2 - 1),
        initials,
        fill=(239, 246, 255, 255),
    )

    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def build_skull_icon(texture_url):
    if not texture_url:
        return None

    skin = fetch_png(texture_url)
    if skin is None:
        return None

    face = skin.crop((8, 8, 16, 16))
    if skin.width >= 64 and skin.height >= 16:
        overlay = skin.crop((40, 8, 48, 16))
        face.alpha_composite(overlay)

    return resize_icon(face)


def build_texture_icon(texture_key):
    if texture_key is None:
        return None

    folder, texture_name = texture_key
    primary_url = f"{TEXTURE_BASE_URL}/{folder}/{texture_name}.png"
    image = fetch_png(primary_url)

    if image is None and folder == "items":
        fallback_url = f"{TEXTURE_BASE_URL}/blocks/{texture_name}.png"
        image = fetch_png(fallback_url)

    if image is None:
        return None

    return resize_icon(image)


def build_material_icon(material):
    return build_texture_icon(get_texture_key(material))


def fetch_neu_item(item_id):
    if item_id in _neu_item_cache:
        return _neu_item_cache[item_id]

    try:
        response = requests.get(NEU_ITEM_URL.format(item_id=item_id), timeout=15)
        if response.status_code == 404:
            _neu_item_cache[item_id] = None
            return None
        response.raise_for_status()
        neu_item = response.json()
    except (requests.RequestException, ValueError):
        neu_item = None

    _neu_item_cache[item_id] = neu_item
    return neu_item


def build_neu_icon(item_id):
    neu_item = fetch_neu_item(item_id)
    if neu_item is None:
        return None

    skin_texture_url = decode_skin_url_from_nbt(neu_item.get("nbttag"))
    if skin_texture_url:
        icon_bytes = build_skull_icon(skin_texture_url)
        if icon_bytes is not None:
            return icon_bytes

    return build_texture_icon(get_neu_texture_key(neu_item))


def get_icon_bytes(item_id, item_metadata):
    if item_id in _icon_cache:
        return _icon_cache[item_id]

    display_name = format_display_name(
        item_metadata.get("display_name", item_id),
        item_id,
    )

    icon_bytes = None
    if item_metadata.get("skin_texture_url"):
        icon_bytes = build_skull_icon(item_metadata["skin_texture_url"])

    if icon_bytes is None:
        icon_bytes = build_wiki_icon(display_name, item_id)

    if icon_bytes is None:
        icon_bytes = build_neu_icon(item_id)

    if icon_bytes is None and item_metadata.get("material"):
        icon_bytes = build_material_icon(item_metadata["material"])

    if icon_bytes is None:
        icon_bytes = build_fallback_icon(display_name)

    if icon_bytes is not None:
        _icon_cache[item_id] = icon_bytes

    return icon_bytes


def fetch_item_metadata():
    response = requests.get(ITEMS_URL, timeout=15)
    response.raise_for_status()

    metadata = {}
    for item in response.json()["items"]:
        texture_url = decode_skin_url(item.get("skin", {}).get("value"))
        metadata[item["id"]] = {
            "display_name": format_display_name(item.get("name", item["id"]), item["id"]),
            "icon_url": f"/api/icons/{item['id']}",
            "material": item.get("material"),
            "durability": item.get("durability"),
            "skin_texture_url": texture_url,
        }
    return metadata


def get_item_metadata():
    global _item_metadata_cache
    global _item_metadata_cache_expires_at

    now = time()
    if _item_metadata_cache and now < _item_metadata_cache_expires_at:
        return _item_metadata_cache

    _item_metadata_cache = fetch_item_metadata()
    _item_metadata_cache_expires_at = now + METADATA_TTL_SECONDS
    return _item_metadata_cache


def get_bazaar_products():
    global _bazaar_products_cache
    global _bazaar_products_cache_expires_at

    now = time()
    if _bazaar_products_cache and now < _bazaar_products_cache_expires_at:
        return _bazaar_products_cache

    try:
        response = requests.get(BAZAAR_URL, timeout=15)
        response.raise_for_status()
        products = response.json()["products"]
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="Failed to fetch Hypixel data") from exc

    _bazaar_products_cache = products
    _bazaar_products_cache_expires_at = now + MARKET_TTL_SECONDS
    return _bazaar_products_cache


def get_bazaar_prices(product):
    if product is None:
        return None, None
    sell_summary = product.get("sell_summary", [])
    buy_summary = product.get("buy_summary", [])
    instant_buy_price = sell_summary[0]["pricePerUnit"] if sell_summary else None
    instant_sell_price = buy_summary[0]["pricePerUnit"] if buy_summary else None
    return instant_buy_price, instant_sell_price


def get_bazaar_unit_cost(item_id, products):
    if item_id == "SKYBLOCK_COIN":
        return 1
    instant_buy_price, _ = get_bazaar_prices(products.get(item_id))
    return instant_buy_price


def calculate_recursive_forge_unit(item_id, products, trail=None):
    """Return cost/time for one item, forcing Forge recipes when one exists."""
    trail = trail or frozenset()
    if item_id in trail:
        return None

    recipe = FORGE_RECIPES.get(item_id)
    if recipe is None:
        bazaar_cost = get_bazaar_unit_cost(item_id, products)
        if bazaar_cost is None:
            return None
        return {
            "cost": bazaar_cost,
            "forge_seconds": 0,
            "forged_components": set(),
            "raw_components": {item_id: 1},
        }

    total_cost = 0
    total_seconds = recipe["duration"]
    forged_components = {item_id}
    raw_components = {}
    next_trail = trail | {item_id}

    for ingredient in recipe["ingredients"]:
        child = calculate_recursive_forge_unit(ingredient["item"], products, next_trail)
        if child is None:
            return None
        amount = ingredient["amount"]
        total_cost += child["cost"] * amount
        total_seconds += child["forge_seconds"] * amount
        forged_components.update(child["forged_components"])
        for raw_item, raw_amount in child["raw_components"].items():
            raw_components[raw_item] = raw_components.get(raw_item, 0) + raw_amount * amount

    output_count = recipe["output_count"]
    return {
        "cost": total_cost / output_count,
        "forge_seconds": total_seconds / output_count,
        "forged_components": forged_components,
        "raw_components": {
            item: amount / output_count for item, amount in raw_components.items()
        },
    }


def ingredient_display_name(item_id, metadata):
    if item_id == "SKYBLOCK_COIN":
        return "Coins"
    item = metadata.get(item_id, {})
    return format_display_name(item.get("display_name"), item_id)


def serialize_raw_components(raw_components, products, metadata):
    result = []
    for item_id, amount in sorted(raw_components.items()):
        unit_price = get_bazaar_unit_cost(item_id, products)
        result.append(
            {
                "item": item_id,
                "display_name": ingredient_display_name(item_id, metadata),
                "amount": amount,
                "unit_price": unit_price,
                "cost": unit_price * amount if unit_price is not None else None,
            }
        )
    return result


def build_forge_items():
    global _forge_market_cache
    global _forge_market_cache_expires_at

    now = time()
    if _forge_market_cache and now < _forge_market_cache_expires_at:
        return _forge_market_cache

    products = get_bazaar_products()
    try:
        metadata = get_item_metadata()
    except (requests.RequestException, ValueError, KeyError, TypeError):
        metadata = {}

    forge_items = []
    for item_id, recipe in FORGE_RECIPES.items():
        _, sale_price = get_bazaar_prices(products.get(item_id))
        if sale_price is None:
            continue

        direct_cost = 0
        direct_available = True
        ingredients = []
        for ingredient in recipe["ingredients"]:
            ingredient_id = ingredient["item"]
            amount = ingredient["amount"]
            unit_price = get_bazaar_unit_cost(ingredient_id, products)
            component_cost = unit_price * amount if unit_price is not None else None
            if component_cost is None:
                direct_available = False
            else:
                direct_cost += component_cost
            ingredients.append(
                {
                    "item": ingredient_id,
                    "display_name": ingredient_display_name(ingredient_id, metadata),
                    "amount": amount,
                    "bazaar_unit_price": unit_price,
                    "bazaar_cost": component_cost,
                    "forgeable": ingredient_id in FORGE_RECIPES,
                }
            )

        recursive = calculate_recursive_forge_unit(item_id, products)
        output_count = recipe["output_count"]
        net_revenue = sale_price * output_count * (1 - TAX_RATE)
        bazaar_component_cost = direct_cost if direct_available else None
        recursive_forge_cost = (
            recursive["cost"] * output_count if recursive is not None else None
        )

        if bazaar_component_cost is None and recursive_forge_cost is None:
            continue

        item_metadata = metadata.get(item_id, {})
        forge_items.append(
            {
                "item": item_id,
                "display_name": format_display_name(
                    item_metadata.get("display_name") or recipe["display_name"], item_id
                ),
                "icon_url": item_metadata.get("icon_url") or f"/api/icons/{item_id}",
                "duration": recipe["duration"],
                "output_count": output_count,
                "sale_price": sale_price,
                "net_revenue": net_revenue,
                "bazaar_component_cost": bazaar_component_cost,
                "bazaar_component_profit": (
                    net_revenue - bazaar_component_cost
                    if bazaar_component_cost is not None
                    else None
                ),
                "recursive_forge_cost": recursive_forge_cost,
                "recursive_forge_profit": (
                    net_revenue - recursive_forge_cost
                    if recursive_forge_cost is not None
                    else None
                ),
                "recursive_forge_seconds": (
                    recursive["forge_seconds"] * output_count
                    if recursive is not None
                    else None
                ),
                "forged_components": (
                    sorted(recursive["forged_components"] - {item_id})
                    if recursive is not None
                    else []
                ),
                "raw_components": (
                    serialize_raw_components(
                        {
                            raw_item: raw_amount * output_count
                            for raw_item, raw_amount in recursive["raw_components"].items()
                        },
                        products,
                        metadata,
                    )
                    if recursive is not None
                    else []
                ),
                "ingredients": ingredients,
            }
        )

    forge_items.sort(
        key=lambda item: max(
            item["bazaar_component_profit"] or float("-inf"),
            item["recursive_forge_profit"] or float("-inf"),
        ),
        reverse=True,
    )
    _forge_market_cache = forge_items
    _forge_market_cache_expires_at = now + MARKET_TTL_SECONDS
    return forge_items


def build_good_items():
    global _market_cache
    global _market_cache_expires_at

    now = time()
    if _market_cache and now < _market_cache_expires_at:
        return _market_cache

    try:
        item_metadata = get_item_metadata()
        products = get_bazaar_products()
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="Failed to fetch Hypixel data") from exc

    good_items = {}
    for item, product in products.items():
        purchase_price, sale_price = get_bazaar_prices(product)

        quick_status = product["quick_status"]
        sell_volume = quick_status["sellMovingWeek"]
        buy_volume = quick_status["buyMovingWeek"]
        volume_balance_score = calculate_volume_balance_score(buy_volume, sell_volume)
        good_volume_score = calculate_good_volume_score(buy_volume, sell_volume)
        buy_coin_volume = calculate_coin_volume(buy_volume, sale_price)
        sell_coin_volume = calculate_coin_volume(sell_volume, purchase_price)
        coin_balance_score = calculate_volume_balance_score(
            buy_coin_volume,
            sell_coin_volume,
        )
        matched_coin_volume = calculate_good_volume_score(
            buy_coin_volume,
            sell_coin_volume,
        )

        profit = 0
        if purchase_price is not None and sale_price is not None:
            profit = sale_price * (1 - TAX_RATE) - purchase_price

        metadata = item_metadata.get(item, {})
        item_data = {
            "item": item,
            "display_name": format_display_name(metadata.get("display_name"), item),
            "icon_url": metadata.get("icon_url") or f"/api/icons/{item}",
            "profit": profit,
            "purchase_price": purchase_price,
            "sale_price": sale_price,
            "buy_volume": buy_volume,
            "sell_volume": sell_volume,
            "instant_buy_volume": quick_status["buyVolume"],
            "instant_sell_volume": quick_status["sellVolume"],
            "volume_balance_score": volume_balance_score,
            "good_volume_score": good_volume_score,
            "buy_coin_volume": buy_coin_volume,
            "sell_coin_volume": sell_coin_volume,
            "coin_balance_score": coin_balance_score,
            "matched_coin_volume": matched_coin_volume,
            "passes_coin_balance_filter": coin_balance_score >= MIN_COIN_BALANCE_SCORE,
            "passes_coin_volume_filter": matched_coin_volume >= MIN_MATCHED_COIN_VOLUME,
            "passes_volume_filter": (
                coin_balance_score >= MIN_COIN_BALANCE_SCORE
                and matched_coin_volume >= MIN_MATCHED_COIN_VOLUME
            ),
        }

        if item_data["passes_volume_filter"]:
            good_items[item] = item_data

    _market_cache = good_items
    _market_cache_expires_at = now + MARKET_TTL_SECONDS
    return good_items


def item_sender():
    return build_good_items()
