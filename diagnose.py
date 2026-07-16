import sys
sys.path.append(r"/home/ubuntu/stock/stock")  # Server path support
sys.path.append(r"d:\python work\stock")      # Local path support

import json
import requests
from market_data import get_snapshot, get_kis_client, _fetch_naver_world_index

print("--- Naver World Index (real S&P 500) Diagnostic ---")
print("S&P 500 (.INX):", _fetch_naver_world_index(".INX"))

print("\n--- KIS Client Diagnostic ---")
client = get_kis_client()
if client:
    print(f"Mode: {client.mode}")
    print(f"Base URL: {client.base_url}")
    print(f"Token Loaded: {client.token is not None}")

    # 한투 해외시세가 실제로 되는지, 뭘 돌려주는지 '원본 응답'을 그대로 출력
    print("\n--- KIS Overseas RAW response (why S&P500/TQQQ not from KIS) ---")
    url = f"{client.base_url}/uapi/overseas-price/v1/quotations/price"
    for label, excd, symb in [("S&P 500 = SPY", "AMS", "SPY"), ("TQQQ", "NAS", "TQQQ")]:
        try:
            r = requests.get(
                url,
                headers=client.get_headers("HHDFS00000300"),
                params={"AUTH": "", "EXCD": excd, "SYMB": symb},
                timeout=10,
            )
            data = r.json()
            out = data.get("output", {})
            print(f"[{label}] http={r.status_code} rt_cd={data.get('rt_cd')} "
                  f"msg_cd={data.get('msg_cd')} msg='{data.get('msg1')}' "
                  f"last='{out.get('last')}' rate='{out.get('rate')}'")
        except Exception as e:
            print(f"[{label}] KIS overseas request failed: {e}")
else:
    print("Failed to initialize KIS Client")

print("\n--- Market Snapshot Diagnostic ---")
snapshot = get_snapshot(include_sparkline=False, use_cache=False)
for name, data in snapshot.items():
    print(f"Index: {name}")
    print(f"  Current Price: {data.get('current')}")
    print(f"  Source: {data.get('source')}")
    print(f"  ATH: {data.get('ath')}")
    print(f"  Drawdown: {data.get('ath_change_rate')}%")
    print("-" * 30)
