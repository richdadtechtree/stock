import os
for k, v in os.environ.items():
    if "KIS" in k:
        print(f"{k}: {'***' if v else 'empty'}")
