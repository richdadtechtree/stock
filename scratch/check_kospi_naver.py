import requests
import json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}
res = requests.get("https://m.stock.naver.com/api/index/KOSPI/basic", headers=headers, timeout=5)
print(json.dumps(res.json(), indent=2, ensure_ascii=False))
