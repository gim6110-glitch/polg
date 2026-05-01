import os
import sys
import json
import time
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv('/media/dps/T7/stock_ai/.env')

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
        self.token_file = "/media/dps/T7/stock_ai/data/kis_token.json"
        self.timeout_sec = int(os.getenv("API_TIMEOUT_SEC", "10"))

    def _log(self, level, fn, msg):
        print(f"[KISApi][{fn}][{level}] {msg}")

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
            res  = requests.post(url, json=body, timeout=self.timeout_sec)
            data = res.json()
            if 'access_token' in data:
                self.token     = data['access_token']
                self.token_exp = datetime.now() + timedelta(hours=12)
                os.makedirs("/media/dps/T7/stock_ai/data", exist_ok=True)
                with open(self.token_file, 'w') as f:
                    json.dump({
                        'token':   self.token,
                        'expires': self.token_exp.isoformat()
                    }, f)
                self._log("INFO", "_get_token", "KIS 토큰 발급 완료")
                return self.token
            else:
                self._log("ERROR", "_get_token", f"토큰 발급 실패: {data}")
                return None
        except Exception as e:
            self._log("ERROR", "_get_token", f"토큰 요청 실패: {e}")
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
            res  = requests.get(url, headers=headers, params=params, timeout=self.timeout_sec)
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

    def get_top_fluctuation(self, market="J", count=50):
        """
        국내주식 등락률 상위 조회
        TR: FHPST01020000
        """
        try:
            headers, base = self._headers("FHPST01020000")
            url = f"{base}/uapi/domestic-stock/v1/ranking/fluctuation"
            params = {
                "FID_COND_MRKT_DIV_CODE": market,
                "FID_COND_SCR_DIV_CODE": "20170",
                "FID_INPUT_ISCD": "0000",
                "FID_DIV_CLS_CODE": "0",
                "FID_BLNG_CLS_CODE": "0",
                "FID_TRGT_CLS_CODE": "111111111",
                "FID_TRGT_EXLS_CLS_CODE": "0000000000",
                "FID_INPUT_PRICE_1": "",
                "FID_INPUT_PRICE_2": "",
                "FID_VOL_CNT": "100000",
                "FID_INPUT_DATE_1": "",
            }
            res = requests.get(url, headers=headers, params=params, timeout=self.timeout_sec)
            data = res.json()
            if data.get("rt_cd") != "0":
                print(f"❌ 등락률 상위 조회 실패: {data.get('msg1')}")
                return []

            rows = []
            for item in data.get("output", []):
                try:
                    rows.append({
                        "name": item.get("hts_kor_isnm", "").strip(),
                        "ticker": item.get("stck_shrn_iscd", "").strip(),
                        "price": int(item.get("stck_prpr", 0) or 0),
                        "change_pct": float(item.get("prdy_ctrt", 0) or 0),
                        "volume": int(item.get("acml_vol", 0) or 0),
                    })
                except Exception:
                    continue

            rows.sort(key=lambda x: x["change_pct"], reverse=True)
            return rows[:max(0, int(count))]
        except Exception as e:
            print(f"❌ 등락률 상위 조회 오류: {e}")
            return []



    def get_kr_stock_info(self, code):
        """한국 주식 종목명 + 업종 조회 (TR: CTPF1604R)"""
        try:
            headers, base = self._headers('CTPF1604R')
            url    = f'{base}/uapi/domestic-stock/v1/quotations/search-stock-info'
            params = {
                'PRDT_TYPE_CD': '300',
                'PDNO': code,
            }
            res  = requests.get(url, headers=headers, params=params, timeout=10)
            data = res.json()
            if data.get('rt_cd') == '0':
                output = data.get('output', {})
                name   = output.get('prdt_abrv_name', '') or output.get('prdt_name', '')
                sector = output.get('idx_bztp_scls_cd_name', '') or output.get('bstp_kor_isnm', '')
                return {'name': name, 'sector': sector}
        except Exception as e:
            print(f'❌ 종목 정보 조회 실패: {e}')
        return None

    def get_kr_stock_name(self, code):
        """하위 호환용 — get_kr_stock_info 래퍼"""
        info = self.get_kr_stock_info(code)
        return info['name'] if info else None

    def get_kr_ohlcv(self, code, days=60):
        """
        한국 주식 일봉 데이터 (KIS API)
        TR: FHKST01010400 — 국내주식 기간별시세
        반환: list of dict {date, open, high, low, close, volume}
        """
        try:
            headers, base = self._headers("FHKST01010400")
            url    = f"{base}/uapi/domestic-stock/v1/quotations/inquire-daily-price"
            end_dt   = datetime.now().strftime("%Y%m%d")
            start_dt = (datetime.now() - timedelta(days=days + 30)).strftime("%Y%m%d")
            params = {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD":         code,
                "FID_PERIOD_DIV_CODE":    "D",   # D=일봉
                "FID_ORG_ADJ_PRC":        "0",   # 수정주가
            }
            res  = requests.get(url, headers=headers, params=params, timeout=10)
            data = res.json()
            if data.get('rt_cd') != '0':
                print(f"❌ {code} 일봉 실패: {data.get('msg1')}")
                return None
            rows = []
            for item in data.get('output', []):
                try:
                    rows.append({
                        "date":   item['stck_bsop_date'],
                        "open":   int(item['stck_oprc']),
                        "high":   int(item['stck_hgpr']),
                        "low":    int(item['stck_lwpr']),
                        "close":  int(item['stck_clpr']),
                        "volume": int(item['acml_vol']),
                    })
                except Exception:
                    continue
            # 오래된 순 정렬
            rows.sort(key=lambda x: x['date'])
            return rows[-days:] if len(rows) >= days else rows
        except Exception as e:
            print(f"❌ {code} 일봉 조회 실패: {e}")
            return None

    def calc_indicators_kr(self, code, days=60):
        """
        KIS 일봉 기반 기술적 지표 계산
        반환: dict {rsi, ma5, ma20, ma60, vol_ratio, obv_trend, drawdown, high_52w, low_52w, macd, macd_signal, macd_hist, macd_cross}
        """
        rows = self.get_kr_ohlcv(code, days=max(days, 80))
        if not rows or len(rows) < 20:
            return {}
        try:
            import pandas as pd
            df         = pd.DataFrame(rows)
            close      = df['close'].astype(float)
            volume     = df['volume'].astype(float)
            current    = close.iloc[-1]

            ma5  = round(close.rolling(5).mean().iloc[-1], 0)
            ma20 = round(close.rolling(20).mean().iloc[-1], 0)
            ma60 = round(close.rolling(60).mean().iloc[-1], 0) if len(close) >= 60 else ma20

            # RSI
            delta = close.diff()
            gain  = delta.clip(lower=0).rolling(14).mean()
            loss  = (-delta.clip(upper=0)).rolling(14).mean()
            rs    = gain / (loss.replace(0, 0.0001))
            rsi   = round((100 - 100 / (1 + rs)).iloc[-1], 1)

            # 거래량 비율
            avg_vol   = volume.mean()
            curr_vol  = volume.iloc[-1]
            vol_ratio = round(curr_vol / avg_vol, 1) if avg_vol > 0 else 1

            # OBV
            obv       = (volume * close.diff().apply(lambda x: 1 if x > 0 else -1)).cumsum()
            obv_trend = "상승" if obv.iloc[-1] > obv.iloc[-5] else "하락"

            # MACD
            ema12 = close.ewm(span=12, adjust=False).mean()
            ema26 = close.ewm(span=26, adjust=False).mean()
            macd = ema12 - ema26
            signal = macd.ewm(span=9, adjust=False).mean()
            hist = macd - signal
            prev_macd = macd.iloc[-2] if len(macd) >= 2 else macd.iloc[-1]
            prev_signal = signal.iloc[-2] if len(signal) >= 2 else signal.iloc[-1]
            curr_macd = macd.iloc[-1]
            curr_signal = signal.iloc[-1]
            if prev_macd <= prev_signal and curr_macd > curr_signal:
                macd_cross = "golden"
            elif prev_macd >= prev_signal and curr_macd < curr_signal:
                macd_cross = "dead"
            else:
                macd_cross = "none"

            # 52주 고저
            high_52w = close.max()
            low_52w  = close.min()
            drawdown = round((current - high_52w) / high_52w * 100, 1)

            return {
                "rsi":       rsi,
                "ma5":       ma5,
                "ma20":      ma20,
                "ma60":      ma60,
                "vol_ratio": vol_ratio,
                "obv_trend": obv_trend,
                "drawdown":  drawdown,
                "high_52w":  round(high_52w, 0),
                "low_52w":   round(low_52w, 0),
                "macd":      round(curr_macd, 4),
                "macd_signal": round(curr_signal, 4),
                "macd_hist": round(hist.iloc[-1], 4),
                "macd_cross": macd_cross,
            }
        except Exception as e:
            print(f"❌ {code} 지표 계산 실패: {e}")
            return {}

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
