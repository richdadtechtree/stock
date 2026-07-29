import requests

def test_fetch_naver_quote(name):
    naver_codes = {
        "KOSPI": "KOSPI",
        "KOSDAQ": "KOSDAQ",
        "S&P 500": "SPY",
        "TQQQ": "TQQQ.O"
    }
    code = naver_codes.get(name)
    if not code:
        return None
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        if name in ["KOSPI", "KOSDAQ"]:
            url = f"https://m.stock.naver.com/api/index/{code}/basic"
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code == 200:
                data = res.json()
                current = float(data.get("closePrice").replace(",", ""))
                change_rate = float(data.get("compareToPreviousCloseRate", 0))
                return {"current": current, "change_rate": change_rate}
        else:
            url = f"https://api.stock.naver.com/stock/{code}/basic"
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code == 200:
                data = res.json()
                current = float(data.get("closePrice").replace(",", ""))
                
                # Find basePrice (previous close)
                base_price = None
                for info in data.get("stockItemTotalInfos", []):
                    if info.get("code") == "basePrice":
                        try:
                            base_price = float(info.get("value").replace(",", ""))
                        except ValueError:
                            pass
                        break
                
                if base_price and base_price != 0:
                    change_rate = ((current - base_price) / base_price) * 100
                else:
                    diff = float(data.get("compareToPreviousClosePrice", "0").replace(",", ""))
                    prev = current - diff
                    change_rate = (diff / prev) * 100 if prev else 0.0
                    
                return {"current": current, "change_rate": change_rate, "base_price": base_price}
    except Exception as e:
        print(f"Error {name}: {e}")
    return None

print("TQQQ:", test_fetch_naver_quote("TQQQ"))
print("S&P 500:", test_fetch_naver_quote("S&P 500"))
