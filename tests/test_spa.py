"""Offline checks for the built SPA (run after npm run build)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "app" / "page" / "dist"


def _read_assets():
    assert DIST.is_dir(), "Run `cd app/page && npm run build` first"
    index = (DIST / "index.html").read_text(encoding="utf-8")
    js_files = list((DIST / "assets").glob("index-*.js"))
    css_files = list((DIST / "assets").glob("index-*.css"))
    assert js_files and css_files, "Missing hashed bundle in dist/assets"
    return index, js_files[0].read_text(encoding="utf-8"), css_files[0].read_text(encoding="utf-8")


def test_dist_index_mounts_app():
    index, _, _ = _read_assets()
    assert 'id="app"' in index
    assert "Outfit" in index or "fonts.googleapis.com" in index


def test_bundle_wires_core_ui():
    _, js, _ = _read_assets()
    for needle in (
        "/api/bazaar",
        "/api/forge",
        "/api/status",
        "skyblock-market-settings",
        "metric-card",
        "dataset.wired",
        "sort-clear",
    ):
        assert needle in js, f"missing {needle} in JS bundle"


def test_stylesheet_has_table_layout():
    _, _, css = _read_assets()
    assert ".col-item" in css
    assert ".sticky-col" in css
    assert "min-width:" in css and "1006px" in css
    assert "color-mix" not in css


def test_no_stale_flip_api_constant():
    _, js, _ = _read_assets()
    assert "FLIP_API_URL" not in js


def test_integration_live_module_has_skip_guard():
  """Ensure live tests do not hard-fail CI without a server."""
  text = (ROOT / "tests" / "test_integration_live.py").read_text(encoding="utf-8")
  assert "skipif" in text
  assert "_server_up" in text
