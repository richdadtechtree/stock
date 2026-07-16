"""
투자 타이밍 트리거 백테스트 스크립트

과거 일봉 데이터를 트리거 엔진에 순서대로 흘려보내
언제 어떤 알람이 발생했을지를 시뮬레이션한다.
(실제 알람 DB는 건드리지 않고 임시 DB 사용)

사용 예:
    python backtest.py                        # 전체 기간
    python backtest.py --start 2020-01-01     # 특정 시작일부터
    python backtest.py --start 2021-11-01 --end 2023-01-01
"""
import argparse
import os
import tempfile
from datetime import datetime

import pandas as pd
import yfinance as yf

from trigger_engine import TriggerEngine

TICKERS = {
    "KOSPI": "^KS11",
    "KOSDAQ": "^KQ11",
    "S&P 500": "^GSPC",
    "TQQQ": "TQQQ",
}


def load_history(start=None, end=None):
    """모든 심볼의 종가 시계열을 날짜 기준으로 병합해 반환."""
    frames = {}
    for name, ticker in TICKERS.items():
        hist = yf.Ticker(ticker).history(period="max", auto_adjust=True)
        if hist.empty:
            print(f"[Warn] No history for {name} ({ticker})")
            continue
        s = hist["Close"]
        s.index = s.index.tz_localize(None).normalize()
        frames[name] = s
    df = pd.DataFrame(frames).sort_index()
    if start:
        df = df[df.index >= pd.Timestamp(start)]
    if end:
        df = df[df.index <= pd.Timestamp(end)]
    # 휴장일 갭은 직전 값으로 채움 (미장/국장 개장일 불일치 대응)
    df = df.ffill()
    return df


def main():
    parser = argparse.ArgumentParser(description="투자 타이밍 트리거 백테스트")
    parser.add_argument("--start", help="시작일 (YYYY-MM-DD)")
    parser.add_argument("--end", help="종료일 (YYYY-MM-DD)")
    args = parser.parse_args()

    print("Loading historical data (yfinance)...")
    df = load_history(args.start, args.end)
    if df.empty:
        print("No data to backtest.")
        return
    print(f"Backtest range: {df.index[0].date()} ~ {df.index[-1].date()} ({len(df)} days)")

    # 임시 DB로 엔진 초기화 (실제 alert_state.db에 영향 없음)
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = TriggerEngine(db_path=tmp.name)

    total_events = 0
    for date, row in df.iterrows():
        snapshot = {
            name: {"current": float(px)}
            for name, px in row.items()
            if pd.notna(px) and px > 0
        }
        if not snapshot:
            continue
        events = engine.check(snapshot, now=str(date.date()))
        for e in events:
            total_events += 1
            flat = e["message"].replace("\n", " / ").replace("*", "")
            print(f"{date.date()}  [{e['symbol']:>7}] {flat}")

    print("-" * 60)
    print(f"Total triggered alerts: {total_events}")
    os.unlink(tmp.name)


if __name__ == "__main__":
    main()
