from app.arb import analyze
from app.api import getData
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
     title = "Bazaar Arb",
     description = "Hypixel Skyblock Bazaar arbitrage",
     version = "1.1"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"], # Vite's default port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Hello World"}

@app.get("/api/flip")
def flip_arb_api():
     return analyze()

@app.get("/flip")
def flip_arb():
     return analyze()

if __name__ == "__main__":
        for item, key in analyze().items():
            print(f"{item}, profit: {key}")