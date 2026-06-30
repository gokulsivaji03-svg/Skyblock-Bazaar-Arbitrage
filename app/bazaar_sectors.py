"""Bazaar product → sector/industry classification.

Hypixel does not tag Bazaar products with skill categories, so we infer sector
from product id patterns (and a few explicit overrides). Used by the Finviz-style
Bazaar screener.
"""

# Explicit overrides for ambiguous ids.
_OVERRIDES = {
    "ROCK": "Mining",
    "HARD_STONE": "Mining",
    "MITHRIL": "Mining",
    "TITANIUM": "Mining",
    "GEMSTONE": "Mining",
    "FLAWED": "Mining",
    "FINE": "Mining",
    "REFINED": "Mining",
    "DWARVEN": "Mining",
    "GLACITE": "Mining",
    "TUNGSTEN": "Mining",
    "UMBER": "Mining",
    "EXPERIENCE_BOTTLE": "Enchanting",
    "GRAND_EXP_BOTTLE": "Enchanting",
    "TITANIC_EXP_BOTTLE": "Enchanting",
    "SUPERIOR": "Enchanting",
    "HOT_POTATO_BOOK": "Enchanting",
    "FUMING_POTATO_BOOK": "Enchanting",
    "RECOMBOBULATOR": "Enchanting",
    "ENCHANTED_BOOK": "Enchanting",
}

# Longest-prefix wins within each sector list.
_SECTOR_RULES = [
    ("Fishing", [
        "RAW_FISH", "SALMON", "PRISMARINE", "SPONGE", "LILY_PAD", "CLAY_BALL",
        "INK_SACK", "PUFFERFISH", "MAGMA_FISH", "SHARK", "TIGER", "WATER",
        "LURE", "DIVER", "CLAY", "SEAWEED", "CORAL", "BARNACLE", "FISH",
    ]),
    ("Foraging", [
        "LOG", "LEAVES", "SAPLING", "MUSHROOM", "OAK", "BIRCH", "SPRUCE",
        "JUNGLE", "ACACIA", "DARK_OAK", "RED_MUSHROOM", "BROWN_MUSHROOM",
        "VINE", "CACTUS_GREEN", "FLOWER", "ROSE", "LILAC", "SUGAR_CANE",
    ]),
    ("Farming", [
        "WHEAT", "CARROT", "POTATO", "PUMPKIN", "MELON", "SEEDS", "CACTUS",
        "SUGAR", "COCO", "COCOA", "BEANS", "LEATHER", "FEATHER", "EGG",
        "MUTTON", "RABBIT", "PORK", "CHICKEN", "BEEF", "MILK", "HAY",
        "CROPIE", "SQUASH", "FERMENTO", "MOOSHROOM", "BARN", "HONEY",
    ]),
    ("Mining", [
        "COBBLESTONE", "COAL", "IRON", "GOLD", "DIAMOND", "LAPIS", "REDSTONE",
        "EMERALD", "QUARTZ", "OBSIDIAN", "GLOWSTONE", "GRAVEL", "SAND",
        "NETHERRACK", "MITHRIL", "TITANIUM", "HARD_STONE", "STONE", "ICE",
        "SNOW", "SULPHUR", "ENDSTONE", "MITHRIL", "REFINED", "PLATE",
        "DWARVEN", "GLACITE", "TUNGSTEN", "UMBER", "GEM", "AMBER", "JADE",
        "SAPPHIRE", "AMETHYST", "RUBY", "JASPER", "OPAL", "AQUAMARINE",
        "CITRINE", "PERIDOT", "ONYX", "FLAWED", "FINE", "FORGE",
    ]),
    ("Combat", [
        "ROTTEN", "BONE", "STRING", "PEARL", "SLIME", "SPIDER", "BLAZE",
        "MAGMA", "ENDER", "GHAST", "SKELETON", "ZOMBIE", "CREEPER",
        "WOLF", "VAMPIRE", "REVENANT", "REAPER", "SOUL", "WITHER",
        "DRAGON", "HYPERION", "BONZO", "SCARF", "LIVID", "SHADOW",
        "ASPECT", "BOW", "SWORD", "HELMET", "CHESTPLATE", "LEGGINGS",
        "BOOTS", "DUNGEON", "STAR", "FEL", "FUMING", "ESSENCE",
    ]),
    ("Wool", ["WOOL"]),
    ("Alchemy", ["POTION", "BREW", "GLOWSTONE_DUST", "NETHER_STALK", "GENESIS"]),
]


def _match_sector(product_id: str) -> str:
    pid = product_id.upper()
    for token, sector in _OVERRIDES.items():
        if token in pid:
            return sector
    for sector, tokens in _SECTOR_RULES:
        for token in tokens:
            if token in pid:
                return sector
    return "Other"


def _industry(product_id: str, sector: str) -> str:
    pid = product_id.upper()
    if pid.startswith("ENCHANTED_"):
        return "Enchanted"
    if "BLOCK" in pid:
        return "Blocks"
    if sector == "Mining" and ("GEM" in pid or "FLAWED" in pid or "FINE" in pid):
        return "Gemstones"
    if sector == "Fishing":
        return "Sea Creatures" if any(x in pid for x in ("SHARK", "TIGER", "WATER")) else "Fish"
    if sector == "Farming":
        return "Crops"
    if sector == "Foraging":
        return "Wood"
    if sector == "Combat":
        return "Drops"
    return sector


def classify(product_id: str) -> dict:
    sector = _match_sector(product_id)
    return {"sector": sector, "industry": _industry(product_id, sector)}
