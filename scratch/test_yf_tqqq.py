import yfinance as yf
import requests

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
})

ticker = yf.Ticker("TQQQ", session=session)
try:
    hist = ticker.history(period="7d")
    print("History:")
    print(hist)
except Exception as e:
    print("Error:", e)
