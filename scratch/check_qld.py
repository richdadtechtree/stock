import yfinance as yf
import requests

try:
    hist = yf.Ticker("QLD").history(period="max")
    print("Max price:", hist['Close'].max())
except Exception as e:
    print("yf error:", e)

# Naver API check
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}
res = requests.get("https://api.stock.naver.com/stock/QLD/basic", headers=headers)
print("Naver data:", res.json().get("closePrice"), res.json().get("compareToPreviousClosePrice"))
