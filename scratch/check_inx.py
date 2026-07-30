import requests

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://m.stock.naver.com/'
}

res = requests.get("https://api.stock.naver.com/index/.INX/basic", headers=headers)
print("Status:", res.status_code)
print("Text:", res.text)
