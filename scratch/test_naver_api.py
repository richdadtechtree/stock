import requests
import json
import yfinance as yf

# Naver quote test
def _fetch_naver_quote(name):
    naver_codes = {
        "KOSPI": "KOSPI",
        "KOSDAQ": "KOSDAQ",
        "S&P 500": "SPY",
        "TQQQ": "TQQQ.O"
    }
    code = naver_codes.get(name)
    if not code:
        return None
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        if name in ["KOSPI", "KOSDAQ"]:
            url = f"https://m.stock.naver.com/api/index/{code}/basic"
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code == 200:
                data = res.json()
                current = float(data.get("closePrice").replace(",", ""))
                change_rate = float(data.get("compareToPreviousCloseRate", 0))
                return {"current": current, "change_rate": change_rate, "raw": data}
        else:
            url = f"https://api.stock.naver.com/stock/{code}/basic"
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code == 200:
                data = res.json()
                current = float(data.get("closePrice").replace(",", ""))
                diff = float(data.get("compareToPreviousClosePrice", "0").replace(",", ""))
                prev = current - diff
                change_rate = (diff / prev) * 100 if prev else 0.0
                return {"current": current, "change_rate": change_rate, "raw": data}
    except Exception as e:
        print(f"Error {name}: {e}")
    return None

print("TQQQ from Naver:")
print(json.dumps(_fetch_naver_quote("TQQQ"), indent=2, ensure_ascii=False))

print("S&P 500 from Naver:")
print(json.dumps(_fetch_naver_quote("S&P 500"), indent=2, ensure_ascii=False))
