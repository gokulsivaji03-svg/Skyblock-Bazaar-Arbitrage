"""Best-effort player lookup for personalization.

Reuses the keyless SkyCrypt scraper in ``test.py`` to pull a player's purse,
bank, SkyBlock level, and skills. The Heart of the Mountain (HOTM) tier is not
always present in the scraped payload, so it is extracted best-effort and may be
``None`` (the UI lets the user set it manually in that case).
"""

import importlib.util
import os

# Import the sibling top-level module ``test.py`` without relying on it being on
# the path (it lives at the repo root, not inside the ``app`` package).
_spec = importlib.util.spec_from_file_location(
    "sb_player_lookup",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "test.py"),
)
_lookup_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_lookup_mod)

fetch_player_profile = _lookup_mod.fetch_player_profile
LookupError = _lookup_mod.LookupError


def _find_hotm_tier(node, depth=0):
    """Recursively search the decoded stats for a Heart of the Mountain tier."""
    if depth > 8 or node is None:
        return None
    if isinstance(node, dict):
        for key, value in node.items():
            lkey = str(key).lower()
            if "heart_of_the_mountain" in lkey or lkey == "hotm":
                if isinstance(value, (int, float)):
                    return int(value)
                if isinstance(value, dict):
                    for tk in ("tier", "level", "current_tier"):
                        tv = value.get(tk)
                        if isinstance(tv, (int, float)):
                            return int(tv)
            found = _find_hotm_tier(value, depth + 1)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_hotm_tier(item, depth + 1)
            if found is not None:
                return found
    return None


def lookup(username, profile=None):
    """Return a compact personalization profile for ``username``."""
    export = fetch_player_profile(username, profile)
    selected = export.get("selected_profile") or {}
    player = export.get("player") or {}
    skills = (export.get("skill_summary") or {}).get("skills") or {}
    mining = skills.get("mining") or {}

    return {
        "username": player.get("username") or username,
        "uuid": player.get("uuid"),
        "profile": selected.get("cute_name") or selected.get("profile_id"),
        "skyblock_level": selected.get("skyblock_level"),
        "purse": selected.get("purse"),
        "bank": selected.get("bank"),
        "mining_level": mining.get("level"),
        "hotm_tier": _find_hotm_tier(export.get("raw_stats")),
        "available_profiles": export.get("available_profiles") or [],
        "source": "SkyCrypt (keyless)",
    }
