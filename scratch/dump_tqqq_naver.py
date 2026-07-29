import requests
import json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}
res = requests.get("https://api.stock.naver.com/stock/TQQQ.O/basic", headers=headers, timeout=5)
data = res.json()
# Filter out image URLs to make it readable
clean_data = {k: v for k, v in data.items() if not isinstance(v, str) or not v.startswith("http")}
print(json.dumps(clean_data, indent=2, ensure_ascii=False))
