import requests
import json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}
url = "https://query1.finance.yahoo.com/v8/finance/chart/TQQQ?range=max"
res = requests.get(url, headers=headers, timeout=5)
print("Status:", res.status_code)
if res.status_code == 200:
    data = res.json()
    result = data.get("chart", {}).get("result", [{}])[0]
    indicators = result.get("indicators", {}).get("quote", [{}])[0]
    highs = [h for h in indicators.get("high", []) if h is not None]
    if highs:
        print("Max High:", max(highs))
        print("Max High rounded:", round(max(highs), 2))
    else:
        print("No highs found")
