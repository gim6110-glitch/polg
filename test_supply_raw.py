import sys
import json
import requests
sys.path.insert(0, '/home/dps/stock_ai')
from modules.kis_api import KISApi

kis    = KISApi()
token  = kis._get_token()
headers = {
    "Content-Type":  "application/json",
    "authorization": f"Bearer {token}",
    "appkey":        kis.app_key,
    "appsecret":     kis.app_secret,
    "tr_id":         "FHKST01010900",
}
url    = f"{kis.base_url}/uapi/domestic-stock/v1/quotations/inquire-investor"
params = {
    "FID_COND_MRKT_DIV_CODE": "J",
    "FID_INPUT_ISCD": "005930"
}
res  = requests.get(url, headers=headers, params=params, timeout=10)
data = res.json()
print(json.dumps(data, ensure_ascii=False, indent=2))
