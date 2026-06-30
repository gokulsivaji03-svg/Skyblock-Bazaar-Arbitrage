from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

SKYCRYPT_BASE_URL = "https://sky.shiiyu.moe"
REQUEST_TIMEOUT = 30
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}
GET_PROFILE_STATS_LINE = re.compile(
    r'\["(?:\\.|[^"])*getProfileStats(?:\\.|[^"])*",(?P<payload>"(?:\\.|[^"])*")\],?'
)


class LookupError(Exception):
    pass


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_output_path(player: str, profile: str | None, output_arg: str | None) -> Path:
    if output_arg:
        return Path(output_arg).expanduser()

    safe_player = re.sub(r"[^a-zA-Z0-9_-]+", "_", player).strip("_") or "player"
    safe_profile = re.sub(r"[^a-zA-Z0-9_-]+", "_", profile or "selected").strip("_") or "selected"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(f"skyblock_lookup_{safe_player}_{safe_profile}_{timestamp}.json")


def normalize_profile_selector(selector: str) -> str:
    return selector.strip().lower().replace("-", "")


class SkyCryptClient:
    def __init__(self, timeout: int = REQUEST_TIMEOUT) -> None:
        self.timeout = timeout

    def fetch_page(self, player: str, profile: str | None = None) -> tuple[str, str]:
        path_parts = ["stats", player]
        if profile:
            path_parts.append(profile)

        path = "/".join(path_parts)
        url = f"{SKYCRYPT_BASE_URL}/{path}"
        curl_command = [
            "curl",
            "-L",
            "-sS",
            url,
            "--max-time",
            str(self.timeout),
            "-w",
            "\n__HTTP_STATUS__:%{http_code}",
        ]

        for header_name, header_value in BROWSER_HEADERS.items():
            curl_command.extend(["-H", f"{header_name}: {header_value}"])

        try:
            result = subprocess.run(
                curl_command,
                check=False,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise LookupError("curl is required for the no-key SkyCrypt lookup, but it was not found.") from exc

        if result.returncode != 0:
            raise LookupError(f"curl failed while fetching {url}: {result.stderr.strip() or 'unknown error'}")

        marker = "\n__HTTP_STATUS__:"
        if marker not in result.stdout:
            raise LookupError(f"Could not determine the HTTP status for {url}.")

        html, status_code_text = result.stdout.rsplit(marker, 1)
        status_code = int(status_code_text.strip())

        if status_code >= 400:
            raise LookupError(f"SkyCrypt request failed with HTTP {status_code} for {url}")

        if "Attention Required! | Cloudflare" in html or "Sorry, you have been blocked" in html:
            raise LookupError(
                "SkyCrypt blocked the request. Try again later or from a different network."
            )

        return url, html


def extract_serialized_stats_payload(html: str) -> str:
    for line in html.splitlines():
        if "getProfileStats" not in line:
            continue

        match = GET_PROFILE_STATS_LINE.search(line)
        if match:
            return json.loads(match.group("payload"))

    raise LookupError("Could not find embedded SkyBlock profile data in the SkyCrypt page.")


def decode_reference_table(table: list[Any]) -> Any:
    cache: dict[int, Any] = {}
    visiting: set[int] = set()

    def decode_ref(index: int) -> Any:
        if index in cache:
            return cache[index]
        if index in visiting:
            return None

        visiting.add(index)
        raw_value = table[index]

        if isinstance(raw_value, dict):
            decoded_dict: dict[str, Any] = {}
            cache[index] = decoded_dict
            for key, value in raw_value.items():
                decoded_dict[key] = decode_node(value, treat_int_as_ref=True)
            visiting.remove(index)
            return decoded_dict

        if isinstance(raw_value, list):
            decoded_list: list[Any] = []
            cache[index] = decoded_list
            decoded_list.extend(decode_node(item, treat_int_as_ref=True) for item in raw_value)
            visiting.remove(index)
            return decoded_list

        cache[index] = raw_value
        visiting.remove(index)
        return raw_value

    def decode_node(value: Any, *, treat_int_as_ref: bool) -> Any:
        if isinstance(value, bool) or value is None:
            return value
        if isinstance(value, str):
            return value
        if isinstance(value, int):
            if treat_int_as_ref and 0 <= value < len(table):
                return decode_ref(value)
            return value
        if isinstance(value, list):
            return [decode_node(item, treat_int_as_ref=True) for item in value]
        if isinstance(value, dict):
            return {key: decode_node(item, treat_int_as_ref=True) for key, item in value.items()}
        return value

    return decode_ref(0)


def parse_profile_stats(html: str) -> dict[str, Any]:
    serialized_payload = extract_serialized_stats_payload(html)

    try:
        reference_table = json.loads(serialized_payload)
    except json.JSONDecodeError as exc:
        raise LookupError("Embedded SkyCrypt data was present but could not be decoded.") from exc

    if not isinstance(reference_table, list) or not reference_table:
        raise LookupError("Embedded SkyCrypt data had an unexpected format.")

    decoded = decode_reference_table(reference_table)
    if not isinstance(decoded, dict):
        raise LookupError("Decoded SkyCrypt profile data had an unexpected shape.")

    return decoded


def summarize_profiles(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for profile in profiles:
        summaries.append(
            {
                "profile_id": profile.get("profile_id"),
                "cute_name": profile.get("cute_name"),
                "game_mode": profile.get("game_mode"),
                "selected": profile.get("selected", False),
            }
        )
    return summaries


def find_matching_profile(profiles: list[dict[str, Any]], selector: str) -> dict[str, Any] | None:
    normalized_selector = normalize_profile_selector(selector)

    for profile in profiles:
        profile_id = str(profile.get("profile_id") or "")
        cute_name = str(profile.get("cute_name") or "")

        if normalize_profile_selector(profile_id) == normalized_selector:
            return profile
        if cute_name.strip().lower() == selector.strip().lower():
            return profile

    return None


def build_skill_summary(decoded_stats: dict[str, Any]) -> dict[str, Any]:
    skills_section = decoded_stats.get("skills") or {}
    per_skill = skills_section.get("skills") or {}

    return {
        "average_skill_level": skills_section.get("averageSkillLevel"),
        "average_skill_level_with_progress": skills_section.get("averageSkillLevelWithProgress"),
        "total_skill_xp": skills_section.get("totalSkillXp"),
        "skills": per_skill,
    }


def build_export(
    player: str,
    requested_profile: str | None,
    page_url: str,
    decoded_stats: dict[str, Any],
) -> dict[str, Any]:
    available_profiles = summarize_profiles(decoded_stats.get("profiles") or [])

    return {
        "meta": {
            "source": "SkyCrypt embedded page data",
            "source_url": page_url,
            "fetched_at": utc_now_iso(),
            "requested_player": player,
            "requested_profile": requested_profile,
            "official_hypixel_api_used": False,
        },
        "player": {
            "username": decoded_stats.get("username"),
            "display_name": decoded_stats.get("displayName"),
            "uuid": decoded_stats.get("uuid"),
            "rank": decoded_stats.get("rank"),
            "social": decoded_stats.get("social"),
        },
        "selected_profile": {
            "profile_id": decoded_stats.get("profile_id"),
            "cute_name": decoded_stats.get("profile_cute_name"),
            "selected_flag": decoded_stats.get("selected"),
            "skyblock_level": decoded_stats.get("skyblock_level"),
            "joined": decoded_stats.get("joined"),
            "purse": decoded_stats.get("purse"),
            "bank": decoded_stats.get("bank"),
            "personal_bank": decoded_stats.get("personalBank"),
            "fairy_souls": decoded_stats.get("fairySouls"),
            "api_settings": decoded_stats.get("apiSettings"),
        },
        "available_profiles": available_profiles,
        "skill_summary": build_skill_summary(decoded_stats),
        "raw_stats": decoded_stats,
    }


def fetch_player_profile(player: str, profile_selector: str | None = None) -> dict[str, Any]:
    client = SkyCryptClient()

    base_url, base_html = client.fetch_page(player)
    base_stats = parse_profile_stats(base_html)

    if not profile_selector:
        return build_export(player, None, base_url, base_stats)

    profiles = base_stats.get("profiles") or []
    matched_profile = find_matching_profile(profiles, profile_selector)
    if not matched_profile:
        available = ", ".join(
            profile.get("cute_name") or str(profile.get("profile_id"))
            for profile in summarize_profiles(profiles)
        )
        raise LookupError(
            f"Profile '{profile_selector}' was not found. Available profiles: {available or 'none'}"
        )

    canonical_selector = matched_profile.get("profile_id") or matched_profile.get("cute_name")
    selected_url, selected_html = client.fetch_page(player, str(canonical_selector))
    selected_stats = parse_profile_stats(selected_html)
    return build_export(player, profile_selector, selected_url, selected_stats)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Look up Hypixel SkyBlock player data without a Hypixel API key."
    )
    parser.add_argument("player", help="Minecraft username used on SkyCrypt")
    parser.add_argument(
        "--profile",
        help="Optional SkyBlock profile cute name or profile ID to fetch instead of the default selected profile.",
    )
    parser.add_argument(
        "--output",
        help="Output JSON file path. Defaults to ./skyblock_lookup_<player>_<profile>_<timestamp>.json",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indentation level. Defaults to 2.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        export = fetch_player_profile(args.player, args.profile)
    except LookupError as exc:
        print(f"Lookup failed: {exc}", file=sys.stderr)
        return 1
    except requests.RequestException as exc:
        print(f"Network error while fetching SkyCrypt data: {exc}", file=sys.stderr)
        return 1

    output_path = build_output_path(args.player, args.profile, args.output)
    output_path.write_text(
        json.dumps(export, indent=args.indent, ensure_ascii=True),
        encoding="utf-8",
    )

    selected_profile = export["selected_profile"]["cute_name"] or export["selected_profile"]["profile_id"]
    print(f"Exported SkyBlock lookup for {args.player} ({selected_profile}) to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
