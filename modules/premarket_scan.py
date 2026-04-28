import sys
import os
import json
import time
import asyncio
from datetime import datetime
from dotenv import load_dotenv

sys.path.insert(0, '/media/dps/T7/stock_ai')
from modules.kis_api import KISApi
from modules.sector_db import SECTOR_DB

load_dotenv('/media/dps/T7/stock_ai/.env')

class PremarketScan:
    """
    매일 새벽 5시 상한가 후보 스캔
    당일 상한가 갈 가능성 높은 종목 사전 포착
    """
    def __init__(self):
        self.kis = KISApi()

    def _get_all_watchlist(self):
        """전체 감시 종목 수집"""
        watchlist = {}
        for sector_name, sector_data in SECTOR_DB.items():
            for tier in ['대장주', '2등주', '소부장']:
                watchlist.update(sector_data.get(tier, {}))
        return watchlist

    def _score_stock(self, name, ticker, market="KR"):
        """상한가 후보 점수 계산"""
        try:
            if market == "KR":
                data = self.kis.get_kr_price(ticker)
            else:
                data = None
                for excd in ["NAS", "NYS"]:
                    data = self.kis.get_us_price(ticker, excd)
                    if data and data.get('price', 0) > 0:
                        break

            if not data:
                return None

            import yfinance as yf
            yf_ticker = f"{ticker}.KS" if market == "KR" else ticker
            stock     = yf.Ticker(yf_ticker)
            hist      = stock.history(period="1mo")

            if hist.empty or len(hist) < 5:
                return None

            close     = hist['Close']
            volume    = hist['Volume']
            current   = data.get('price', close.iloc[-1])
            change    = data.get('change_pct', 0)
            avg_vol   = volume.mean()
            curr_vol  = volume.iloc[-1]
            vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1

            # 52주 고점 대비
            high_52w   = close.max()
            proximity  = (current / high_52w) * 100

            # 최근 5일 상승률
            week_change = ((close.iloc[-1] - close.iloc[-5]) / close.iloc[-5]) * 100

            # RSI
            delta    = close.diff()
            gain     = delta.clip(lower=0).rolling(14).mean()
            loss     = (-delta.clip(upper=0)).rolling(14).mean()
            rs       = gain / loss
            rsi      = (100 - (100 / (1 + rs))).iloc[-1]

            # 점수 계산
            score    = 0
            signals  = []

            # 거래량 급증
            if vol_ratio >= 3:
                score += 3
                signals.append(f"💥 거래량 {vol_ratio:.1f}배 폭발")
            elif vol_ratio >= 2:
                score += 2
                signals.append(f"📊 거래량 {vol_ratio:.1f}배 급증")

            # 52주 신고가 근접
            if proximity >= 99:
                score += 3
                signals.append(f"🏔 52주 신고가 도전 ({proximity:.1f}%)")
            elif proximity >= 97:
                score += 2
                signals.append(f"🏔 52주 신고가 근접 ({proximity:.1f}%)")

            # 최근 상승 추세
            if week_change >= 10:
                score += 2
                signals.append(f"🚀 5일 {week_change:+.1f}% 강세")
            elif week_change >= 5:
                score += 1
                signals.append(f"📈 5일 {week_change:+.1f}% 상승")

            # RSI 모멘텀
            if 60 <= rsi <= 75:
                score += 2
                signals.append(f"✅ RSI {rsi:.0f} 강세 구간")
            elif rsi > 75:
                score += 1
                signals.append(f"⚠️ RSI {rsi:.0f} 과열 주의")

            # 당일 상승 중
            if change >= 3:
                score += 2
                signals.append(f"▲ 당일 {change:+.1f}% 강세")
            elif change >= 1:
                score += 1
                signals.append(f"▲ 당일 {change:+.1f}%")

            return {
                "name":       name,
                "ticker":     ticker,
                "market":     market,
                "price":      current,
                "change":     change,
                "vol_ratio":  round(vol_ratio, 1),
                "rsi":        round(rsi, 1),
                "proximity":  round(proximity, 1),
                "week_change": round(week_change, 1),
                "score":      score,
                "signals":    signals,
            }
        except Exception as e:
            return None

    async def scan_top_candidates(self, news_list=None):
        """상한가 후보 TOP5 스캔"""
        print(f"[{datetime.now().strftime('%H:%M')}] 🌅 상한가 후보 스캔 시작")

        # AI로 오늘 핫 섹터 파악
        hot_sectors = []
        if news_list:
            try:
                from anthropic import Anthropic
                client    = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
                news_text = "\n".join([f"- {n['title']}" for n in news_list[:10]])
                res       = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=200,
                    messages=[{
                        "role": "user",
                        "content": f"""오늘 뉴스 기반으로 한국 주식 상한가 가능성 높은 섹터 3개만 골라주세요.
뉴스: {news_text}
JSON: {{"sectors": ["섹터1", "섹터2", "섹터3"]}}"""
                    }]
                )
                import re
                m = re.search(r'\{.*\}', res.content[0].text, re.DOTALL)
                if m:
                    hot_sectors = json.loads(m.group()).get("sectors", [])
                    print(f"  🔥 오늘 핫섹터: {hot_sectors}")
            except Exception as e:
                print(f"  ⚠️ AI 섹터 분석 실패: {e}")

        # 핫섹터 종목 우선 스캔
        candidates = []
        scanned    = set()

        # 핫섹터 종목 먼저
        for sector_name in hot_sectors:
            sector = SECTOR_DB.get(sector_name, {})
            if sector.get('market', 'KR') != 'KR':
                continue
            for tier in ['대장주', '2등주', '소부장']:
                for name, ticker in sector.get(tier, {}).items():
                    if ticker in scanned:
                        continue
                    scanned.add(ticker)
                    result = self._score_stock(name, ticker, "KR")
                    if result and result['score'] >= 4:
                        candidates.append(result)
                    time.sleep(0.2)

        # 전체 대장주 스캔
        if len(candidates) < 5:
            for sector_name, sector in SECTOR_DB.items():
                if sector.get('market', 'KR') != 'KR':
                    continue
                for name, ticker in sector.get('대장주', {}).items():
                    if ticker in scanned:
                        continue
                    scanned.add(ticker)
                    result = self._score_stock(name, ticker, "KR")
                    if result and result['score'] >= 3:
                        candidates.append(result)
                    time.sleep(0.2)

        # 점수순 정렬
        candidates.sort(key=lambda x: x['score'], reverse=True)
        top5 = candidates[:5]

        print(f"  ✅ 상한가 후보 {len(top5)}개 선정")
        return top5, hot_sectors

    def build_premarket_message(self, candidates, hot_sectors):
        """새벽 스캔 결과 메시지"""
        if not candidates:
            return "🌅 오늘 상한가 후보 없음 → 관망 추천"

        msg = f"""🌅 <b>오늘의 상한가 후보</b> {datetime.now().strftime('%m/%d')}

🔥 오늘 핫섹터: {' / '.join(hot_sectors) if hot_sectors else '분석중'}

━━━━━━━━━━━━━━━━━━━
"""
        for i, c in enumerate(candidates):
            stars    = "★" * min(c['score'], 5) + "☆" * (5 - min(c['score'], 5))
            signals  = "\n".join([f"  {s}" for s in c['signals']])
            currency = "$" if c['market'] == "US" else "₩"

            # 진입 전략
            if c['change'] >= 5:
                entry = "눌림목 대기 후 진입"
                tip   = "지금 추격 금지"
            elif c['proximity'] >= 97:
                entry = "신고가 돌파 확인 후 진입"
                tip   = "돌파 시 강한 매수"
            else:
                entry = "장 시작 후 10분 확인"
                tip   = "거래량 동반 확인 필수"

            msg += f"""🏆 {i+1}위. <b>{c['name']}</b> {stars}
💰 현재가: {currency}{c['price']:,}
📊 당일: {c['change']:+.1f}% | 5일: {c['week_change']:+.1f}%
📦 거래량: {c['vol_ratio']}배 | RSI: {c['rsi']}

{signals}

⏱ 전략: {entry}
💡 {tip}

"""
        msg += f"""━━━━━━━━━━━━━━━━━━━
⚠️ 장 시작 후 거래량 확인 필수
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"""
        return msg

if __name__ == "__main__":
    async def test():
        print("=" * 50)
        print("🌅 상한가 후보 스캔 테스트")
        print("=" * 50)
        from modules.news_collector import NewsCollector
        nc   = NewsCollector()
        news = nc.collect_news(max_per_feed=3)
        pm   = PremarketScan()
        candidates, hot_sectors = await pm.scan_top_candidates(news)
        msg = pm.build_premarket_message(candidates, hot_sectors)
        print(msg)

    asyncio.run(test())
