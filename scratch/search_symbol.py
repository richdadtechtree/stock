import requests
import json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

# Search Naver for S&P 500 symbol
# Endpoints like: https://ac.finance.naver.com:11002/ac?q=S%26P%20500&q_enc=utf-8&st=111&r_lt=111
url = "https://ac.finance.naver.com:11002/ac"
params = {
    "q": "S&P 500",
    "q_enc": "utf-8",
    "st": "111",
    "r_lt": "111"
}
try:
    res = requests.get(url, headers=headers, params=params, timeout=5)
    print(res.text)
except Exception as e:
    print("Search error:", e)
