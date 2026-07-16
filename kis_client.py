import os
import json
import time
import requests
import yfinance as yf
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Cache file for token
TOKEN_CACHE_FILE = ".token_cache.json"

class KISClient:
    def __init__(self):
        self.app_key = os.getenv("KIS_APP_KEY")
        self.app_secret = os.getenv("KIS_APP_SECRET")
        self.account_no = os.getenv("KIS_ACCOUNT_NO")
        self.mode = os.getenv("KIS_CANV_MODE", "VIRTUAL").upper()
        
        # Base URL based on Mode
        if self.mode == "REAL":
            self.base_url = "https://openapi.koreainvestment.com:9443"
        else:
            self.base_url = "https://openapivts.koreainvestment.com:29443"
            
        self.token = self._get_valid_token()

    def _get_valid_token(self):
        """
        Retrieves a valid token from cache or issues a new one if expired.
        """
        if os.path.exists(TOKEN_CACHE_FILE):
            try:
                with open(TOKEN_CACHE_FILE, "r") as f:
                    cache = json.load(f)
                    # Check if token is still valid (expire minus 1 hour buffer)
                    if cache.get("expires_at", 0) > time.time() + 3600:
                        return cache.get("access_token")
            except Exception as e:
                print(f"Error reading token cache: {e}")

        # Issue new token
        return self._issue_token()

    def _issue_token(self):
        """
        Issues a new token from KIS API and caches it.
        """
        url = f"{self.base_url}/oauth2/tokenP"
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        }
        headers = {"content-type": "application/json"}
        
        try:
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            access_token = data.get("access_token")
            # expires_in is usually 86400 seconds (24 hours)
            expires_in = data.get("expires_in", 86400)
            expires_at = time.time() + expires_in
            
            # Save to cache
            cache_data = {
                "access_token": access_token,
                "expires_at": expires_at,
                "issued_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            with open(TOKEN_CACHE_FILE, "w") as f:
                json.dump(cache_data, f, indent=4)
                
            print("Successfully issued and cached new KIS Access Token.")
            return access_token
        except Exception as e:
            print(f"Failed to issue KIS token: {e}")
            return None

    def get_headers(self, tr_id):
        """
        Returns common headers for KIS API requests.
        """
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P"
        }

    def get_domestic_index(self, code):
        """
        Fetches domestic index current price and rate of change.
        code: '0001' (KOSPI), '2001' (KOSDAQ)
        """
        if not self.token:
            return None
            
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-index-price"
        params = {
            "FID_COND_MRKT_DIV_CODE": "U",
            "FID_INPUT_ISCD": code
        }
        
        try:
            headers = self.get_headers("FHPST04000000")
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data.get("rt_cd") == "0":
                output = data.get("output", {})
                return {
                    "current": float(output.get("bstp_nmix_prpr", 0)),
                    "change_amount": float(output.get("bstp_nmix_prdy_vrss", 0)),
                    "change_rate": float(output.get("bstp_nmix_prdy_ctrt", 0)),
                    "high": float(output.get("bstp_nmix_hgpr", 0)),
                    "low": float(output.get("bstp_nmix_lwpr", 0)),
                }
        except Exception as e:
            print(f"Error fetching KIS index {code}: {e}")
        return None

    def get_account_balance(self):
        """
        Fetches account evaluation balance.
        """
        if not self.token or not self.account_no:
            return None
            
        # Account no parsing
        parts = self.account_no.split("-")
        if len(parts) == 2:
            acc_num, acc_code = parts[0], parts[1]
        else:
            acc_num, acc_code = self.account_no[:8], self.account_no[8:]
            
        # Choose transaction ID based on mode
        tr_id = "TTTC8434R" if self.mode == "REAL" else "VTTC8434R"
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
        
        # Query parameters required by KIS
        params = {
            "CANO": acc_num,
            "ACNT_PRDT_CD": acc_code,
            "AFHR_FLG": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }
        
        try:
            headers = self.get_headers(tr_id)
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data.get("rt_cd") == "0":
                output2 = data.get("output2", [])
                summary = output2[0] if output2 else {}
                return {
                    "total_eval_amt": int(summary.get("tot_evlu_amt", 0)), # 총 평가금액
                    "total_profit_loss": int(summary.get("evlu_amt_smtl_amt", 0)) - int(summary.get("pchs_amt_smtl_amt", 0)), # 평가손익
                    "total_return_rate": float(summary.get("evlu_erng_rt", 0)), # 수익률
                    "holdings": [
                        {
                            "name": x.get("prdt_name"),
                            "qty": int(x.get("hldg_qty")),
                            "eval_amt": int(x.get("eval_amt")),
                            "return_rate": float(x.get("evlu_erng_rt", 0))
                        } for x in data.get("output1", []) if int(x.get("hldg_qty", 0)) > 0
                    ]
                }
        except Exception as e:
            print(f"Error fetching KIS account balance: {e}")
        return None

def fetch_index_data_yfinance():
    """
    Fetches index data (KOSPI, KOSDAQ, S&P 500) using yfinance.
    Calculates historical ATH (All-Time High) dynamically.
    """
    indices = {
        "KOSPI": {"ticker": "^KS11", "ath": 3305.21}, # Default ATH just in case
        "KOSDAQ": {"ticker": "^KQ11", "ath": 1062.03},
        "S&P 500": {"ticker": "^GSPC", "ath": 5669.67} # Updated below
    }
    
    results = {}
    for name, info in indices.items():
        try:
            t = yf.Ticker(info["ticker"])
            # Get historical max to find ATH
            hist_max = t.history(period="max")
            if not hist_max.empty:
                ath = float(hist_max["Close"].max())
            else:
                ath = info["ath"]
                
            # Get today's close or intraday
            today = t.history(period="5d")
            if not today.empty:
                current = float(today["Close"].iloc[-1])
                prev_close = float(today["Close"].iloc[-2]) if len(today) > 1 else current
                change_rate = ((current - prev_close) / prev_close) * 100
                
                # Drawdown from ATH
                ath_change_rate = ((current - ath) / ath) * 100
                
                results[name] = {
                    "current": round(current, 2),
                    "change_rate": round(change_rate, 2),
                    "ath": round(ath, 2),
                    "ath_change_rate": round(ath_change_rate, 2),
                    "history": today["Close"].tolist() # For sparkline
                }
        except Exception as e:
            print(f"yfinance error for {name}: {e}")
            
    return results

if __name__ == "__main__":
    # Diagnostic test run
    print("Testing KIS Client and yfinance...")
    y_data = fetch_index_data_yfinance()
    print("yfinance Index Data:", json.dumps(y_data, indent=2, ensure_ascii=False))
    
    client = KISClient()
    if client.token:
        print("KIS token is valid!")
        kospi = client.get_domestic_index("0001")
        print("KIS KOSPI:", kospi)
        kosdaq = client.get_domestic_index("2001")
        print("KIS KOSDAQ:", kosdaq)
    else:
        print("Could not obtain KIS token. Please verify KIS_APP_KEY and KIS_APP_SECRET in .env.")
