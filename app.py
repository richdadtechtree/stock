import os
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime
import yfinance as yf
from kis_client import KISClient, fetch_index_data_yfinance
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Stock Briefing Dashboard API")

# Ensure templates and static directories exist
os.makedirs("templates", exist_ok=True)
os.makedirs("static", exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Instantiate KIS Client (lazily initialized or verified)
kis_client = None
try:
    kis_client = KISClient()
except Exception as e:
    print(f"KISClient initialization warning (will fallback to yfinance): {e}")

import threading

# Cache for historical ATH values. Defaults are high to avoid positive drawdown.
# They will be updated dynamically in the background on startup.
ATH_CACHE = {
    "KOSPI": 3305.21,
    "KOSDAQ": 1062.03,
    "S&P 500": 5669.67
}
last_ath_update = 0

def load_ath_background():
    """
    Fetches the historical max prices in a background thread on startup.
    """
    global last_ath_update
    print("Starting background update of historical ATH values...")
    tickers = {
        "KOSPI": "^KS11",
        "KOSDAQ": "^KQ11",
        "S&P 500": "^GSPC"
    }
    
    for name, ticker in tickers.items():
        try:
            t = yf.Ticker(ticker)
            # Fetch max period to calculate actual historical ATH
            hist = t.history(period="max")
            if not hist.empty:
                max_val = float(hist["Close"].max())
                if max_val > 0:
                    ATH_CACHE[name] = round(max_val, 2)
                    print(f"[Background] Updated ATH for {name}: {max_val}")
        except Exception as e:
            print(f"[Background] Error fetching ATH for {name}: {e}")
            
    last_ath_update = datetime.now().timestamp()
    print("[Background] ATH update completed successfully!")

@app.on_event("startup")
def startup_event():
    # Start ATH fetching in background thread
    threading.Thread(target=load_ath_background, daemon=True).start()


def get_ath_and_drawdown(name, current):
    """
    Returns the ATH and the percent drawdown from the ATH.
    Updates the ATH cache if the current price is a new high.
    """
    if current > ATH_CACHE.get(name, 0):
        ATH_CACHE[name] = round(current, 2)
    ath = ATH_CACHE.get(name, current)
    drawdown = ((current - ath) / ath) * 100 if ath > 0 else 0.0
    return ath, drawdown

@app.get("/api/indices")
def get_indices():
    """
    Endpoint that returns current price, today's change rate, and ATH drawdown.
    Attempts KIS API first for KOSPI/KOSDAQ, uses yfinance for S&P 500 and fallbacks.
    """
    data = {}
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Try fetching KIS first for KOSPI/KOSDAQ
    kis_kospi = None
    kis_kosdaq = None
    
    if kis_client and kis_client.token:
        try:
            kis_kospi = kis_client.get_domestic_index("0001")
            kis_kosdaq = kis_client.get_domestic_index("2001")
        except Exception as e:
            print(f"Error using KIS API: {e}")
            
    # Process KOSPI
    if kis_kospi:
        current = kis_kospi["current"]
        change_rate = kis_kospi["change_rate"]
        ath, ath_change_rate = get_ath_and_drawdown("KOSPI", current)
        data["KOSPI"] = {
            "current": round(current, 2),
            "change_rate": round(change_rate, 2),
            "ath": round(ath, 2),
            "ath_change_rate": round(ath_change_rate, 2),
            "source": "Korea Investment API"
        }
    else:
        # Fallback to yfinance
        try:
            t = yf.Ticker("^KS11")
            hist = t.history(period="5d")
            if not hist.empty:
                current = float(hist["Close"].iloc[-1])
                prev_close = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current
                change_rate = ((current - prev_close) / prev_close) * 100
                ath, ath_change_rate = get_ath_and_drawdown("KOSPI", current)
                data["KOSPI"] = {
                    "current": round(current, 2),
                    "change_rate": round(change_rate, 2),
                    "ath": round(ath, 2),
                    "ath_change_rate": round(ath_change_rate, 2),
                    "source": "Yahoo Finance (Fallback)"
                }
        except Exception as e:
            print(f"Error fetching KOSPI fallback: {e}")

    # Process KOSDAQ
    if kis_kosdaq:
        current = kis_kosdaq["current"]
        change_rate = kis_kosdaq["change_rate"]
        ath, ath_change_rate = get_ath_and_drawdown("KOSDAQ", current)
        data["KOSDAQ"] = {
            "current": round(current, 2),
            "change_rate": round(change_rate, 2),
            "ath": round(ath, 2),
            "ath_change_rate": round(ath_change_rate, 2),
            "source": "Korea Investment API"
        }
    else:
        # Fallback to yfinance
        try:
            t = yf.Ticker("^KQ11")
            hist = t.history(period="5d")
            if not hist.empty:
                current = float(hist["Close"].iloc[-1])
                prev_close = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current
                change_rate = ((current - prev_close) / prev_close) * 100
                ath, ath_change_rate = get_ath_and_drawdown("KOSDAQ", current)
                data["KOSDAQ"] = {
                    "current": round(current, 2),
                    "change_rate": round(change_rate, 2),
                    "ath": round(ath, 2),
                    "ath_change_rate": round(ath_change_rate, 2),
                    "source": "Yahoo Finance (Fallback)"
                }
        except Exception as e:
            print(f"Error fetching KOSDAQ fallback: {e}")

    # Process S&P 500 (Always yfinance since KIS Overseas API setup can be complex)
    try:
        t = yf.Ticker("^GSPC")
        hist = t.history(period="5d")
        if not hist.empty:
            current = float(hist["Close"].iloc[-1])
            prev_close = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current
            change_rate = ((current - prev_close) / prev_close) * 100
            ath, ath_change_rate = get_ath_and_drawdown("S&P 500", current)
            data["S&P 500"] = {
                "current": round(current, 2),
                "change_rate": round(change_rate, 2),
                "ath": round(ath, 2),
                "ath_change_rate": round(ath_change_rate, 2),
                "source": "Yahoo Finance"
            }
    except Exception as e:
        print(f"Error fetching S&P 500: {e}")


    # Add sparkline data for UI charts
    for name, ticker in [("KOSPI", "^KS11"), ("KOSDAQ", "^KQ11"), ("S&P 500", "^GSPC")]:
        if name in data:
            try:
                # Fetch last 30 days for trend sparkline
                hist_month = yf.Ticker(ticker).history(period="30d")
                if not hist_month.empty:
                    prices = hist_month["Close"].tolist()
                    # Normalize prices between 0 and 100 for easy plotting
                    min_p, max_p = min(prices), max(prices)
                    span = max_p - min_p if max_p != min_p else 1
                    norm_prices = [round(((p - min_p) / span) * 100, 1) for p in prices]
                    data[name]["sparkline"] = norm_prices
                else:
                    data[name]["sparkline"] = []
            except Exception as e:
                print(f"Sparkline error for {name}: {e}")
                data[name]["sparkline"] = []

    return {
        "status": "success",
        "timestamp": timestamp,
        "data": data
    }

@app.get("/", response_class=HTMLResponse)
def get_dashboard():
    """
    Serves the main HTML dashboard.
    """
    return FileResponse("templates/index.html")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=port)
