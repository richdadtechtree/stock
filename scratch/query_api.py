import requests
import json

res = requests.get("http://127.0.0.1:8000/api/indices")
print("Status:", res.status_code)
if res.status_code == 200:
    print(json.dumps(res.json(), indent=2, ensure_ascii=False))
else:
    print(res.text)
