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

class ClosingAnalyzer:
    def __init__(self):
        self.kis = KISApi()

    def get_today_movers(self):
        print("  📊 오늘 한국 장 결과 수집 중...")
        sector_results = {}
        for sector_name, sector_data in SECTOR_DB.items():
            if sector_data.get('market') != 'KR':
                continue
            sector_changes = {}
            for name, ticker in sector_data.get('대장주', {}).items():
                data = self.kis.get_kr_price(ticker)
                if data:
                    sector_changes[name] = {"ticker": ticker, "change": data['change_pct'], "price": data['price'], "volume": data['volume'], "tier": "대장주"}
                time.sleep(0.2)
            for name, ticker in sector_data.get('2등주', {}).items():
                data = self.kis.get_kr_price(ticker)
                if data:
                    sector_changes[name] = {"ticker": ticker, "change": data['change_pct'], "price": data['price'], "volume": data['volume'], "tier": "2등주"}
                time.sleep(0.2)
            for cat_name, cat_stocks in sector_data.get('소부장', {}).items():
                if not isinstance(cat_stocks, dict):
                    continue
                for name, ticker in cat_stocks.items():
                    if name in sector_changes:
                        continue
                    data = self.kis.get_kr_price(ticker)
                    if data:
                        sector_changes[name] = {"ticker": ticker, "change": data['change_pct'], "price": data['price'], "volume": data['volume'], "tier": f"소부장/{cat_name}"}
                    time.sleep(0.2)
            if sector_changes:
                changes = [v['change'] for v in sector_changes.values()]
                sector_results[sector_name] = {"stocks": sector_changes, "avg_change": round(sum(changes)/len(changes), 2), "max_change": round(max(changes), 2)}
        return sector_results

    def get_us_movers(self):
        import yfinance as yf
        print("  📊 오늘 미국 장 결과 수집 중...")
        sector_results = {}
        for sector_name, sector_data in SECTOR_DB.items():
            if sector_data.get('market') != 'US':
                continue
            sector_changes = {}
            for tier in ['대장주', '2등주']:
                for name, ticker in sector_data.get(tier, {}).items():
                    try:
                        hist = yf.Ticker(ticker).history(period="2d").dropna()
                        if len(hist) >= 2:
                            price = round(hist['Close'].iloc[-1], 2)
                            change_pct = round(((hist['Close'].iloc[-1] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2]) * 100, 2)
                            sector_changes[name] = {"ticker": ticker, "change": change_pct, "price": price, "volume": int(hist['Volume'].iloc[-1]), "tier": tier}
                    except:
                        pass
                    time.sleep(0.1)
            for cat_name, cat_stocks in sector_data.get('소부장', {}).items():
                if not isinstance(cat_stocks, dict):
                    continue
                for name, ticker in cat_stocks.items():
                    if name in sector_changes:
                        continue
                    try:
                        hist = yf.Ticker(ticker).history(period="2d").dropna()
                        if len(hist) >= 2:
                            price = round(hist['Close'].iloc[-1], 2)
                            change_pct = round(((hist['Close'].iloc[-1] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2]) * 100, 2)
                            sector_changes[name] = {"ticker": ticker, "change": change_pct, "price": price, "volume": int(hist['Volume'].iloc[-1]), "tier": f"소부장/{cat_name}"}
                    except:
                        pass
                    time.sleep(0.1)
            if sector_changes:
                changes = [v['change'] for v in sector_changes.values()]
                sector_results[sector_name] = {"stocks": sector_changes, "avg_change": round(sum(changes)/len(changes), 2), "max_change": round(max(changes), 2)}
        return sector_results

    def find_rotation_targets(self, sector_results):
        targets = []
        for sector_name, sector_data in sector_results.items():
            stocks   = sector_data['stocks']
            leaders  = [(n, s) for n, s in stocks.items() if s['tier'] == '대장주']
            seconds  = [(n, s) for n, s in stocks.items() if s['tier'] == '2등주']
            subsects = [(n, s) for n, s in stocks.items() if '소부장' in s['tier']]
            if not leaders:
                continue
            leader_avg = sum(s['change'] for _, s in leaders) / len(leaders)
            second_avg = sum(s['change'] for _, s in seconds) / len(seconds) if seconds else 0
            if leader_avg >= 5:
                for name, stock in seconds:
                    if stock['change'] < leader_avg * 0.5:
                        targets.append({"name": name, "ticker": stock['ticker'], "sector": sector_name, "tier": "2등주", "today_change": stock['change'], "leader_avg": leader_avg, "price": stock['price'], "reason": f"대장주 {leader_avg:+.1f}% 급등, 2등주 아직 {stock['change']:+.1f}%", "score": leader_avg - stock['change']})
            if leader_avg >= 8:
                for name, stock in subsects:
                    if stock['change'] < 3:
                        cat = stock['tier'].replace('소부장/', '')
                        targets.append({"name": name, "ticker": stock['ticker'], "sector": sector_name, "tier": f"소부장/{cat}", "today_change": stock['change'], "leader_avg": leader_avg, "price": stock['price'], "reason": f"대장주 {leader_avg:+.1f}% 급등, {cat} 소부장 아직 {stock['change']:+.1f}%", "score": leader_avg - stock['change']})
            if second_avg >= 5:
                for name, stock in subsects:
                    if stock['change'] < 2:
                        cat = stock['tier'].replace('소부장/', '')
                        targets.append({"name": name, "ticker": stock['ticker'], "sector": sector_name, "tier": f"소부장/{cat}", "today_change": stock['change'], "leader_avg": second_avg, "price": stock['price'], "reason": f"2등주 {second_avg:+.1f}% 급등, {cat} 소부장 아직 {stock['change']:+.1f}%", "score": second_avg - stock['change']})
        targets.sort(key=lambda x: x['score'], reverse=True)
        return targets[:10]

    async def _ai_recommend(self, hot_text, target_text, news_text, market="KR"):
        from anthropic import Anthropic
        import re
        client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        currency = "원" if market == "KR" else "달러"
        timing   = "오늘 마감 전 또는 내일 NXT 08:00" if market == "KR" else "오늘 밤 10:30 개장 후 지정가"
        prompt = f"""{'한국' if market=='KR' else '미국'} 주식시장 마감 결과 분석 후 내일 추천 종목을 선정해주세요.

=== 오늘 섹터 결과 ===
{hot_text}

=== 순환매 후보 ===
{target_text}

=== 오늘 주요 뉴스 ===
{news_text}

진입 가능 시간: {timing}

JSON으로만:
{{
  "today_summary": "오늘 장 한줄 요약",
  "tomorrow_outlook": "내일 전망 한줄",
  "hot_sectors_tomorrow": ["섹터1", "섹터2"],
  "recommendations": [
    {{
      "name": "종목명",
      "ticker": "티커",
      "sector": "섹터",
      "tier": "2등주 또는 소부장/카테고리",
      "reason": "추천 이유 한줄",
      "current_price": 실제현재가숫자,
      "buy_price": 실제매수가숫자,
      "buy_timing": "{timing}",
      "target1": 목표가1숫자,
      "target2": 목표가2숫자,
      "stop_loss": 손절가숫자,
      "expected_change": "+5~10%"
    }}
  ]
}}
반드시 실제 가격 숫자를 넣어주세요."""
        try:
            res  = client.messages.create(model="claude-sonnet-4-6", max_tokens=1500, messages=[{"role": "user", "content": prompt}])
            text = re.sub(r'```json|```', '', res.content[0].text.strip()).strip()
            m    = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                return json.loads(m.group())
        except Exception as e:
            print(f"  ❌ AI 분석 실패: {e}")
        return None

    async def ai_analyze_tomorrow(self, sector_results, targets, news_list):
        hot = sorted(sector_results.items(), key=lambda x: x[1]['avg_change'], reverse=True)[:5]
        hot_text    = "".join([f"{n}: 평균 {d['avg_change']:+.1f}% (최고 {d['max_change']:+.1f}%)\n" for n, d in hot])
        target_text = "".join([f"{t['name']}({t['ticker']}) {t['sector']}/{t['tier']}: 현재가:{t['price']:,}원 오늘{t['today_change']:+.1f}% | {t['reason']}\n" for t in targets[:8]])
        news_text   = "".join([f"{'🔴' if n.get('importance')=='high' else '🟡'} {n['title']}\n" for n in news_list[:10]])
        return await self._ai_recommend(hot_text, target_text, news_text, "KR")

    async def ai_analyze_us_tomorrow(self, sector_results, targets, news_list):
        hot = sorted(sector_results.items(), key=lambda x: x[1]['avg_change'], reverse=True)[:5]
        hot_text    = "".join([f"{n}: 평균 {d['avg_change']:+.1f}% (최고 {d['max_change']:+.1f}%)\n" for n, d in hot])
        target_text = "".join([f"{t['name']}({t['ticker']}) {t['sector']}/{t['tier']}: 현재가:${t['price']} 오늘{t['today_change']:+.1f}% | {t['reason']}\n" for t in targets[:8]])
        news_text   = "".join([f"{'🔴' if n.get('importance')=='high' else '🟡'} {n['title']}\n" for n in news_list[:10]])
        return await self._ai_recommend(hot_text, target_text, news_text, "US")

    def _build_msg(self, sector_results, result, market="KR"):
        if not result:
            return "❌ 분석 실패"
        hot      = sorted(sector_results.items(), key=lambda x: x[1]['avg_change'], reverse=True)
        currency = "원" if market == "KR" else "$"
        flag     = "🇰🇷" if market == "KR" else "🇺🇸"
        title    = "오늘 마감 + 내일 전략" if market == "KR" else "미국 마감 + 오늘 밤 전략"
        msg  = f"{flag} <b>{title}</b> {datetime.now().strftime('%m/%d %H:%M')}\n\n"
        msg += f"💡 {result.get('today_summary', '')}\n"
        msg += f"🔮 {result.get('tomorrow_outlook', '')}\n\n"
        msg += f"📈 <b>오늘 섹터 결과</b>\n"
        for name, data in hot[:6]:
            arrow = "▲" if data['avg_change'] > 0 else "▼"
            msg  += f"  {arrow} {name}: {data['avg_change']:+.1f}% (최고 {data['max_change']:+.1f}%)\n"
        hot_tmr = result.get('hot_sectors_tomorrow', [])
        if hot_tmr:
            msg += f"\n🔥 <b>내일 주목 섹터</b>: {' / '.join(hot_tmr)}\n"
        recs = result.get('recommendations', [])
        if recs:
            msg += "\n━━━━━━━━━━━━━━━━━━━\n"
            msg += "🎯 <b>선점 추천</b>\n"
            msg += "<i>(대장주 급등 → 파급 효과)</i>\n\n"
            for r in recs[:5]:
                tier_emoji = "🥈" if "2등주" in r.get('tier', '') else "🔩"
                cp = r.get('current_price', 0)
                bp = r.get('buy_price', 0)
                t1 = r.get('target1', 0)
                t2 = r.get('target2', 0)
                sl = r.get('stop_loss', 0)
                fmt = f"{cp:,}" if market == "KR" else f"{cp}"
                msg += f"{tier_emoji} <b>{r['name']}</b> ({r['ticker']})\n"
                msg += f"   {r['reason']}\n\n"
                msg += f"   💰 현재가: {fmt}{currency}\n" if market == "KR" else f"   💰 현재가: {currency}{fmt}\n"
                msg += f"   🟢 매수가: {currency}{bp:,}\n" if market == "KR" else f"   🟢 매수가: {currency}{bp}\n"
                msg += f"   ⏱ 진입:   {r.get('buy_timing', '')}\n"
                msg += f"   🎯 목표1:  {currency}{t1:,}\n" if market == "KR" else f"   🎯 목표1:  {currency}{t1}\n"
                msg += f"   🎯 목표2:  {currency}{t2:,}\n" if market == "KR" else f"   🎯 목표2:  {currency}{t2}\n"
                msg += f"   🛑 손절:   {currency}{sl:,}\n" if market == "KR" else f"   🛑 손절:   {currency}{sl}\n"
                msg += f"   📊 예상:   {r.get('expected_change', '')}\n"
                msg += "━━━━━━━━━━━━━━━━━━━\n"
        msg += f"\n⚠️ 최종 판단은 본인이 하세요.\n"
        msg += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return msg

    def build_message(self, sector_results, result):
        return self._build_msg(sector_results, result, "KR")

    def build_us_message(self, sector_results, result):
        return self._build_msg(sector_results, result, "US")


if __name__ == "__main__":
    async def test():
        print("=" * 50)
        print("📊 마감 분석 테스트 (한국 + 미국)")
        print("=" * 50)
        from modules.news_collector import NewsCollector
        ca       = ClosingAnalyzer()
        nc       = NewsCollector()
        news     = nc.collect_news(max_per_feed=3)
        filtered = nc.filter_by_importance(news)

        print("\n[한국]")
        kr_results = ca.get_today_movers()
        kr_targets = ca.find_rotation_targets(kr_results)
        print(f"순환매 후보: {len(kr_targets)}개")
        kr_result  = await ca.ai_analyze_tomorrow(kr_results, kr_targets, filtered)
        print(ca.build_message(kr_results, kr_result))

        print("\n[미국]")
        us_results = ca.get_us_movers()
        us_targets = ca.find_rotation_targets(us_results)
        print(f"순환매 후보: {len(us_targets)}개")
        us_result  = await ca.ai_analyze_us_tomorrow(us_results, us_targets, filtered)
        print(ca.build_us_message(us_results, us_result))

    asyncio.run(test())
