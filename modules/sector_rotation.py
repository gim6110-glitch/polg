import sys
import os
import json
import asyncio
import time
from datetime import datetime
from dotenv import load_dotenv

sys.path.insert(0, '/home/dps/stock_ai')
from modules.kis_api import KISApi
from modules.sector_db import SECTOR_DB, get_sector_list, get_all_tickers, get_subsector_tickers, get_sector_by_ticker

load_dotenv('/home/dps/stock_ai/.env')

class SectorRotation:
    def __init__(self):
        self.kis           = KISApi()
        self.rotation_file = "/home/dps/stock_ai/data/sector_rotation.json"

    def _is_market_open(self, market="KR"):
        """장 운영 시간 여부"""
        now  = datetime.now()
        hour = now.hour
        wday = now.weekday()
        if wday >= 5:  # 주말
            return False
        if market == "KR":
            return 8 <= hour < 18
        else:
            return hour >= 21 or hour < 6

    def _get_change_rate(self, ticker, market="KR"):
        """종목 등락률 조회 — 장 마감/주말 시 yfinance 전일 종가 기준"""
        # 장중이면 KIS 실시간
        if self._is_market_open(market):
            try:
                if market == "KR":
                    data = self.kis.get_kr_price(ticker)
                else:
                    data = None
                    for excd in ["NAS", "NYS"]:
                        data = self.kis.get_us_price(ticker, excd)
                        if data and data.get('price', 0) > 0:
                            break
                if data and data.get('change_pct', 0) != 0:
                    return data.get('change_pct', 0)
            except:
                pass

        # 장 마감 / 주말 → yfinance 전일 종가 기준 등락률
        try:
            import yfinance as yf
            yf_ticker = f"{ticker}.KS" if market == "KR" else ticker
            hist = yf.Ticker(yf_ticker).history(period="5d").dropna()
            if len(hist) >= 2:
                prev = hist['Close'].iloc[-2]
                last = hist['Close'].iloc[-1]
                return round((last - prev) / prev * 100, 2)
        except:
            pass
        return 0

    def analyze_sector_stage(self, sector_name):
        """섹터 순환매 단계 분석"""
        sector  = SECTOR_DB.get(sector_name, {})
        market  = sector.get('market', 'KR')
        results = {}

        for tier in ["대장주", "2등주", "소부장"]:
            stocks    = sector.get(tier, {})
            tier_data = []
            for name, ticker in stocks.items():
                change = self._get_change_rate(ticker, market)
                tier_data.append({
                    "name":   name,
                    "ticker": ticker,
                    "change": change
                })
                time.sleep(0.2)

            if tier_data:
                avg = sum(d['change'] for d in tier_data) / len(tier_data)
                mx  = max(d['change'] for d in tier_data)
                results[tier] = {
                    "stocks":     tier_data,
                    "avg_change": round(avg, 2),
                    "max_change": round(mx, 2),
                }

        return results, market

    def determine_target(self, sector_analysis):
        """순환매 타겟 결정"""
        대장 = sector_analysis.get("대장주", {})
        등2  = sector_analysis.get("2등주", {})
        소부 = sector_analysis.get("소부장", {})

        대장_avg = 대장.get("avg_change", 0)
        등2_avg  = 등2.get("avg_change", 0)
        소부_avg = 소부.get("avg_change", 0)

        if 대장_avg >= 8 and 등2_avg >= 5:
            target = "소부장"
            reason = f"대장주 {대장_avg:+.1f}% + 2등주 {등2_avg:+.1f}% 이미 급등 → 소부장 차례"
        elif 대장_avg >= 5:
            target = "2등주"
            reason = f"대장주 {대장_avg:+.1f}% 급등 → 2등주로 순환매 예상"
        elif 대장_avg >= 2:
            target = "대장주"
            reason = f"대장주 {대장_avg:+.1f}% 상승 중 → 추가 상승 여력 있음"
        else:
            target = "대장주"
            reason = "섹터 초입 → 대장주 선취매 기회"

        target_stocks = sector_analysis.get(target, {}).get("stocks", [])
        target_stocks.sort(key=lambda x: x['change'])

        return {
            "target":    target,
            "reason":    reason,
            "stocks":    target_stocks[:4],
            "대장_avg":  대장_avg,
            "2등주_avg": 등2_avg,
            "소부장_avg": 소부_avg,
        }

    async def analyze_hot_sectors(self, news_list, market="KR"):
        """AI로 핫섹터 분석"""
        news_text = ""
        for i, n in enumerate(news_list[:15]):
            news_text += f"{i+1}. [{n['source']}] {n['title']}\n"

        if market == "KR":
            sector_list = "AI반도체, 방산, 2차전지, 바이오, 조선, 원전, 로봇, 전기차, 게임, 엔터"
        else:
            sector_list = "미국AI, 미국빅테크, 미국원전, 미국우주, 미국바이오, 미국에너지, 미국방산, 미국금융, 미국소비, 미국전기차"

        from anthropic import Anthropic
        import os
        client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

        prompt = f"""오늘 뉴스를 분석해서 {"한국" if market=="KR" else "미국"} 주식시장 핫섹터를 파악해주세요.

=== 뉴스 ===
{news_text}

선택 가능한 섹터:
{sector_list}

JSON으로만 답변:
{{
  "hot_sectors": ["섹터1", "섹터2"],
  "reason": "선정 이유 한줄",
  "next_sectors": ["다음에 올 섹터"]
}}"""

        try:
            res  = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )
            text = res.content[0].text.strip()
            import re, json
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                return json.loads(m.group())
        except Exception as e:
            print(f"❌ 핫섹터 분석 실패: {e}")

        default = {
            "KR": {"hot_sectors": ["AI반도체", "방산"], "reason": "기본값", "next_sectors": ["원전"]},
            "US": {"hot_sectors": ["미국AI", "미국원전"], "reason": "기본값", "next_sectors": ["미국방산"]}
        }
        return default.get(market, default["KR"])

    async def get_today_targets(self, news_list, market="KR"):
        """오늘 순환매 타겟 분석"""
        print(f"🔄 {market} 순환매 분석 시작...")
        hot_info    = await self.analyze_hot_sectors(news_list, market)
        hot_sectors = hot_info.get("hot_sectors", [])
        results     = {}

        for sector_name in hot_sectors:
            if sector_name not in SECTOR_DB:
                continue
            if SECTOR_DB[sector_name]['market'] != market:
                continue
            print(f"  📊 {sector_name} 분석 중...")
            analysis, mkt = self.analyze_sector_stage(sector_name)
            rotation      = self.determine_target(analysis)
            results[sector_name] = {
                "analysis": analysis,
                "rotation": rotation,
                "market":   mkt,
            }

        # 저장
        os.makedirs("/home/dps/stock_ai/data", exist_ok=True)
        save_key = f"rotation_{market}"
        existing = {}
        if os.path.exists(self.rotation_file):
            with open(self.rotation_file, "r", encoding="utf-8") as f:
                existing = json.load(f)

        existing[save_key] = {
            "date":         datetime.now().strftime("%Y-%m-%d"),
            "hot_sectors":  hot_sectors,
            "next_sectors": hot_info.get("next_sectors", []),
            "hot_reason":   hot_info.get("reason", ""),
            "results":      {k: v['rotation'] for k, v in results.items()},
            "updated":      datetime.now().isoformat()
        }
        with open(self.rotation_file, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

        return hot_info, results

    def build_alert_message(self, hot_info, results, market="KR"):
        """순환매 알림 메시지"""
        flag         = "🇰🇷" if market == "KR" else "🇺🇸"
        hot_sectors  = hot_info.get("hot_sectors", [])
        next_sectors = hot_info.get("next_sectors", [])
        reason       = hot_info.get("reason", "")
        market_open  = self._is_market_open(market)
        price_label  = "실시간" if market_open else "전일 종가 기준"

        msg = f"""{flag} <b>{"한국" if market=="KR" else "미국"} 순환매 전략</b> {datetime.now().strftime('%m/%d')}
📊 <i>({price_label})</i>
🔥 <b>오늘 핫섹터:</b> {' / '.join(hot_sectors)}
📋 {reason}

"""
        for sector_name, data in results.items():
            rotation   = data['rotation']
            target     = rotation['target']
            stocks     = rotation['stocks'][:3]
            tier_emoji = {"대장주": "👑", "2등주": "🥈", "소부장": "🔩"}.get(target, "📊")

            msg += f"""━━━━━━━━━━━━━━━━━━━
{tier_emoji} <b>{sector_name} → {target} 공략</b>
💡 {rotation['reason']}

대장주: {rotation['대장_avg']:+.1f}% | 2등주: {rotation['2등주_avg']:+.1f}% | 소부장: {rotation['소부장_avg']:+.1f}%

🎯 주목 종목:
"""
            for s in stocks:
                arrow = "▲" if s['change'] > 0 else "▼"
                msg  += f"  • {s['name']} ({s['ticker']}): {arrow}{s['change']:+.1f}%\n"

        if next_sectors:
            msg += f"""
━━━━━━━━━━━━━━━━━━━
🔮 <b>다음에 올 섹터:</b> {' / '.join(next_sectors)}
→ 미리 관심 종목 등록 추천
"""
        msg += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return msg

    def get_watchlist_for_realtime(self, market="KR"):
        """실시간 감시 종목 반환"""
        if not os.path.exists(self.rotation_file):
            return {}
        with open(self.rotation_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        save_key = f"rotation_{market}"
        rot_data = data.get(save_key, {})

        if rot_data.get("date") != datetime.now().strftime("%Y-%m-%d"):
            return {}

        watchlist = {}
        for sector_name, rotation in rot_data.get("results", {}).items():
            if sector_name not in SECTOR_DB:
                continue
            target = rotation.get("target", "대장주")
            stocks = SECTOR_DB[sector_name].get(target, {})
            watchlist.update(stocks)

        return watchlist

if __name__ == "__main__":
    import asyncio
    from modules.news_collector import NewsCollector

    async def test():
        print("=" * 50)
        print("🔄 섹터 순환매 테스트 (한국)")
        print("=" * 50)
        nc       = NewsCollector()
        news     = nc.collect_news(max_per_feed=3)
        sr       = SectorRotation()
        hot_info, results = await sr.get_today_targets(news, market="KR")
        msg = sr.build_alert_message(hot_info, results, market="KR")
        print(msg)

        print("\n" + "=" * 50)
        print("🔄 섹터 순환매 테스트 (미국)")
        print("=" * 50)
        hot_info_us, results_us = await sr.get_today_targets(news, market="US")
        msg_us = sr.build_alert_message(hot_info_us, results_us, market="US")
        print(msg_us)

    asyncio.run(test())
