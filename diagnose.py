import sys
sys.path.append(r"/home/ubuntu/stock/stock")  # Server path support
sys.path.append(r"d:\python work\stock")      # Local path support

import json
from market_data import get_snapshot, get_kis_client, _fetch_naver_world_index

print("--- Naver World Index (real S&P 500) Diagnostic ---")
print("S&P 500 (.INX):", _fetch_naver_world_index(".INX"))

print("\n--- KIS Client Diagnostic ---")
client = get_kis_client()
if client:
    print(f"Mode: {client.mode}")
    print(f"Base URL: {client.base_url}")
    print(f"Token Loaded: {client.token is not None}")
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
