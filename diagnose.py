import sys
import json
import requests
import yfinance as yf

# Naver quote fetcher test
def fetch_naver_stock(code):
    try:
        url = f"https://api.stock.naver.com/stock/{code}/basic"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            current = float(data.get("closePrice").replace(",", ""))
            diff = float(data.get("compareToPreviousClosePrice", "0").replace(",", ""))
            prev = current - diff
            change_rate = (diff / prev) * 100 if prev else 0.0
            return {"current": current, "change_rate": change_rate, "name": data.get("stockName")}
    except Exception as e:
        print(f"Naver error for {code}: {e}")
    return None

# KIS domestic price test
from kis_client import KISClient
def fetch_kis_domestic_stock(client, code):
    if not client or not client.token:
        return None
    url = f"{client.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": code
    }
    try:
        headers = client.get_headers("FHKST01010100")
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        if data.get("rt_cd") == "0":
            output = data.get("output", {})
            # stck_prpr (주식 현재가), prdy_ctrt (전일 대비율)
            return {
                "current": float(output.get("stck_prpr", 0)),
                "change_rate": float(output.get("prdy_ctrt", 0)),
            }
    except Exception as e:
        print(f"KIS domestic error for {code}: {e}")
    return None

# Run tests
client = KISClient()
print("1. Testing Naver stock fetch:")
for code in ["005930", "371160", "AAPL"]:
    print(f"Code {code}:", fetch_naver_stock(code))

print("\n2. Testing KIS domestic stock fetch:")
if client.token:
    for code in ["005930", "371160"]:
        print(f"Code {code}:", fetch_kis_domestic_stock(client, code))
else:
    print("KIS Token not available")

print("\n3. Testing yfinance stock fetch:")
for ticker in ["005930.KS", "371160.KS", "VOO"]:
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="2d")
        if not hist.empty:
            cur = hist["Close"].iloc[-1]
            prev = hist["Close"].iloc[-2] if len(hist) > 1 else cur
            change = ((cur - prev) / prev) * 100
            print(f"Ticker {ticker}: current={cur}, change={change:.2f}%")
    except Exception as e:
        print(f"yfinance error for {ticker}: {e}")

