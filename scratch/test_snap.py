import sys
import os
sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from market_data import get_snapshot
import json

snap = get_snapshot(include_sparkline=False, use_cache=False)
print(json.dumps(snap, indent=2, ensure_ascii=False))
