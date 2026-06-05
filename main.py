from app.arb import analyze
from app.api import getData

if __name__ == "__main__":
        for item, key in analyze().items():
            print(f"{item}, profit: {key}")
    