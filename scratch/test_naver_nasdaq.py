import requests
import json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

# In Naver Finance, the international index for NASDAQ is usually NAS@IXIC.
# Let's test different URLs
urls = [
    "https://api.stock.naver.com/index/NAS@IXIC/basic",
    "https://api.stock.naver.com/index/.IXIC/basic",
    "https://m.stock.naver.com/api/index/NAS@IXIC/basic"
]

for url in urls:
    try:
        res = requests.get(url, headers=headers, timeout=5)
        print("URL:", url, "Status:", res.status_code)
        if res.status_code == 200:
            print(json.dumps(res.json(), indent=2)[:500])
    except Exception as e:
        print("Error for", url, ":", e)
