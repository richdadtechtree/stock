import requests

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

possible_urls = [
    "https://api.stock.naver.com/index/.SPX/basic",
    "https://api.stock.naver.com/stock/.SPX/basic",
    "https://api.stock.naver.com/index/.GSPC/basic",
    "https://api.stock.naver.com/stock/.GSPC/basic",
    "https://api.stock.naver.com/index/SPI@SPX/basic",
    "https://api.stock.naver.com/stock/SPI@SPX/basic",
    "https://api.stock.naver.com/index/SPI@GSPC/basic",
    "https://api.stock.naver.com/stock/SPI@GSPC/basic",
    "https://api.stock.naver.com/index/SPX/basic",
    "https://api.stock.naver.com/stock/SPX/basic",
]

for url in possible_urls:
    try:
        res = requests.get(url, headers=headers, timeout=3)
        print(url, "->", res.status_code)
        if res.status_code == 200:
            print("FOUND 200!")
            break
    except Exception as e:
        print(url, "error:", e)
