import sys
import os
import json
import time
import requests
import asyncio
import yfinance as yf
from datetime import datetime
from dotenv import load_dotenv

sys.path.insert(0, '/media/dps/T7/stock_ai')
from modules.kis_api import KISApi
from modules.sector_db import SECTOR_DB

load_dotenv('/media/dps/T7/stock_ai/.env')

class PremarketFutures:
    """
    선물 + NXT 분석 기반 정규장 예측

    [한국]
    ① 밤새 미국 선물 방향 파악
    ② 한국 선물(코스피200) 방향 파악
    ③ 08:00 NXT에서 오른 종목/섹터 파악
    ④ NXT에서 안 올랐지만 연관 종목 추천
    → 09:00 정규장 진입 준비

    [미국]
    ① 한국장 마감 후 미국 선물 방향
    ② 프리마켓 강세 섹터 파악
    ③ 프리마켓 안 올랐지만 연관 종목 추천
    → 22:30 정규장 진입 준비
    """
    def __init__(self):
        self.kis = KISApi()

    def get_us_futures(self):
        """미국 선물 현황 (밤새 방향)"""
        futures = {
            "나스닥선물":  "NQ=F",
            "S&P500선물": "ES=F",
            "다우선물":    "YM=F",
            "VIX":         "^VIX",
        }
        results = {}
        for name, ticker in futures.items():
            try:
                data = yf.Ticker(ticker)
                hist = data.history(period="2d").dropna()
                if len(hist) >= 2:
                    current    = hist['Close'].iloc[-1]
                    prev       = hist['Close'].iloc[-2]
                    change_pct = ((current - prev) / prev) * 100
                    results[name] = {
                        "price":      round(current, 2),
                        "change_pct": round(change_pct, 2)
                    }
            except:
                pass
            time.sleep(0.2)
        return results

    def get_kr_futures(self):
        """한국 코스피200 선물 방향"""
        try:
            # yfinance로 코스피200 선물
            data = yf.Ticker("^KS200")
            hist = data.history(period="2d").dropna()
            if len(hist) >= 2:
                current    = hist['Close'].iloc[-1]
                prev       = hist['Close'].iloc[-2]
                change_pct = ((current - prev) / prev) * 100
                return {
                    "코스피200": {
                        "price":      round(current, 2),
                        "change_pct": round(change_pct, 2)
                    }
                }
        except:
            pass
        return {}

    def get_nxt_prices(self, code):
        """
        NXT 시세 조회
        실제 주식을 정규장 전에 거래하는 시장
        08:00~08:50 프리마켓
        """
        try:
            token   = self.kis._get_token()
            headers = {
                "Content-Type":  "application/json",
                "authorization": f"Bearer {token}",
                "appkey":        self.kis.app_key,
                "appsecret":     self.kis.app_secret,
                "tr_id":         "FHPOW02100000",  # NXT 현재가
            }
            url    = f"{self.kis.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
            params = {
                "FID_COND_MRKT_DIV_CODE": "NX",  # NXT 시장
                "FID_INPUT_ISCD": code
            }
            res  = requests.get(url, headers=headers, params=params, timeout=10)
            data = res.json()
            if data.get('rt_cd') == '0':
                output = data.get('output', {})
                price  = float(output.get('stck_prpr', 0))
                change = float(output.get('prdy_ctrt', 0))
                volume = int(output.get('acml_vol', 0))
                if price > 0:
                    return {
                        "price":      price,
                        "change_pct": change,
                        "volume":     volume
                    }
        except Exception as e:
            pass

        # NXT 안 되면 일반 현재가로 폴백
        data = self.kis.get_kr_price(code)
        if data:
            return {
                "price":      data['price'],
                "change_pct": data['change_pct'],
                "volume":     data['volume']
            }
        return None

    def get_nxt_sector_status(self):
        """
        NXT 섹터별 등락 분석
        어떤 섹터가 이미 올랐는지 파악
        """
        sector_status = {}

        for sector_name, sector_data in SECTOR_DB.items():
            if sector_data.get('market', 'KR') != 'KR':
                continue

            leaders     = sector_data.get('대장주', {})
            leader_data = []

            for name, ticker in leaders.items():
                # NXT 시간(08:00~08:50)이면 NXT 시세, 아니면 일반 시세
                from datetime import datetime as _dt
                hour   = _dt.now().hour
                minute = _dt.now().minute
                is_nxt = (hour == 8 and 0 <= minute <= 50)

                if is_nxt:
                    data = self.get_nxt_prices(ticker)
                else:
                    # 일반 KIS 시세로 폴백
                    from modules.kis_api import KISApi as _KIS
                    _kis = _KIS()
                    raw  = _kis.get_kr_price(ticker)
                    data = {"price": raw["price"], "change_pct": raw["change_pct"], "volume": raw["volume"]} if raw else None

                if data and data.get("price", 0) > 0:
                    leader_data.append({
                        "name":   name,
                        "ticker": ticker,
                        "change": data["change_pct"],
                        "volume": data["volume"],
                        "price":  data["price"]
                    })
                time.sleep(0.3)

            if not leader_data:
                continue

            avg_change = sum(d['change'] for d in leader_data) / len(leader_data)
            sector_status[sector_name] = {
                "avg_change":  round(avg_change, 2),
                "leaders":     leader_data,
                "description": sector_data.get('description', '')
            }

        return sector_status

    def get_us_premarket_status(self):
        """미국 프리마켓 섹터 분석"""
        sector_status = {}

        for sector_name, sector_data in SECTOR_DB.items():
            if sector_data.get('market', 'KR') != 'US':
                continue

            leaders     = sector_data.get('대장주', {})
            leader_data = []

            for name, ticker in leaders.items():
                for excd in ["NAS", "NYS"]:
                    data = self.kis.get_us_price(ticker, excd)
                    if data and data.get('price', 0) > 0:
                        leader_data.append({
                            "name":   name,
                            "ticker": ticker,
                            "change": data['change_pct'],
                            "price":  data['price']
                        })
                        break
                time.sleep(0.2)

            if not leader_data:
                continue

            avg_change = sum(d['change'] for d in leader_data) / len(leader_data)
            sector_status[sector_name] = {
                "avg_change": round(avg_change, 2),
                "leaders":    leader_data,
            }

        return sector_status

    async def _ai_find_undervalued(self, hot_sectors, neutral_sectors, market):
        """
        AI가 핵심 분석
        이미 오른 섹터 파악
        → 아직 안 올랐지만 파급 효과로 오를 종목 추천
        """
        if not hot_sectors:
            return [], ""

        hot_detail = ""
        for name, data in hot_sectors[:3]:
            leaders = " / ".join([
                f"{l['name']} {l['change']:+.1f}%"
                for l in data['leaders'][:2]
            ])
            hot_detail += f"- {name}: 평균 {data['avg_change']:+.1f}% ({leaders})\n"

        neutral_names = [name for name, _ in neutral_sectors[:5]]

        from anthropic import Anthropic
        client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

        prompt = f"""주식 전문가로서 분석해주세요.

{"한국" if market=="KR" else "미국"} {"NXT(정규장 전 거래)" if market=="KR" else "프리마켓"}에서:

🔥 이미 많이 오른 섹터:
{hot_detail}

⬜ 아직 안 오른 섹터: {', '.join(neutral_names)}

분석 요청:
1. 이미 오른 섹터의 파급 효과로 정규장에서 오를 섹터는?
2. 아직 안 올랐지만 연관되어 오를 가능성 높은 종목 5개
   - 대장주보다 2등주/소부장 위주
   - NXT/프리마켓에서 아직 안 오른 것
   - 실제 존재하는 종목만

JSON으로만 답변:
{{
  "analysis": "파급 효과 분석 두줄",
  "target_sectors": ["오를 섹터1", "오를 섹터2"],
  "recommendations": [
    {{
      "sector": "섹터명",
      "name": "종목명",
      "ticker": "티커",
      "reason": "추천 이유 한줄",
      "expected_change": "+5~10%",
      "entry_timing": "진입 타이밍"
    }}
  ]
}}"""

        try:
            res = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=700,
                messages=[{"role": "user", "content": prompt}]
            )
            text = res.content[0].text.strip()
            import re
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                data     = json.loads(m.group())
                recs     = data.get('recommendations', [])
                analysis = data.get('analysis', '')
                return recs, analysis
        except Exception as e:
            print(f"  ❌ AI 분석 실패: {e}")
        return [], ""

    async def analyze_kr_nxt(self):
        """한국 NXT 분석 → 정규장 추천"""
        print(f"[{datetime.now().strftime('%H:%M')}] 🌅 NXT + 선물 분석 시작")

        # 미국 선물 방향 (밤새)
        us_futures = self.get_us_futures()
        kr_futures = self.get_kr_futures()

        nas_future = us_futures.get('나스닥선물', {}).get('change_pct', 0)
        sp_future  = us_futures.get('S&P500선물', {}).get('change_pct', 0)
        vix        = us_futures.get('VIX', {}).get('price', 20)

        # 선물 방향 판단
        if nas_future >= 0.5 and sp_future >= 0.3:
            direction       = "강세"
            direction_emoji = "🚀"
            direction_desc  = "미국 선물 강세 → 한국장 갭상승 예상"
        elif nas_future <= -0.5 and sp_future <= -0.3:
            direction       = "약세"
            direction_emoji = "📉"
            direction_desc  = "미국 선물 약세 → 한국장 갭하락 주의"
        else:
            direction       = "중립"
            direction_emoji = "➡️"
            direction_desc  = "선물 중립 → 종목별 차별화 장세"

        # NXT 섹터 분석
        print("  📊 NXT 섹터 분석 중...")
        sector_status = self.get_nxt_sector_status()

        # 이미 오른 섹터 vs 안 오른 섹터
        hot_sectors     = []
        neutral_sectors = []
        down_sectors    = []

        for name, data in sector_status.items():
            avg = data['avg_change']
            if avg >= 2:
                hot_sectors.append((name, data))
            elif avg >= -1:
                neutral_sectors.append((name, data))
            else:
                down_sectors.append((name, data))

        hot_sectors.sort(key=lambda x: x[1]['avg_change'], reverse=True)
        neutral_sectors.sort(key=lambda x: x[1]['avg_change'], reverse=True)

        # AI 파급 분석
        print("  🧠 AI 파급 효과 분석 중...")
        recommendations, ai_analysis = await self._ai_find_undervalued(
            hot_sectors, neutral_sectors, "KR"
        )

        return {
            "direction":       direction,
            "direction_emoji": direction_emoji,
            "direction_desc":  direction_desc,
            "nas_future":      nas_future,
            "sp_future":       sp_future,
            "vix":             vix,
            "kr_futures":      kr_futures,
            "hot_sectors":     hot_sectors,
            "neutral_sectors": neutral_sectors,
            "down_sectors":    down_sectors,
            "recommendations": recommendations,
            "ai_analysis":     ai_analysis,
        }

    async def analyze_us_premarket(self):
        """미국 프리마켓 분석 → 정규장 추천"""
        print(f"[{datetime.now().strftime('%H:%M')}] 🌙 미국 프리마켓 분석")

        us_futures = self.get_us_futures()
        nas_future = us_futures.get('나스닥선물', {}).get('change_pct', 0)
        sp_future  = us_futures.get('S&P500선물', {}).get('change_pct', 0)
        vix        = us_futures.get('VIX', {}).get('price', 20)

        if nas_future >= 0.5:
            direction       = "강세"
            direction_emoji = "🚀"
            direction_desc  = "선물 강세 → 미국장 상승 출발 예상"
        elif nas_future <= -0.5:
            direction       = "약세"
            direction_emoji = "📉"
            direction_desc  = "선물 약세 → 미국장 하락 출발 주의"
        else:
            direction       = "중립"
            direction_emoji = "➡️"
            direction_desc  = "선물 중립 → 종목 차별화"

        print("  📊 프리마켓 섹터 분석 중...")
        sector_status = self.get_us_premarket_status()

        hot_sectors     = []
        neutral_sectors = []

        for name, data in sector_status.items():
            avg = data['avg_change']
            if avg >= 2:
                hot_sectors.append((name, data))
            elif avg >= -1:
                neutral_sectors.append((name, data))

        hot_sectors.sort(key=lambda x: x[1]['avg_change'], reverse=True)
        neutral_sectors.sort(key=lambda x: x[1]['avg_change'], reverse=True)

        print("  🧠 AI 파급 분석 중...")
        recommendations, ai_analysis = await self._ai_find_undervalued(
            hot_sectors, neutral_sectors, "US"
        )

        return {
            "direction":       direction,
            "direction_emoji": direction_emoji,
            "direction_desc":  direction_desc,
            "nas_future":      nas_future,
            "sp_future":       sp_future,
            "vix":             vix,
            "hot_sectors":     hot_sectors,
            "neutral_sectors": neutral_sectors,
            "recommendations": recommendations,
            "ai_analysis":     ai_analysis,
        }

    def build_kr_message(self, d):
        """한국 NXT 분석 메시지"""
        em  = d['direction_emoji']
        msg = f"""🌅 <b>NXT + 선물 분석</b> {datetime.now().strftime('%m/%d %H:%M')}

{em} <b>오늘 시장 방향: {d['direction']}</b>
💡 {d['direction_desc']}

📊 <b>미국 선물 (밤새 방향)</b>
  나스닥: {d['nas_future']:+.2f}%
  S&P500: {d['sp_future']:+.2f}%
  VIX: {d['vix']:.1f} {'(공포 주의)' if d['vix'] > 25 else '(안정)'}
"""
        if d['kr_futures']:
            msg += "\n📊 <b>한국 선물</b>\n"
            for name, data in d['kr_futures'].items():
                arrow = "▲" if data['change_pct'] > 0 else "▼"
                msg  += f"  {name}: {arrow}{data['change_pct']:+.2f}%\n"

        msg += "\n━━━━━━━━━━━━━━━━━━━\n"

        if d['hot_sectors']:
            msg += "🔥 <b>NXT에서 이미 오른 섹터</b>\n"
            for name, data in d['hot_sectors'][:4]:
                leaders = " / ".join([
                    f"{l['name']} {l['change']:+.1f}%"
                    for l in data['leaders'][:2]
                ])
                msg += f"  🔴 {name}: +{data['avg_change']:.1f}% ({leaders})\n"

        if d['neutral_sectors']:
            msg += "\n⬜ <b>NXT에서 아직 안 오른 섹터</b>\n"
            for name, data in d['neutral_sectors'][:4]:
                msg += f"  ⚪ {name}: {data['avg_change']:+.1f}%\n"

        if d['ai_analysis']:
            msg += f"\n🧠 <b>AI 파급 분석</b>\n{d['ai_analysis']}\n"

        if d['recommendations']:
            msg += "\n━━━━━━━━━━━━━━━━━━━\n"
            msg += "🎯 <b>정규장 선점 추천</b>\n"
            msg += "<i>NXT에서 안 올랐지만 파급 효과로 오를 종목</i>\n\n"
            for r in d['recommendations'][:5]:
                msg += f"⭐ <b>{r['name']}</b> ({r['ticker']})\n"
                msg += f"   섹터: {r['sector']}\n"
                msg += f"   이유: {r['reason']}\n"
                msg += f"   예상: {r.get('expected_change', '')} | {r.get('entry_timing', '')}\n\n"

        msg += f"""━━━━━━━━━━━━━━━━━━━
⚠️ 09:00 장 시작 후 거래량 반드시 확인
⚠️ 선물/NXT 방향은 정규장과 다를 수 있음
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"""
        return msg

    def build_us_message(self, d):
        """미국 프리마켓 분석 메시지"""
        em  = d['direction_emoji']
        msg = f"""🌙 <b>미국 프리마켓 분석</b> {datetime.now().strftime('%m/%d %H:%M')}

{em} <b>오늘 미국장 방향: {d['direction']}</b>
💡 {d['direction_desc']}

📊 <b>선물 현황</b>
  나스닥: {d['nas_future']:+.2f}%
  S&P500: {d['sp_future']:+.2f}%
  VIX: {d['vix']:.1f}

━━━━━━━━━━━━━━━━━━━
"""
        if d['hot_sectors']:
            msg += "🔥 <b>프리마켓 강세 섹터</b>\n"
            for name, data in d['hot_sectors'][:4]:
                leaders = " / ".join([
                    f"{l['name']} {l['change']:+.1f}%"
                    for l in data['leaders'][:2]
                ])
                msg += f"  🔴 {name}: +{data['avg_change']:.1f}% ({leaders})\n"

        if d['neutral_sectors']:
            msg += "\n⬜ <b>아직 안 오른 섹터</b>\n"
            for name, data in d['neutral_sectors'][:4]:
                msg += f"  ⚪ {name}: {data['avg_change']:+.1f}%\n"

        if d['ai_analysis']:
            msg += f"\n🧠 <b>AI 파급 분석</b>\n{d['ai_analysis']}\n"

        if d['recommendations']:
            msg += "\n━━━━━━━━━━━━━━━━━━━\n"
            msg += "🎯 <b>미국장 선점 추천</b>\n\n"
            for r in d['recommendations'][:5]:
                msg += f"⭐ <b>{r['name']}</b> ({r['ticker']})\n"
                msg += f"   이유: {r['reason']}\n"
                msg += f"   예상: {r.get('expected_change', '')} | {r.get('entry_timing', '')}\n\n"

        msg += f"""━━━━━━━━━━━━━━━━━━━
⚠️ 22:30 개장 후 거래량 확인 필수
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"""
        return msg

if __name__ == "__main__":
    async def test():
        print("=" * 50)
        print("🌅 NXT + 선물 분석 테스트")
        print("=" * 50)
        pf = PremarketFutures()

        print("\n[한국 NXT 분석]")
        kr = await pf.analyze_kr_nxt()
        print(pf.build_kr_message(kr))

    asyncio.run(test())
