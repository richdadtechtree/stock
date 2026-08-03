"""
KIS(한국투자증권) 기간별 지수 시세 API로 코스피/코스닥의 '역대 최고가'를 뽑아올 수 있는지 확인하는 진단 스크립트.

서버에서 실행하세요:
    cd ~/stock/stock
    source venv/bin/activate
    python3 scratch/check_kis_index_history.py

목적: KIS 과거 데이터 API가 동작하는지, 어떤 필드에 고가가 들어있는지, 계산된
      역대 최고가가 실제와 맞는지 확인. (야후가 막힌 서버에서 ATH를 자동으로 구하기 위함)
"""
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from kis_client import KISClient


def fetch_index_history_high(client, code, period="Y", start="19800101"):
    """
    inquire-daily-indexchartprice (TR: FHKUP03500100) 로 기간별 지수 시세를 받아
    전체 기간의 최고가를 계산해서 돌려줍니다.
    period: 'D'(일) 'W'(주) 'M'(월) 'Y'(년). 역대 최고가는 'Y'(연봉)로 한 번에 훑는 게 유리.
    """
    url = f"{client.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice"
    today = datetime.now().strftime("%Y%m%d")
    params = {
        "FID_COND_MRKT_DIV_CODE": "U",
        "FID_INPUT_ISCD": code,
        "FID_INPUT_DATE_1": start,
        "FID_INPUT_DATE_2": today,
        "FID_PERIOD_DIV_CODE": period,
    }
    headers = client.get_headers("FHKUP03500100")
    res = requests.get(url, headers=headers, params=params, timeout=10)
    print(f"  HTTP {res.status_code}")
    data = res.json()
    print(f"  rt_cd={data.get('rt_cd')}  msg={data.get('msg1')}")

    rows = data.get("output2") or data.get("output1") or []
    if not rows:
        print("  (output2 비어있음 — 전체 응답 키:", list(data.keys()), ")")
        return None

    print(f"  받은 데이터 개수: {len(rows)}")
    print(f"  첫 행 필드들: {list(rows[0].keys())}")
    print(f"  첫 행 값: {rows[0]}")

    # 고가로 보이는 필드 후보들 중 실제로 값이 있는 걸 사용
    high_field_candidates = ["bstp_nmix_hgpr", "bstp_nmix_prpr", "ovrs_nmix_hgpr", "hgpr"]
    highs = []
    used_field = None
    for field in high_field_candidates:
        vals = []
        for r in rows:
            v = r.get(field)
            if v not in (None, "", "0"):
                try:
                    vals.append(float(str(v).replace(",", "")))
                except ValueError:
                    pass
        if vals:
            used_field = field
            highs = vals
            break

    if not highs:
        print("  ⚠️ 고가 필드를 못 찾음. 위 '첫 행 필드들'을 보고 알려주세요.")
        return None

    ath = max(highs)
    print(f"  ✅ 사용한 고가 필드: '{used_field}'  →  계산된 역대 최고가(ATH): {ath:,.2f}")
    return ath


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    client = KISClient()
    if not client.token:
        print("KIS 토큰을 못 받았습니다. .env의 KIS 키를 확인하세요.")
        sys.exit(1)

    for name, code in [("KOSPI", "0001"), ("KOSDAQ", "1001")]:
        print(f"\n===== {name} (code={code}) — 연봉(Y) 기준 역대 최고가 =====")
        try:
            fetch_index_history_high(client, code, period="Y")
        except Exception as e:
            print(f"  에러: {e}")
