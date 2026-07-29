import requests
import json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}
res = requests.get("https://api.stock.naver.com/stock/TQQQ.O/basic", headers=headers, timeout=5)
data = res.json()

print("closePrice:", data.get("closePrice"))
print("compareToPreviousClosePrice:", data.get("compareToPreviousClosePrice"))
print("fluctuationsRatio:", data.get("fluctuationsRatio"))
print("localTradedAt:", data.get("localTradedAt"))
print("marketStatus:", data.get("marketStatus"))
print("overMarketPriceInfo:", data.get("overMarketPriceInfo"))
