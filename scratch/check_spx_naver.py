import requests
import json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

url = "https://api.stock.naver.com/index/SPI@SPX/basic"
try:
    res = requests.get(url, headers=headers, timeout=5)
    print("SPI@SPX Status:", res.status_code)
    if res.status_code == 200:
        print(json.dumps(res.json(), indent=2, ensure_ascii=False))
except Exception as e:
    print("error:", e)
