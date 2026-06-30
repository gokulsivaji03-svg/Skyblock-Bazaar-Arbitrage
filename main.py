import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import cache, history, scheduler
from app.arb import TAX_RATE, analyze, analyze_screener
from app.forge import analyze_forge
from app.forge import TAX_RATE as FORGE_TAX_RATE


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm the cache and start the background refresher/snapshotter.
    scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(
    title="Forge & Flip",
    description="Hypixel SkyBlock Bazaar flip & Forge craft arbitrage",
    version="1.2",
    lifespan=lifespan,
)

# Allow overriding CORS origins for deployment (comma-separated env var).
_origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api")
def api_root():
    return {"message": "Forge & Flip API", "status": "/api/status"}


@app.get("/api/status")
def api_status():
    """Cache freshness + history stats for health checks and the UI."""
    return {
        "cache": cache.status(),
        "history": history.stats(),
        "auction": {"wip": True},
    }


def _flip(min_profit, min_liquidity, min_price, min_volume, tax_rate):
    return analyze(
        min_profit=min_profit,
        min_liquidity_rating=min_liquidity,
        min_price=min_price,
        min_volume=min_volume,
        tax_rate=tax_rate,
    )


@app.get("/api/bazaar")
def bazaar_screener_api(min_volume: int = 0, tax_rate: float = TAX_RATE):
    return analyze_screener(min_volume=min_volume, tax_rate=tax_rate)


@app.get("/api/flip")
def flip_arb_api(
    min_profit: float = 0,
    min_liquidity: float = 0,
    min_price: float = 1,
    min_volume: int = 1000,
    tax_rate: float = TAX_RATE,
):
    return _flip(min_profit, min_liquidity, min_price, min_volume, tax_rate)


@app.get("/flip")
def flip_arb(
    min_profit: float = 0,
    min_liquidity: float = 0,
    min_price: float = 1,
    min_volume: int = 1000,
    tax_rate: float = TAX_RATE,
):
    return _flip(min_profit, min_liquidity, min_price, min_volume, tax_rate)


@app.get("/api/forge")
def forge_arb_api(use_orders: bool = False, min_profit: float = 0, tax_rate: float = FORGE_TAX_RATE):
    return analyze_forge(min_profit=min_profit, use_orders=use_orders, tax_rate=tax_rate)


@app.get("/forge")
def forge_arb(use_orders: bool = False, min_profit: float = 0, tax_rate: float = FORGE_TAX_RATE):
    return analyze_forge(min_profit=min_profit, use_orders=use_orders, tax_rate=tax_rate)


@app.get("/api/history/{product_id}")
def price_history(product_id: str, hours: float = 24):
    """Time-ordered price/volume points for a Bazaar product."""
    normalized = product_id.upper()
    return {
        "product_id": normalized,
        "hours": hours,
        "points": history.get_history(normalized, hours=hours),
    }


@app.get("/api/player/{username}")
def player_lookup(username: str, profile: str = None):
    """Best-effort player profile (purse, bank, level, HOTM) for personalization."""
    from app import player

    try:
        return player.lookup(username, profile)
    except player.LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Lookup failed: {exc}")


# Serve the built frontend (production) when present, so a single process can
# host both the API and the SPA. In dev the Vite server handles the UI instead.
_DIST = os.path.join(os.path.dirname(__file__), "app", "page", "dist")
if os.path.isdir(_DIST):
    from fastapi.responses import FileResponse

    @app.get("/", include_in_schema=False)
    def spa_index():
        """Always revalidate index.html so hashed asset URLs stay fresh after deploy."""
        return FileResponse(
            os.path.join(_DIST, "index.html"),
            media_type="text/html",
            headers={"Cache-Control": "no-cache"},
        )

    app.mount("/", StaticFiles(directory=_DIST, html=True), name="spa")
else:

    @app.get("/")
    def dev_root():
        return {"message": "Forge & Flip API (dev). Run the Vite dev server for the UI.", "status": "/api/status"}


if __name__ == "__main__":
    for item, key in analyze().items():
        print(f"{item}, profit: {key}")
