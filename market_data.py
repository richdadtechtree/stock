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
    "KOSPI":   {"yf": "^KS11", "kis_type": "domestic", "kis_code": "0001", "default_ath": 3305.21},
    "KOSDAQ":  {"yf": "^KQ11", "kis_type": "domestic", "kis_code": "2001", "default_ath": 1062.03},
    "S&P 500": {"yf": "^GSPC", "kis_type": "overseas", "kis_code": ("AMS", "SPY"), "default_ath": 5669.67},
    "TQQQ":    {"yf": "TQQQ",  "kis_type": "overseas", "kis_code": ("NAS", "TQQQ"), "default_ath": 93.79},
}


# 역대 최고가 캐시 (기본값은 안전용, 시작 시 load_ath_from_history()로 갱신)
ATH_CACHE = {name: info["default_ath"] for name, info in SYMBOLS.items()}

_kis_client = None
_kis_init_tried = False

# 스냅샷 캐시 (yfinance 중복 호출 방지)
SNAPSHOT_TTL = 60      # seconds
SPARKLINE_TTL = 300    # seconds
_snapshot_cache = {"ts": 0, "data": None}
_sparkline_cache = {"ts": 0, "data": None}
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
    """
    print("Loading historical ATH values...")
    for name, info in SYMBOLS.items():
        try:
            hist = yf.Ticker(info["yf"], session=YF_SESSION).history(period="max")
            if not hist.empty:
                max_val = float(hist["Close"].max())
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
                quote = _fetch_kis_quote(name)
                source = "Korea Investment API"
                if not quote:
                    try:
                        quote = _fetch_yf_quote(name)
                    except Exception as e:
                        print(f"yfinance quote error for {name}: {e}")
                        quote = None
                    source = "Yahoo Finance"
                if not quote:
                    continue
                current = quote["current"]
                # S&P 500은 KIS에서 SPY ETF로 가져왔으므로 지수 스케일(10배)로 환산
                if name == "S&P 500" and source.startswith("Korea"):
                    current = current * 10
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
            if not (use_cache and _sparkline_cache["data"] and now - _sparkline_cache["ts"] < SPARKLINE_TTL):
                _sparkline_cache["data"] = _fetch_sparklines()
                _sparkline_cache["ts"] = now
            for name in data:
                data[name]["sparkline"] = _sparkline_cache["data"].get(name, [])

        return data


if __name__ == "__main__":
    import json
    load_ath_from_history()
    snap = get_snapshot()
    print(json.dumps(snap, indent=2, ensure_ascii=False))
