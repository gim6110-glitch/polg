import os
import sys
import json
import time
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv('/home/dps/stock_ai/.env')

class KISApi:
    def __init__(self):
        self.app_key    = os.getenv('KIS_APP_KEY')
        self.app_secret = os.getenv('KIS_APP_SECRET')
        self.account    = os.getenv('KIS_ACCOUNT')
        self.is_mock    = os.getenv('KIS_MOCK', 'true').lower() == 'true'

        if self.is_mock:
            self.base_url = "https://openapivts.koreainvestment.com:29443"
        else:
            self.base_url = "https://openapi.koreainvestment.com:9443"

        # 미국 주식은 항상 실전 URL 사용 (모의투자도 동일)
        self.us_base_url = "https://openapi.koreainvestment.com:9443"

        self.token      = None
        self.token_exp  = None
        self.token_file = "/home/dps/stock_ai/data/kis_token.json"

    def _get_token(self):
        if os.path.exists(self.token_file):
            with open(self.token_file, 'r') as f:
                saved = json.load(f)
            exp = datetime.fromisoformat(saved['expires'])
            if datetime.now() < exp - timedelta(minutes=10):
                self.token     = saved['token']
                self.token_exp = exp
                return self.token

        url  = f"{self.base_url}/oauth2/tokenP"
        body = {
            "grant_type": "client_credentials",
            "appkey":     self.app_key,
            "appsecret":  self.app_secret
        }
        try:
            res  = requests.post(url, json=body, timeout=10)
            data = res.json()
            if 'access_token' in data:
                self.token     = data['access_token']
                self.token_exp = datetime.now() + timedelta(hours=12)
                os.makedirs("/home/dps/stock_ai/data", exist_ok=True)
                with open(self.token_file, 'w') as f:
                    json.dump({
                        'token':   self.token,
                        'expires': self.token_exp.isoformat()
                    }, f)
                print("✅ KIS 토큰 발급 완료")
                return self.token
            else:
                print(f"❌ 토큰 발급 실패: {data}")
                return None
        except Exception as e:
            print(f"❌ 토큰 요청 실패: {e}")
            return None

    def _headers(self, tr_id, use_us=False):
        token   = self._get_token()
        base    = self.us_base_url if use_us else self.base_url
        return {
            "Content-Type":  "application/json",
            "authorization": f"Bearer {token}",
            "appkey":        self.app_key,
            "appsecret":     self.app_secret,
            "tr_id":         tr_id,
            "custtype":      "P"
        }, base

    def get_kr_price(self, code):
        """한국 주식 실시간"""
        try:
            headers, base = self._headers("FHKST01010100")
            url    = f"{base}/uapi/domestic-stock/v1/quotations/inquire-price"
            params = {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": code
            }
            res  = requests.get(url, headers=headers, params=params, timeout=10)
            data = res.json()
            if data.get('rt_cd') == '0':
                output = data['output']
                price  = int(output['stck_prpr'])
                hour   = datetime.now().hour

                # 장 마감 후 (15:30~09:00) 종가 표시
                is_closed = not (9 <= hour < 16)
                source    = "KIS종가" if is_closed else "KIS실시간"

                return {
                    "code":       code,
                    "price":      price,
                    "change":     int(output['prdy_vrss']),
                    "change_pct": float(output['prdy_ctrt']),
                    "volume":     int(output['acml_vol']),
                    "high":       int(output['stck_hgpr']),
                    "low":        int(output['stck_lwpr']),
                    "open":       int(output['stck_oprc']),
                    "source":     source,
                    "is_closed":  is_closed,
                    "timestamp":  datetime.now().strftime("%H:%M:%S")
                }
            else:
                print(f"❌ {code}: {data.get('msg1')}")
                return None
        except Exception as e:
            print(f"❌ {code} 조회 실패: {e}")
            return None

    def get_us_price(self, ticker, exchange="NAS"):
        """미국 주식 실시간"""
        try:
            headers, base = self._headers("HHDFS00000300", use_us=True)
            url    = f"{base}/uapi/overseas-price/v1/quotations/price"
            params = {
                "AUTH": "",
                "EXCD": exchange,
                "SYMB": ticker
            }
            res  = requests.get(url, headers=headers, params=params, timeout=10)
            if not res.text.strip():
                # NAS 실패시 NYS 시도
                if exchange == "NAS":
                    return self.get_us_price(ticker, "NYS")
                return None
            data = res.json()
            if data.get('rt_cd') == '0':
                output = data['output']
                def safe_float(val, default=0):
                    try:
                        return float(val) if val and val.strip() else default
                    except:
                        return default

                price = safe_float(output.get('last', 0))
                if price == 0:
                    if exchange == "NAS":
                        return self.get_us_price(ticker, "NYS")
                    return None

                return {
                    "ticker":     ticker,
                    "price":      price,
                    "change":     safe_float(output.get('diff', 0)),
                    "change_pct": safe_float(output.get('rate', 0)),
                    "volume":     int(safe_float(output.get('tvol', 0))),
                    "high":       safe_float(output.get('high', 0)),
                    "low":        safe_float(output.get('low', 0)),
                    "open":       safe_float(output.get('open', 0)),
                    "exchange":   exchange,
                    "source":     "KIS실시간",
                    "timestamp":  datetime.now().strftime("%H:%M:%S")
                }
            else:
                print(f"❌ {ticker}: {data.get('msg1')}")
                return None
        except Exception as e:
            print(f"❌ {ticker} 조회 실패: {e}")
            return None

    def get_kospi(self):
        """코스피 실시간"""
        try:
            headers, base = self._headers("FHPUP02100000")
            url    = f"{base}/uapi/domestic-stock/v1/quotations/inquire-index-price"
            params = {
                "FID_COND_MRKT_DIV_CODE": "U",
                "FID_INPUT_ISCD": "0001"
            }
            res  = requests.get(url, headers=headers, params=params, timeout=10)
            data = res.json()
            if data.get('rt_cd') == '0':
                output = data['output']
                return {
                    "name":       "코스피",
                    "price":      float(output['bstp_nmix_prpr']),
                    "change_pct": float(output['bstp_nmix_prdy_ctrt']),
                    "source":     "KIS실시간",
                    "timestamp":  datetime.now().strftime("%H:%M:%S")
                }
        except Exception as e:
            print(f"❌ 코스피 조회 실패: {e}")
        return None

    def get_kosdaq(self):
        """코스닥 실시간"""
        try:
            headers, base = self._headers("FHPUP02100000")
            url    = f"{base}/uapi/domestic-stock/v1/quotations/inquire-index-price"
            params = {
                "FID_COND_MRKT_DIV_CODE": "U",
                "FID_INPUT_ISCD": "1001"
            }
            res  = requests.get(url, headers=headers, params=params, timeout=10)
            data = res.json()
            if data.get('rt_cd') == '0':
                output = data['output']
                return {
                    "name":       "코스닥",
                    "price":      float(output['bstp_nmix_prpr']),
                    "change_pct": float(output['bstp_nmix_prdy_ctrt']),
                    "source":     "KIS실시간",
                    "timestamp":  datetime.now().strftime("%H:%M:%S")
                }
        except Exception as e:
            print(f"❌ 코스닥 조회 실패: {e}")
        return None

    def get_exchange_rate(self):
        """달러/원 환율 실시간"""
        # 네이버 실시간
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            url     = "https://finance.naver.com/marketindex/exchangeMain.naver"
            res     = requests.get(url, headers=headers, timeout=5)
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(res.text, "html.parser")
            item = soup.select_one("#exchangeList .value")
            if item:
                price = float(item.text.strip().replace(",", ""))
                if price > 0:
                    return {
                        "name":       "달러/원",
                        "price":      price,
                        "change_pct": 0,
                        "source":     "네이버실시간",
                        "timestamp":  datetime.now().strftime("%H:%M:%S")
                    }
        except:
            pass

        # 폴백: yfinance
        try:
            import yfinance as yf
            hist  = yf.Ticker("USDKRW=X").history(period="1d").dropna()
            if not hist.empty:
                price = round(float(hist["Close"].iloc[-1]), 2)
                return {
                    "name":       "달러/원",
                    "price":      price,
                    "change_pct": 0,
                    "source":     "yfinance",
                    "timestamp":  datetime.now().strftime("%H:%M:%S")
                }
        except Exception as e:
            print(f"❌ 환율 조회 실패: {e}")
        return None

    def get_nasdaq(self):
        """나스닥 지수 (yfinance 폴백)"""
        try:
            import yfinance as yf
            df = yf.Ticker("^IXIC").history(period="2d").dropna()
            if len(df) >= 2:
                current    = df['Close'].iloc[-1]
                prev       = df['Close'].iloc[-2]
                change_pct = ((current - prev) / prev) * 100
                return {
                    "name":       "나스닥",
                    "price":      round(current, 2),
                    "change_pct": round(change_pct, 2),
                    "source":     "yfinance(15분지연)",
                    "timestamp":  datetime.now().strftime("%H:%M:%S")
                }
        except Exception as e:
            print(f"❌ 나스닥 조회 실패: {e}")
        return None

    def get_all_realtime(self):
        """전체 실시간 데이터"""
        result = {}
        print("📡 KIS 실시간 데이터 수집 중...")

        # 한국 지수
        for func, name in [(self.get_kospi, "코스피"), (self.get_kosdaq, "코스닥")]:
            data = func()
            if data:
                result[name] = data
                arrow = "▲" if data['change_pct'] > 0 else "▼"
                print(f"  ✅ {name}: {data['price']:,} {arrow}{data['change_pct']:+.2f}% [{data['timestamp']}]")

        # 나스닥 (yfinance)
        nasdaq = self.get_nasdaq()
        if nasdaq:
            result['나스닥'] = nasdaq
            arrow = "▲" if nasdaq['change_pct'] > 0 else "▼"
            print(f"  ✅ 나스닥: {nasdaq['price']:,} {arrow}{nasdaq['change_pct']:+.2f}% (15분지연)")

        # 한국 주요 종목
        kr_stocks = {
            "삼성전자":          "005930",
            "SK하이닉스":        "000660",
            "한화에어로스페이스": "012450",
            "현대차":            "005380",
            "LG에너지솔루션":    "373220",
        }
        for name, code in kr_stocks.items():
            data = self.get_kr_price(code)
            if data:
                result[name] = data
                arrow = "▲" if data['change_pct'] > 0 else "▼"
                print(f"  ✅ {name}: {data['price']:,} {arrow}{data['change_pct']:+.2f}% [{data['timestamp']}]")
            time.sleep(0.3)

        # 미국 주요 종목
        us_stocks = {
            "NVIDIA":    ("NVDA", "NAS"),
            "Apple":     ("AAPL", "NAS"),
            "Tesla":     ("TSLA", "NAS"),
            "Microsoft": ("MSFT", "NAS"),
            "AMD":       ("AMD",  "NAS"),
        }
        for name, (ticker, excd) in us_stocks.items():
            data = self.get_us_price(ticker, excd)
            if data:
                result[name] = data
                arrow = "▲" if data['change_pct'] > 0 else "▼"
                print(f"  ✅ {name}: ${data['price']} {arrow}{data['change_pct']:+.2f}% [{data['timestamp']}]")
            else:
                print(f"  ⚠️ {name}: 미국장 마감 or 데이터 없음")
            time.sleep(0.3)

        # 환율
        rate = self.get_exchange_rate()
        if rate:
            result['달러/원'] = rate
            print(f"  ✅ 달러/원: {rate['price']:,} [{rate['timestamp']}]")

        return result

if __name__ == "__main__":
    print("=" * 50)
    print("⚡ KIS API 실시간 테스트")
    print("=" * 50)
    kis  = KISApi()
    mode = "모의투자" if kis.is_mock else "실전투자"
    print(f"모드: {mode}\n")
    result = kis.get_all_realtime()
    print(f"\n✅ 총 {len(result)}개 실시간 데이터 수집 완료")
