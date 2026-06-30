# Forge & Flip

Forge & Flip is a full-stack market intelligence dashboard for Hypixel SkyBlock. It pulls live marketplace data, calculates after-tax arbitrage opportunities across the Bazaar, the Forge, and the Auction House, scores item liquidity, tracks price history, and surfaces the best plays in a fast, modern web UI.

The frontend is a responsive single-page dashboard with a sticky nav, live KPI cards, a Flip / Forge / Auctions mode switch, instant search, sortable columns, collapsible filters, expandable price-history charts, a personal watchlist with profit alerts, account personalization, light/dark themes, and a one-click refresh.

This project is well suited for a resume or portfolio because it combines external API ingestion, a cached/scheduled data pipeline with persistent history, backend analysis, and frontend product design in one focused app.

![Bazaar Arb screenshot](app/page/src/2026-06-05_16.02.12.png)
![Bazaar Arb additional screenshot](app/page/src/2297E0A5-7AB5-4D7F-BB98-1346449196B3_1_201_a.jpeg)

## Performance Snapshot

- Total gained: 300 million coins
- Trading volume: 6.3 billion coins
- Executed across 570+ trades

## Why It Stands Out

- Built a real-time arbitrage engine spanning three SkyBlock markets: Bazaar flips, Forge crafts, and Auction House BIN snipes.
- Modeled profitability using marketplace tax impact (and the player's Bazaar Flipper perk) instead of raw spread alone.
- Designed a liquidity scoring system to help users avoid low-volume, hard-to-exit trades.
- Engineered a cached, scheduled data pipeline with persistent SQLite price history powering on-demand charts.
- Implemented recursive Forge costing that prices every nested intermediate as the cheaper of "buy it" vs. "forge it yourself".
- Delivered everything through a responsive FastAPI + Vite dashboard with multi-column sorting, saved filters, a watchlist with alerts, and account personalization.

## Features

### Markets & analysis

- Live Bazaar data from the Hypixel public API, plus a full Auction House BIN scan
- Flip profit modeled on the real "buy order → sell offer" method: acquire near the highest buy order, exit near the lowest sell offer, taxed on the sale (net = sellOffer × (1 − tax) − buyOrder)
- Liquidity score and 0-5 liquidity rating for trade quality
- Forge arbitrage: buy raw materials, forge a Bazaar-sellable item, and sell it back for profit, ranked by profit-per-hour with the Heart of the Mountain (HOTM) tier and collections each craft requires
- Recursive Forge costing: nested intermediates (e.g. the Refined Diamond inside a Golden Plate) are priced as the cheaper of "buy from the Bazaar" or "forge it yourself", with the effective HOTM tier aggregated across the chosen chain
- Auction House BIN flips — **work in progress** (see `wip/auction/`, gitignored; tab shows WIP in the UI)

### Bazaar screener (Finviz-style)

- Dense table UI modeled after a stock screener: market cap, P/E, price, 24h change, volume, insta buy/sell, buy order, sell order, and flip profit
- `GET /api/bazaar` returns all Bazaar products with screener metrics
- Market cap ≈ weekly volume × mid price; P/E ≈ mid price ÷ flip profit; change % from SQLite history when available

### Data pipeline

- Cached, scheduled data layer: a background refresher keeps a single warm Bazaar snapshot (with request timeout and graceful failure handling) so every client request is served instantly instead of re-hitting Hypixel
- Persistent price history in SQLite: each refresh appends a per-item snapshot (buy/sell price and weekly volume) with automatic retention pruning
- Auction House scans run on their own (longer) interval and are fetched concurrently across pages
- Health/observability endpoint reporting cache freshness, history stats, and AH scan status

### Dashboard

- Bazaar / Forge / Auctions mode switch with mode-specific KPI cards
- Expandable rows: 24h price-history charts for Bazaar items, full recipe cost breakdowns (with per-ingredient buy/forge method) for Forge crafts
- Watchlist (star any item) plus per-item profit alerts with in-app toasts and optional browser notifications
- Account personalization: look up a player (purse, bank, level, best-effort HOTM) and apply your Bazaar Flipper tax perk, HOTM cap, instant-vs-order forge pricing, and a coin budget
- Budget mode: a "Total @ budget" column = profit × units you can afford
- Server-side filtering: bazaar/flip/forge endpoints accept query params (min profit, min liquidity, min price, min volume, tax rate, order vs. instant pricing)
- Instant search, multi-column sorting, collapsible filters, light/dark themes, and persistent UI settings in `localStorage`
- A live data-freshness pill and graceful loading/empty/error states
- Fast local development with Vite proxying API requests to FastAPI

## Forge Arbitrage

The Hypixel API does not expose Forge recipes, so `app/forge.py` carries a curated
recipe dataset (ingredients, base forge duration, required HOTM tier, and any
collection unlock) sourced from the Hypixel SkyBlock Wiki. Only prices come from
the live Bazaar.

For each Bazaar-sellable Forge output it reports the after-tax profit, profit per
hour (since forging is time-gated), the HOTM tier required, and the base/Quick
Forge durations. Ingredients (including nested intermediates such as the Refined
Diamond inside a Golden Plate) are priced recursively as the cheaper of "buy it
from the Bazaar" or "forge it yourself" — memoized and cycle-safe. The expandable
breakdown shows the chosen method (buy/forge) per ingredient, and the reported
HOTM tier is the highest needed across the chosen forge chain.

## Auction House (WIP)

Auction House flip detection is **not shipped yet**. Experimental code lives in
`wip/auction/` (gitignored) and includes NBT parsing, pet-level grouping, and
avg comp pricing. The dashboard tab is labeled **Auctions WIP** and does not
load live data. Re-enable by moving the module back under `app/` and wiring
`main.py` when ready.

## Personalization

`app/player.py` reuses the keyless SkyCrypt lookup in `test.py` to fetch a
player's purse, bank, SkyBlock level, and (best-effort) Heart of the Mountain
tier — no Hypixel API key required. The dashboard's profile panel uses this to
tailor results: apply your Bazaar Flipper tax perk, cap Forge crafts to your
HOTM tier, choose instant vs. order pricing, and set a coin budget that drives a
"Total @ budget" column.

## Tech Stack

- Backend: Python, FastAPI, Requests, SQLite
- Frontend: JavaScript, Vite, CSS (vanilla SPA, inline SVG charts)
- Tooling: Uvicorn, concurrently, pytest, Docker

## Architecture

`main.py` exposes the FastAPI application, arbitrage endpoints, and the background refresher lifecycle.

`app/cache.py` holds a single thread-safe Bazaar snapshot, refreshed on a TTL with a request timeout and graceful failure handling (stale data is preserved on error).

`app/api.py` provides `getData()`, which now reads from the shared cache instead of hitting Hypixel on every call.

`app/history.py` persists per-item price/volume snapshots to SQLite, with retention pruning and history queries.

`app/scheduler.py` runs a daemon thread that refreshes the cache, appends a history snapshot each cycle, and periodically prunes old rows.

`app/arb.py` transforms raw market data into flip candidates and the Finviz-style Bazaar screener (`analyze_screener`).

`app/bazaar_sectors.py` maps Bazaar product ids to sectors (reserved for future use).

`app/forge.py` holds the Forge recipe dataset and computes forge-craft profitability with recursive buy-vs-forge costing.

`app/player.py` provides best-effort player lookups (purse, bank, level, HOTM) for personalization, reusing the SkyCrypt scraper in `test.py`.

`wip/auction/` — gitignored work-in-progress Auction House module (not loaded by the app).

`app/page/` contains the Vite frontend that renders the dashboard and handles filtering, sorting, charts, watchlist/alerts, personalization, and saved user settings.

`tests/` contains pytest coverage for flip, forge, and bazaar screener math (no network — analyzers are fed mocked payloads).

## Local Setup

### 1. Install backend dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Install frontend dependencies

```bash
cd app/page
npm install
```

### 3. Start the app

Option A: run frontend and backend separately

```bash
# from the repository root
uvicorn main:app --reload
```

```bash
# from app/page
npm run dev
```

Option B: run both from the frontend workspace

```bash
cd app/page
npm run dev:all
```

Frontend: `http://localhost:5173`

Backend: `http://127.0.0.1:8000`

## API Endpoints

- `GET /` - the built SPA in production, or a JSON pointer in dev
- `GET /api` - API root with a pointer to the status endpoint
- `GET /api/status` - cache freshness (last fetch, age, stale flag, errors) and history stats
- `GET /api/bazaar` - Finviz-style Bazaar screener (all products). Params: `min_volume`, `tax_rate`
- `GET /api/flip` - flip arbitrage opportunities. Optional params: `min_profit`, `min_liquidity`, `min_price`, `min_volume`, `tax_rate`
- `GET /flip` - alternate route for the same flip analysis payload (same params)
- `GET /api/forge` - Forge craft profitability. Optional params: `use_orders` (Bazaar orders vs. instant buy/sell), `min_profit`, `tax_rate`
- `GET /forge` - alternate route for the same forge analysis payload (same params)
- `GET /api/player/{username}` - best-effort player profile (purse, bank, level, HOTM). Optional `profile`
- `GET /api/history/{product_id}` - time-ordered price/volume points for a Bazaar product. Optional `hours` (default 24)

Auction endpoints are not exposed while the module is in `wip/auction/`.

### Configuration

The backend reads a few optional environment variables:

- `CORS_ORIGINS` - comma-separated allowed origins (default `http://localhost:5173`)
- `HISTORY_DB_PATH` - SQLite history file location (default `data/bazaar_history.db`)
- `HISTORY_RETENTION_DAYS` - how long to keep history rows (default `7`)
- `PORT` - port for the container entrypoint (default `8000`)

## Testing

```bash
pip install -r requirements-dev.txt
pytest
```

The suite mocks the Bazaar/AH payloads, so it runs offline and covers the
after-tax flip math, liquidity scoring, recursive forge buy-vs-forge selection,
and AH BIN flip ranking.

## Deployment (Docker)

A multi-stage `Dockerfile` builds the Vite frontend, then serves both the API
and the built SPA from a single FastAPI process (the SPA is mounted at `/` when
`app/page/dist` exists).

```bash
docker build -t forge-and-flip .
docker run -p 8000:8000 forge-and-flip
# open http://localhost:8000
```

To serve the built UI without Docker, run `npm run build` in `app/page`, then
start `uvicorn main:app` — FastAPI will detect `app/page/dist` and serve it.

## Example Use Case

A player or tool can query the API or open the dashboard to identify:

- Bazaar flips with strong after-tax profit, healthy volume, and quick fills
- Forge crafts with the best profit-per-hour for their HOTM tier
- Auction House BIN listings priced well below the going rate

## Roadmap

The core build-out (cached/scheduled pipeline, persistent history + charts,
recursive forge costing, Auction House flips, watchlist/alerts, personalization,
tests, and Docker deployment) is complete. Possible future ideas:

- Richer AH item identification (reforges, enchants, attributes, pet levels)
- Per-row sparklines via a bulk history endpoint
- Historical "was profitable yesterday" trend filters and backtesting
- Server-side, multi-user watchlists and push alerts

## Resume-Friendly Project Description

Built a full-stack arbitrage dashboard for the Hypixel SkyBlock Bazaar using FastAPI and Vite. Integrated live market data, implemented profit and liquidity scoring logic, and shipped a responsive UI with sorting, filtering, and persistent client-side settings to help users evaluate profitable in-game trading opportunities in real time.
