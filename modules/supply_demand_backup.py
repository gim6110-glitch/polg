import sys
import os
import json
import time
import asyncio
import requests
from datetime import datetime
from dotenv import load_dotenv
from telegram import Bot
sys.path.insert(0, "/home/dps/stock_ai")
from modules.safe_sender import safe_send

sys.path.insert(0, '/home/dps/stock_ai')
from modules.kis_api import KISApi

load_dotenv('/home/dps/stock_ai/.env')

try:
    import anthropic
    CLAUDE_AVAILABLE = True
except ImportError:
    CLAUDE_AVAILABLE = False

class SupplyDemand:
    """
    외국인/기관 수급 추적
    KIS API output은 리스트 형태
    output[0] = 당일 (장중 비어있음)
    output[1~] = 과거 거래일
    """
    def __init__(self):
        self.kis          = KISApi()
        self.history_file = "/home/dps/stock_ai/data/supply_history.json"

        self.telegram_token   = os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

        self.claude_client    = None
        self.claude_calls     = 0
        self.claude_max_calls = 5

        if CLAUDE_AVAILABLE:
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
            if api_key:
                self.claude_client = anthropic.Anthropic(api_key=api_key)
                print("✅ Claude API 연결됨")
            else:
                print("⚠️ ANTHROPIC_API_KEY 없음 → AI 판단 비활성")

    # ───────────────────────────────────────────────
    # 텔레그램 전송 (safe_sender 사용)
    # ───────────────────────────────────────────────
    async def send_telegram(self, msg):
        """텔레그램 메시지 전송 (safe_sender 자동 분할 + 재시도)"""
        try:
            bot = Bot(token=self.telegram_token)
            await safe_send(bot, self.telegram_chat_id, msg)
            print("✅ 텔레그램 전송 완료!")
        except Exception as e:
            print(f"❌ 텔레그램 전송 실패: {e}")

    # ───────────────────────────────────────────────
    # KIS API 수급 조회
    # ───────────────────────────────────────────────
    def get_investor_trend(self, code):
        """종목별 외국인/기관 수급 조회 (최근 5거래일)"""
        try:
            token   = self.kis._get_token()
            headers = {
                "Content-Type":  "application/json",
                "authorization": f"Bearer {token}",
                "appkey":        self.kis.app_key,
                "appsecret":     self.kis.app_secret,
                "tr_id":         "FHKST01010900",
            }
            url    = f"{self.kis.base_url}/uapi/domestic-stock/v1/quotations/inquire-investor"
            params = {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD":          code
            }
            res  = requests.get(url, headers=headers, params=params, timeout=10)
            data = res.json()

            if data.get('rt_cd') != '0':
                print(f"❌ {code} 수급 조회 실패: {data.get('msg1')}")
                return None

            output_list = data.get('output', [])
            if not output_list:
                return None

            daily_data = []
            for item in output_list[:6]:
                date    = item.get('stck_bsop_date', '')
                foreign = item.get('frgn_ntby_qty', '')
                organ   = item.get('orgn_ntby_qty', '')
                retail  = item.get('prsn_ntby_qty', '')

                if not foreign or not organ:
                    continue

                daily_data.append({
                    "date":    date,
                    "foreign": int(foreign),
                    "organ":   int(organ),
                    "retail":  int(retail) if retail else 0,
                    "close":   int(item.get('stck_clpr', 0)),
                })

            if not daily_data:
                return None

            return daily_data

        except Exception as e:
            print(f"❌ {code} 수급 조회 오류: {e}")
            return None

    # ───────────────────────────────────────────────
    # 규칙 기반 분석
    # ───────────────────────────────────────────────
    def analyze_supply(self, code, name):
        """수급 분석 + 연속 순매수 계산"""
        daily_data = self.get_investor_trend(code)
        if not daily_data:
            return None

        foreign_consecutive = 0
        organ_consecutive   = 0

        for d in daily_data:
            if d['foreign'] > 0:
                foreign_consecutive += 1
            else:
                break

        for d in daily_data:
            if d['organ'] > 0:
                organ_consecutive += 1
            else:
                break

        latest  = daily_data[0]
        signals = []
        score   = 0

        if foreign_consecutive >= 3:
            signals.append(f"🌍 외국인 {foreign_consecutive}일 연속 순매수 (강력)")
            score += 4
        elif foreign_consecutive >= 2:
            signals.append(f"🌍 외국인 {foreign_consecutive}일 연속 순매수")
            score += 3
        elif latest['foreign'] > 0:
            signals.append(f"🌍 외국인 순매수 ({latest['foreign']:,}주)")
            score += 1

        if organ_consecutive >= 3:
            signals.append(f"🏦 기관 {organ_consecutive}일 연속 순매수 (강력)")
            score += 4
        elif organ_consecutive >= 2:
            signals.append(f"🏦 기관 {organ_consecutive}일 연속 순매수")
            score += 3
        elif latest['organ'] > 0:
            signals.append(f"🏦 기관 순매수 ({latest['organ']:,}주)")
            score += 1

        if latest['foreign'] > 0 and latest['organ'] > 0:
            signals.append("💪 외국인 + 기관 동시 순매수")
            score += 2

        if latest['retail'] < 0 and (latest['foreign'] > 0 or latest['organ'] > 0):
            signals.append("📊 개인 순매도 + 세력 매집 패턴")
            score += 1

        if foreign_consecutive == 0 and latest['foreign'] < -1000000:
            signals.append(f"⚠️ 외국인 대량 순매도 ({latest['foreign']:,}주)")
            score -= 2

        trend_text = ""
        for d in daily_data[:5]:
            f_arrow  = "▲" if d['foreign'] > 0 else "▼"
            o_arrow  = "▲" if d['organ'] > 0 else "▼"
            date_fmt = f"{d['date'][4:6]}/{d['date'][6:]}"
            trend_text += f"  {date_fmt} 외국인:{f_arrow}{d['foreign']:,} 기관:{o_arrow}{d['organ']:,}\n"

        return {
            "code":                code,
            "name":                name,
            "foreign":             latest['foreign'],
            "organ":               latest['organ'],
            "retail":              latest['retail'],
            "foreign_consecutive": foreign_consecutive,
            "organ_consecutive":   organ_consecutive,
            "signals":             signals,
            "score":               score,
            "trend_text":          trend_text,
            "daily_data":          daily_data,
            "timestamp":           datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

    def scan_supply(self, stock_dict):
        """전체 종목 수급 스캔"""
        results = []
        for name, code in stock_dict.items():
            print(f"  수급 분석: {name}...")
            data = self.analyze_supply(code, name)
            if data:
                results.append(data)
            time.sleep(0.3)

        results.sort(key=lambda x: x['score'], reverse=True)
        return results

    # ───────────────────────────────────────────────
    # Claude AI 수급 판단 (간결 버전)
    # ───────────────────────────────────────────────
    def ai_analyze_supply(self, results):
        """규칙 기반 결과를 Claude로 해석 — 짧고 실용적으로"""
        if not self.claude_client:
            return None
        if self.claude_calls >= self.claude_max_calls:
            print("⚠️ Claude 호출 한도 초과 → AI 판단 스킵")
            return None
        if not results:
            return None

        strong = [r for r in results if r['score'] >= 2]
        if not strong:
            return None

        stocks_summary = ""
        for r in strong[:5]:
            stocks_summary += f"""
종목: {r['name']} ({r['code']})
- 외국인: {r['foreign']:,}주 ({r['foreign_consecutive']}일 연속)
- 기관: {r['organ']:,}주 ({r['organ_consecutive']}일 연속)
- 개인: {r['retail']:,}주
- 점수: {r['score']}점
- 최근 5일:
{r['trend_text']}"""

        prompt = f"""한국 주식 수급 데이터입니다. 아래 4가지를 각각 한 줄씩만 답하세요.
마크다운(###, **, --, ---)은 절대 사용하지 마세요. 줄바꿈과 이모지만 사용하세요.

{stocks_summary}

답변 형식 (각 항목 딱 한 줄):
1. 🎯 주목 TOP2: 종목명과 이유 한 줄
2. 💡 해석: 전체 수급 흐름 한 줄
3. ⚠️ 주의: 리스크 한 줄
4. 📌 힌트: 행동 제안 한 줄"""

        try:
            self.claude_calls += 1
            print(f"  🤖 Claude AI 분석 중... (호출 {self.claude_calls}/{self.claude_max_calls})")

            response = self.claude_client.messages.create(
                model      = "claude-sonnet-4-6",
                max_tokens = 300,
                messages   = [{"role": "user", "content": prompt}]
            )

            ai_text = response.content[0].text.strip()
            print("  ✅ AI 분석 완료")
            return ai_text

        except Exception as e:
            print(f"  ❌ Claude API 오류: {e}")
            return None

    # ───────────────────────────────────────────────
    # 알림 메시지 빌드
    # ───────────────────────────────────────────────
    def build_alert_message(self, results):
        """수급 알림 메시지 (AI 판단 포함)"""
        if not results:
            return None

        strong = [r for r in results if r['score'] >= 2]
        if not strong:
            return None

        msg = f"💰 <b>외국인/기관 수급 신호</b> {datetime.now().strftime('%m/%d %H:%M')}\n\n"

        for r in strong[:5]:
            stars        = "★" * min(r['score'], 5) + "☆" * (5 - min(r['score'], 5))
            signals_text = "\n".join([f"  {s}" for s in r['signals']])
            f_arrow      = "▲" if r['foreign'] > 0 else "▼"
            o_arrow      = "▲" if r['organ'] > 0 else "▼"

            msg += f"""━━━━━━━━━━━━━━━━━━━
📊 <b>{r['name']}</b> ({r['code']}) {stars}

🌍 외국인: {f_arrow}{r['foreign']:,}주 ({r['foreign_consecutive']}일 연속)
🏦 기관:   {o_arrow}{r['organ']:,}주 ({r['organ_consecutive']}일 연속)
👤 개인:   {r['retail']:,}주

📈 최근 5일 수급:
{r['trend_text']}
{signals_text}

"""

        ai_analysis = self.ai_analyze_supply(results)
        if ai_analysis:
            msg += f"━━━━━━━━━━━━━━━━━━━\n🤖 <b>AI 수급 판단</b>\n\n{ai_analysis}\n\n"
        else:
            msg += "━━━━━━━━━━━━━━━━━━━\n🤖 AI 판단: 비활성\n\n"

        msg += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return msg


if __name__ == "__main__":
    print("=" * 50)
    print("💰 외국인/기관 수급 테스트 (AI 판단 + 텔레그램)")
    print("=" * 50)

    sd = SupplyDemand()

    test_stocks = {
        "삼성전자":           "005930",
        "SK하이닉스":         "000660",
        "LG에너지솔루션":     "373220",
        "한화에어로스페이스":  "012450",
        "현대차":             "005380",
    }

    results = sd.scan_supply(test_stocks)

    if results:
        msg = sd.build_alert_message(results)
        if msg:
            print(msg)
            print("\n📱 텔레그램 전송 중...")
            asyncio.run(sd.send_telegram(msg))
        else:
            print("수급 신호 없음 (점수 2 미만)")
            for r in results:
                print(f"\n{r['name']}: 점수={r['score']}")
                print(f"  외국인 {r['foreign_consecutive']}일 연속: {r['foreign']:,}주")
                print(f"  기관   {r['organ_consecutive']}일 연속: {r['organ']:,}주")
                for s in r['signals']:
                    print(f"  {s}")
    else:
        print("❌ 데이터 없음")
