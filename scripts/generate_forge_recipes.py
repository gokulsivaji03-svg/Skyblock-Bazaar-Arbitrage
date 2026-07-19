#!/usr/bin/env python3
"""Build the compact Forge recipe snapshot used by the API from the NEU repo."""

from argparse import ArgumentParser
import json
from pathlib import Path
import re
import subprocess


MINECRAFT_COLOR_CODE = re.compile(r"§.")


def normalize_number(value):
    numeric_amount = float(value)
    if numeric_amount.is_integer():
        return int(numeric_amount)
    return numeric_amount


def parse_ingredient(value):
    item_id, amount = value.rsplit(":", 1)
    return {"item": item_id, "amount": normalize_number(amount)}


def clean_display_name(value, fallback):
    if not value:
        return fallback.replace("_", " ").title()
    return MINECRAFT_COLOR_CODE.sub("", value)


def get_commit(source):
    try:
        return subprocess.run(
            ["git", "-C", str(source), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


def build_snapshot(source):
    recipes = []
    for item_path in sorted((source / "items").glob("*.json")):
        with item_path.open(encoding="utf-8") as item_file:
            item = json.load(item_file)

        for recipe in item.get("recipes", []):
            if recipe.get("type") != "forge":
                continue
            output_id = recipe.get("overrideOutputId") or item.get("internalname")
            recipes.append(
                {
                    "item": output_id,
                    "display_name": clean_display_name(item.get("displayname"), output_id),
                    "duration": int(recipe["duration"]),
                    "output_count": normalize_number(recipe.get("count", 1)),
                    "ingredients": [parse_ingredient(value) for value in recipe["inputs"]],
                }
            )

    recipes.sort(key=lambda recipe: recipe["item"])
    return {
        "source": "NotEnoughUpdates/NotEnoughUpdates-REPO",
        "source_commit": get_commit(source),
        "recipes": recipes,
    }


def main():
    parser = ArgumentParser()
    parser.add_argument("source", type=Path, help="Path to a NotEnoughUpdates-REPO checkout")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parents[1] / "api" / "forge_recipes.json",
    )
    args = parser.parse_args()

    snapshot = build_snapshot(args.source)
    args.output.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(snapshot['recipes'])} Forge recipes to {args.output}")


if __name__ == "__main__":
    main()
