import requests
import json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

symbols = ["^GSPC", "^IXIC", "SPY", "QQQ"]
for symbol in symbols:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d"
    try:
        res = requests.get(url, headers=headers, timeout=5)
        print(symbol, "Status:", res.status_code)
        if res.status_code == 200:
            data = res.json()
            meta = data.get("chart", {}).get("result", [{}])[0].get("meta", {})
            print("  Price:", meta.get("regularMarketPrice"), "PrevClose:", meta.get("previousClose"))
    except Exception as e:
        print(symbol, "error:", e)
