import requests
import json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}
url = "https://query1.finance.yahoo.com/v8/finance/chart/TQQQ"
res = requests.get(url, headers=headers, timeout=5)
print("Status:", res.status_code)
if res.status_code == 200:
    data = res.json()
    meta = data.get("chart", {}).get("result", [{}])[0].get("meta", {})
    print("Meta:")
    print(json.dumps(meta, indent=2))
