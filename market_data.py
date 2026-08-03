"""
공용 시세 수집 모듈 (코스피/코스닥/S&P500/TQQQ)

- 대시보드(app.py)와 알람 스케줄러(scheduler.py)가 공용으로 사용
- 국내 지수/해외 종목은 한국투자증권 API 우선, 실패 시 yfinance 폴백
- 역대 최고가(ATH)는 yfinance 전체 기간 데이터로 계산해 캐싱
"""
import threading
import time
from datetime import datetime

import requests
import yfinance as yf

from kis_client import KISClient

# Create a custom requests session for yfinance to bypass cloud IP blocks (e.g. on Oracle Cloud, AWS)
YF_SESSION = requests.Session()
YF_SESSION.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
})


# 추적 대상 심볼 정의
# kis_type: 'domestic' (국내지수), 'overseas' (해외주식), None (yfinance 전용)
# S&P 500의 경우 yfinance 차단을 우회하기 위해 KIS 해외주식 API로 SPY ETF를 조회한 뒤 10배를 곱해 지수로 환산합니다.
SYMBOLS = {
    "KOSPI":   {"yf": "^KS11", "kis_type": "domestic", "kis_code": "0001", "default_ath": 3316.08, "max_valid_ath": 3500.0},
    "KOSDAQ":  {"yf": "^KQ11", "kis_type": "domestic", "kis_code": "1001", "default_ath": 1062.03, "max_valid_ath": 1200.0},
    "S&P 500": {"yf": "^GSPC", "kis_type": "overseas", "kis_code": ("AMS", "SPY"), "default_ath": 7620.90, "max_valid_ath": 8500.0},
    "NASDAQ":  {"yf": "^IXIC", "kis_type": "overseas", "kis_code": ("NAS", "QQQ"), "default_ath": 27190.21, "max_valid_ath": 30000.0},
    "QLD":     {"yf": "QLD",   "kis_type": "overseas", "kis_code": ("NAS", "QLD"),  "default_ath": 105.00, "max_valid_ath": 120.0},
    "TQQQ":    {"yf": "TQQQ",  "kis_type": "overseas", "kis_code": ("NAS", "TQQQ"), "default_ath": 88.09, "max_valid_ath": 100.0},
}


# 네이버 금융을 1순위로 조회할 심볼 (지수 실값이 정확한 것들).
# 코스피·코스닥은 네이버 국내지수, S&P500·나스닥은 네이버 해외지수(.INX/.IXIC)로 실값을 바로 받습니다.
# TQQQ·QLD는 개별 ETF라 여기에 넣지 않고 기존 순서(한투 우선)를 유지합니다.
NAVER_FIRST_SYMBOLS = {"KOSPI", "KOSDAQ", "S&P 500", "NASDAQ"}

# 역대 최고가 캐시 (기본값은 안전용, 시작 시 load_ath_from_history()로 갱신)
ATH_CACHE = {name: info["default_ath"] for name, info in SYMBOLS.items()}

_kis_client = None
_kis_init_tried = False

# 스냅샷 캐시 (yfinance 중복 호출 방지)
SNAPSHOT_TTL = 60      # seconds
SPARKLINE_TTL = 300    # seconds
_snapshot_cache = {"ts": 0, "data": None}
_sparkline_cache = {"ts": 0, "data": None}
_custom_snapshot_cache = {"ts": 0, "data": None}
_lock = threading.Lock()


def get_kis_client():
    """Lazily instantiates the KIS client once per process."""
    global _kis_client, _kis_init_tried
    if not _kis_init_tried:
        _kis_init_tried = True
        try:
            _kis_client = KISClient()
        except Exception as e:
            print(f"KISClient initialization warning (fallback to yfinance): {e}")
            _kis_client = None
    if _kis_client and _kis_client.token:
        return _kis_client
    return None


def load_ath_from_history():
    """
    yfinance 전체 기간 데이터로 각 심볼의 역대 최고가(ATH)를 계산해 캐시를 갱신.
    프로세스 시작 시 백그라운드에서 1회 호출 권장.
    비정상적인 아웃라이어(데어터 오류 데드크로스/스파이크)는 상한선(max_valid_ath)으로 차단.
    """
    print("Loading historical ATH values...")
    for name, info in SYMBOLS.items():
        try:
            hist = yf.Ticker(info["yf"], session=YF_SESSION).history(period="max")
            if not hist.empty:
                max_val = float(hist["High"].max())
                max_limit = info.get("max_valid_ath", 999999.0)
                if max_val > max_limit:
                    print(f"[ATH] Ignored glitchy high value {max_val} for {name} (Limit: {max_limit})")
                    continue
                if max_val > ATH_CACHE.get(name, 0):
                    ATH_CACHE[name] = round(max_val, 2)
                    print(f"[ATH] {name}: {ATH_CACHE[name]}")
        except Exception as e:
            print(f"[ATH] Error fetching history for {name}: {e}")
    print("ATH load completed.")


def get_ath_and_drawdown(name, current):
    """
    역대 최고가와 고점 대비 하락률(%)을 반환.
    현재가가 캐시된 ATH보다 높으면 신고점으로 캐시 갱신.
    """
    if current > ATH_CACHE.get(name, 0):
        ATH_CACHE[name] = round(current, 2)
    ath = ATH_CACHE.get(name, current)
    drawdown = ((current - ath) / ath) * 100 if ath > 0 else 0.0
    return ath, drawdown


def _fetch_yf_quote(name):
    """yfinance로 현재가/전일대비 등락률 조회."""
    info = SYMBOLS[name]
    hist = yf.Ticker(info["yf"], session=YF_SESSION).history(period="5d")
    if hist.empty:
        return None
    current = float(hist["Close"].iloc[-1])
    prev_close = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current
    change_rate = ((current - prev_close) / prev_close) * 100 if prev_close else 0.0
    return {"current": current, "change_rate": change_rate}


def _fetch_kis_quote(name):
    """한투 API로 현재가/등락률 조회 (국내지수 / 해외주식)."""
    info = SYMBOLS[name]
    client = get_kis_client()
    if not client or not info["kis_type"]:
        return None
    try:
        if info["kis_type"] == "domestic":
            res = client.get_domestic_index(info["kis_code"])
            # 모의투자 등에서 0 혹은 비정상 값이 오는 경우 None 처리하여 yfinance 폴백 유도
            if res and res.get("current", 0) > 0:
                return res
        if info["kis_type"] == "overseas":
            exchange, symbol = info["kis_code"]
            res = client.get_overseas_price(symbol, exchange)
            if res and res.get("current", 0) > 0:
                return res
    except Exception as e:
        print(f"KIS quote error for {name}: {e}")
    return None


def _fetch_naver_quote(name):
    """네이버 금융 비공식 API로 주가/등락률 조회 (해외주식/국내지수 폴백용)."""
    naver_codes = {
        "KOSPI": "KOSPI",
        "KOSDAQ": "KOSDAQ",
        "S&P 500": ".INX",
        "NASDAQ": ".IXIC",
        "QLD": "QLD",
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
        elif name in ["S&P 500", "NASDAQ"]:
            url = f"https://api.stock.naver.com/index/{code}/basic"
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code == 200:
                data = res.json()
                current = float(data.get("closePrice").replace(",", ""))
                change_rate = float(data.get("fluctuationsRatio", 0))
                return {"current": current, "change_rate": change_rate}
        else:
            url = f"https://api.stock.naver.com/stock/{code}/basic"
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code == 200:
                data = res.json()
                current = float(data.get("closePrice").replace(",", ""))
                diff = float(data.get("compareToPreviousClosePrice", "0").replace(",", ""))
                prev = current - diff
                change_rate = (diff / prev) * 100 if prev else 0.0
                return {"current": current, "change_rate": change_rate}
    except Exception as e:
        print(f"Naver quote error for {name}: {e}")
    return None


def _fetch_sparklines():
    """최근 30일 종가를 0~100으로 정규화한 스파크라인 데이터."""
    result = {}
    for name, info in SYMBOLS.items():
        try:
            hist = yf.Ticker(info["yf"], session=YF_SESSION).history(period="30d")
            if hist.empty:
                result[name] = []
                continue
            prices = hist["Close"].tolist()
            min_p, max_p = min(prices), max(prices)
            span = max_p - min_p if max_p != min_p else 1
            result[name] = [round(((p - min_p) / span) * 100, 1) for p in prices]
        except Exception as e:
            print(f"Sparkline error for {name}: {e}")
            result[name] = []
    return result


def get_snapshot(include_sparkline=False, use_cache=True):
    """
    전체 심볼 스냅샷 반환:
    {name: {current, change_rate, ath, ath_change_rate, source[, sparkline]}}
    """
    with _lock:
        now = time.time()
        if use_cache and _snapshot_cache["data"] and now - _snapshot_cache["ts"] < SNAPSHOT_TTL:
            data = {k: dict(v) for k, v in _snapshot_cache["data"].items()}
        else:
            data = {}
            for name in SYMBOLS:
                quote = None
                source = "None"

                # 지수(코스피·코스닥·S&P500·나스닥)는 네이버 금융이 '지수 실값'을 정확히 제공하므로
                # 네이버를 1순위로 사용합니다. 한투 API는 모의투자/지연 시세라 마감 지수가 어긋나서
                # 폴백으로만 씁니다. (TQQQ·QLD 같은 개별 ETF는 기존대로 한투 우선)
                if name in NAVER_FIRST_SYMBOLS:
                    quote = _fetch_naver_quote(name)
                    if quote:
                        source = "Naver Finance"

                # 1. 한국투자증권(KIS) API 시도 (지수는 폴백, ETF는 1순위)
                if not quote and SYMBOLS[name]["kis_type"]:
                    quote = _fetch_kis_quote(name)
                    source = "Korea Investment API"

                # 2. 한투 API가 실패했거나 설정되지 않은 경우 Yahoo Finance 시도
                if not quote:
                    try:
                        quote = _fetch_yf_quote(name)
                        source = "Yahoo Finance"
                    except Exception as e:
                        print(f"yfinance quote error for {name}: {e}")
                        quote = None

                # 3. 한투/야후 모두 실패 시 실시간/종가 수집이 가능한 네이버 금융 폴백
                if not quote:
                    quote = _fetch_naver_quote(name)
                    source = "Naver Finance"
                        
                if not quote:
                    continue
                current = quote["current"]
                # S&P 500은 KIS에서 SPY ETF로 가져왔으므로 지수 스케일(10.03배)로 환산
                if name == "S&P 500" and source.startswith("Korea"):
                    current = current * 10.03
                # NASDAQ은 KIS에서 QQQ ETF로 가져왔으므로 지수 스케일(36.93배)로 환산
                if name == "NASDAQ" and source.startswith("Korea"):
                    current = current * 36.93
                ath, ath_change_rate = get_ath_and_drawdown(name, current)
                data[name] = {
                    "current": round(current, 2),
                    "change_rate": round(quote["change_rate"], 2),
                    "ath": round(ath, 2),
                    "ath_change_rate": round(ath_change_rate, 2),
                    "source": source,
                }
            _snapshot_cache["ts"] = now
            _snapshot_cache["data"] = {k: dict(v) for k, v in data.items()}

        if include_sparkline:
            # If cache is missing or expired, run update in a background thread to prevent blocking
            if not _sparkline_cache["data"] or now - _sparkline_cache["ts"] >= SPARKLINE_TTL:
                def update_sparklines_async():
                    try:
                        res = _fetch_sparklines()
                        with _lock:
                            _sparkline_cache["data"] = res
                            _sparkline_cache["ts"] = time.time()
                    except Exception as e:
                        print(f"Error in async sparkline update: {e}")
                
                # If cache is completely empty, initialize it to empty lists for all symbols
                if not _sparkline_cache["data"]:
                    _sparkline_cache["data"] = {k: [] for k in SYMBOLS}
                
                # Start background thread
                threading.Thread(target=update_sparklines_async, daemon=True).start()
                
            for name in data:
                data[name]["sparkline"] = _sparkline_cache["data"].get(name, [])

        return data


def parse_monitored_stocks():
    """monitored_stocks.json 파일에서 모니터링 대상 주식/ETF 목록을 읽어옵니다. 파일이 없으면 기본값으로 생성합니다."""
    import json
    import os
    
    file_path = "monitored_stocks.json"
    default_stocks = {
        "005930": "삼성전자",
        "371160": "TIGER 미국필반나",
        "AAPL": "애플",
        "TSLA": "테슬라"
    }
    
    if not os.path.exists(file_path):
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(default_stocks, f, indent=4, ensure_ascii=False)
            print(f"Created default monitored stocks file: {file_path}")
        except Exception as e:
            print(f"Error creating default {file_path}: {e}")
        return default_stocks
        
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return default_stocks


def _fetch_custom_quote(symbol):
    """
    개별 커스텀 종목(국내 6자리 코드 또는 해외 티커)의 시세를 가져옵니다.
    """
    client = get_kis_client()
    
    if symbol.isdigit():
        # 국내 주식 / ETF
        # 1. KIS 국내 주가 API 우선 시도
        if client:
            try:
                res = client.get_domestic_price(symbol)
                if res and res.get("current", 0) > 0:
                    return {
                        "current": res["current"],
                        "change_rate": res["change_rate"],
                        "source": "Korea Investment API"
                    }
            except Exception as e:
                print(f"KIS domestic quote error for {symbol}: {e}")
        
        # 2. 실패 시 yfinance 폴백 (KOSPI .KS 우선, 실패 시 KOSDAQ .KQ 시도)
        for suffix in [".KS", ".KQ"]:
            try:
                hist = yf.Ticker(symbol + suffix, session=YF_SESSION).history(period="2d")
                if not hist.empty:
                    current = float(hist["Close"].iloc[-1])
                    prev_close = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current
                    change_rate = ((current - prev_close) / prev_close) * 100 if prev_close else 0.0
                    return {
                        "current": current,
                        "change_rate": change_rate,
                        "source": "Yahoo Finance"
                    }
            except Exception as e:
                print(f"yfinance quote error for {symbol}{suffix}: {e}")
                
    else:
        # 해외 주식 / ETF (e.g. AAPL, VOO, QQQ)
        # 1. yfinance 우선 시도 (미국의 경우 심볼 매칭이 매우 신뢰성 있음)
        try:
            hist = yf.Ticker(symbol, session=YF_SESSION).history(period="2d")
            if not hist.empty:
                current = float(hist["Close"].iloc[-1])
                prev_close = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current
                change_rate = ((current - prev_close) / prev_close) * 100 if prev_close else 0.0
                return {
                    "current": current,
                    "change_rate": change_rate,
                    "source": "Yahoo Finance"
                }
        except Exception as e:
            print(f"yfinance quote error for US symbol {symbol}: {e}")
            
        # 2. 실패 시 KIS 해외 주가 API 폴백 (거래소 순차 시도)
        if client:
            for ex in ["NAS", "NYS", "AMS"]:
                try:
                    res = client.get_overseas_price(symbol, ex)
                    if res and res.get("current", 0) > 0:
                        return {
                            "current": res["current"],
                            "change_rate": res["change_rate"],
                            "source": "Korea Investment API"
                        }
                except Exception as e:
                    print(f"KIS overseas quote error for {symbol} on {ex}: {e}")
                    
    return None


def get_custom_stocks_snapshot(use_cache=True):
    """
    모니터링 대상 커스텀 종목들의 현재 스냅샷을 반환합니다. (병렬 처리로 로딩 속도 최적화)
    """
    global _custom_snapshot_cache
    with _lock:
        now = time.time()
        if use_cache and _custom_snapshot_cache["data"] and now - _custom_snapshot_cache["ts"] < SNAPSHOT_TTL:
            return {k: dict(v) for k, v in _custom_snapshot_cache["data"].items()}
        
        stocks = parse_monitored_stocks()
        data = {}
        
        import concurrent.futures
        
        def fetch_task(symbol, name):
            try:
                quote = _fetch_custom_quote(symbol)
                if quote:
                    return symbol, {
                        "name": name,
                        "current": round(quote["current"], 2),
                        "change_rate": round(quote["change_rate"], 2),
                        "source": quote["source"],
                        "is_etf": "etf" in name.lower() or "etf" in symbol.lower() or symbol.endswith("ETF")
                    }
            except Exception as e:
                print(f"Error fetching quote in parallel for {symbol}: {e}")
            return symbol, None

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(fetch_task, symbol, name) for symbol, name in stocks.items()]
            for future in concurrent.futures.as_completed(futures):
                symbol, res = future.result()
                if res:
                    data[symbol] = res
                    
        # 원래 monitored_stocks.json에 정의된 순서대로 정렬하여 반환
        ordered_data = {}
        for symbol in stocks.keys():
            if symbol in data:
                ordered_data[symbol] = data[symbol]
                
        _custom_snapshot_cache["ts"] = now
        _custom_snapshot_cache["data"] = {k: dict(v) for k, v in ordered_data.items()}
        return ordered_data


if __name__ == "__main__":
    import json
    load_ath_from_history()
    snap = get_snapshot()
    print("=== MAIN SNAPSHOT ===")
    print(json.dumps(snap, indent=2, ensure_ascii=False))
    print("\n=== CUSTOM STOCKS SNAPSHOT ===")
    custom_snap = get_custom_stocks_snapshot(use_cache=False)
    print(json.dumps(custom_snap, indent=2, ensure_ascii=False))
