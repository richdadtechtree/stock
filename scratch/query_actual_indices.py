import requests
import json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

# Naver has index endpoints. Let's try some common codes:
# S&P 500 index is often .SPX or SPI@SPX or similar in Naver. Let's query:
urls = {
    "S&P 500 index": "https://api.stock.naver.com/index/.SPX/basic",
    "Nasdaq Composite index": "https://api.stock.naver.com/index/.IXIC/basic",
}

for name, url in urls.items():
    try:
        res = requests.get(url, headers=headers, timeout=5)
        print(name, "Status:", res.status_code)
        if res.status_code == 200:
            print(json.dumps(res.json(), indent=2, ensure_ascii=False))
    except Exception as e:
        print(name, "error:", e)
