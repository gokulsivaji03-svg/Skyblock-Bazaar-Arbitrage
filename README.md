# Bazaar Lens

Bazaar Lens is a live market scanner for the Hypixel SkyBlock Bazaar. It narrows the market to items with balanced buy/sell coin flow and meaningful matched weekly liquidity, then makes those signals easy to search, compare, and save.

## What it includes

- Live Bazaar and item metadata from the public Hypixel API
- A 30-second server/CDN market cache to protect the upstream feed
- Summary metrics for liquidity, spread, and balance
- Strategy filters for margin, balance, liquidity, and a device-local watchlist
- Sortable, responsive market results with a detail panel
- Forge crafting arbitrage with strictly separate Bazaar-component and recursive Forge-chain costs
- Layered item icon fallbacks using Hypixel metadata, the SkyBlock Wiki, NEU, and Minecraft assets
- Loading, retry, empty, keyboard, reduced-motion, and mobile states

## Run locally

Install the JavaScript and Python dependencies, then run both services:

```bash
npm install
python3 -m pip install -r requirements.txt
npm run dev:all
```

The web app runs at `http://localhost:5173` and proxies `/api` requests to the FastAPI service at `http://localhost:8001`.

## Deploy to Vercel

The repository is configured as one Vercel project: Vite builds the frontend into `dist`, while `api/index.py` is deployed as a Python Function.

1. Import the repository into Vercel or run `npx vercel` from the project root.
2. Leave the detected framework as **Vite**.
3. Deploy. No environment variables are required for the public Hypixel endpoints.

The deployment configuration is in `vercel.json`. Python is pinned in `.python-version`, and Vercel installs the backend packages from `requirements.txt` automatically.

Production API responses use Vercel's CDN cache: market results revalidate every 30 seconds, and generated item icons remain cached at the edge for 30 days. Function memory is still used as a best-effort warm-instance cache.

## Checks

```bash
npm run build
python3 -m compileall api
python3 -m unittest discover -s tests
```

## Scanner rules

An item qualifies when its buy/sell coin-flow balance is at least 90% and its matched weekly coin volume is at least 100 million coins. Displayed spread accounts for the 1.25% Bazaar tax configured in `api/index.py`.

## Forge recipe data

Forge definitions are stored in `api/forge_recipes.json` as a compact snapshot of the NotEnoughUpdates item repository. To refresh that snapshot from a local NEU repository checkout:

```bash
python3 scripts/generate_forge_recipes.py /path/to/NotEnoughUpdates-REPO
```

The direct route buys every immediate recipe component at the Bazaar instant-buy price. The recursive route forges every forgeable component and only buys terminal raw materials from the Bazaar. Both routes sell the final output at the Bazaar instant-sell price after tax; their costs are never pooled.
