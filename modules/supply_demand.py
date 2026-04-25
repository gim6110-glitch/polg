import sys
import os
import time
import asyncio
import requests
from datetime import datetime
from dotenv import load_dotenv
from telegram import Bot

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
        self.kis              = KISApi()
        self.history_file     = "/home/dps/stock_ai/data/supply_history.json"
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
    # 텔레그램 단일 메시지 전송
    # ───────────────────────────────────────────────
    async def _send_one(self, bot, text):
        """단일 메시지 전송 (재시도 3회)"""
        for attempt in range(3):
            try:
                await bot.send_message(
                    chat_id    = self.telegram_chat_id,
                    text       = text,
                    parse_mode = "HTML"
                )
                await asyncio.sleep(0.5)
                return True
            except Exception as e:
                print(f"  ⚠️ 전송 실패 {attempt+1}/3: {e}")
                if attempt < 2:
                    await asyncio.sleep(3)
        return False

    async def send_telegram(self, messages):
        """
        메시지 리스트를 순서대로 전송.
        문자열 하나 또는 리스트 모두 받을 수 있음.
        """
        if isinstance(messages, str):
            messages = [messages]
        try:
            bot = Bot(token=self.telegram_token)
            for msg in messages:
                if msg and msg.strip():
                    await self._send_one(bot, msg)
            print(f"✅ 텔레그램 전송 완료! ({len(messages)}개 메시지)")
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
    # Claude AI 수급 판단
    # ───────────────────────────────────────────────
    def ai_analyze_supply(self, results):
        """규칙 기반 결과를 Claude로 해석"""
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
- 점수: {r['score']}점"""

        prompt = f"""한국 주식 수급 데이터입니다.
{stocks_summary}

반드시 아래 4줄만 출력하세요. 각 줄은 30자 이내로 끝내세요.
마크다운 금지. 이모지만 사용.

🎯 TOP2: [종목명2개, 이유]
💡 해석: [흐름한줄]
⚠️ 주의: [리스크한줄]
📌 힌트: [행동한줄]"""

        try:
            self.claude_calls += 1
            print(f"  🤖 Claude AI 분석 중... (호출 {self.claude_calls}/{self.claude_max_calls})")

            response = self.claude_client.messages.create(
                model      = "claude-sonnet-4-6",
                max_tokens = 200,
                messages   = [{"role": "user", "content": prompt}]
            )

            ai_text = response.content[0].text.strip()
            print("  ✅ AI 분석 완료")
            return ai_text

        except Exception as e:
            print(f"  ❌ Claude API 오류: {e}")
            return None

    # ───────────────────────────────────────────────
    # 메시지 빌드 — 종목별 + AI판단 각각 별도 메시지
    # ───────────────────────────────────────────────
    def build_alert_messages(self, results):
        """
        메시지를 리스트로 반환.
        1번째: 헤더
        2~N번째: 종목별 수급 (각각 별도 메시지)
        마지막: AI 판단
        """
        if not results:
            return None

        strong = [r for r in results if r['score'] >= 2]
        if not strong:
            return None

        messages = []
        now = datetime.now().strftime('%m/%d %H:%M')

        # 1. 헤더 메시지
        messages.append(f"💰 <b>외국인/기관 수급 신호</b> {now}\n총 {len(strong)}개 종목 신호 감지")

        # 2. 종목별 메시지 (각각 분리)
        for r in strong[:5]:
            stars        = "★" * min(r['score'], 5) + "☆" * (5 - min(r['score'], 5))
            signals_text = "\n".join([f"  {s}" for s in r['signals']])
            f_arrow      = "▲" if r['foreign'] > 0 else "▼"
            o_arrow      = "▲" if r['organ'] > 0 else "▼"

            msg = f"""📊 <b>{r['name']}</b> ({r['code']}) {stars}

🌍 외국인: {f_arrow}{r['foreign']:,}주 ({r['foreign_consecutive']}일 연속)
🏦 기관:   {o_arrow}{r['organ']:,}주 ({r['organ_consecutive']}일 연속)
👤 개인:   {r['retail']:,}주

📈 최근 5일:
{r['trend_text']}
{signals_text}"""

            messages.append(msg)

        # 3. AI 판단 메시지
        ai_analysis = self.ai_analyze_supply(results)
        if ai_analysis:
            messages.append(f"🤖 <b>AI 수급 판단</b>\n\n{ai_analysis}")
        else:
            messages.append("🤖 AI 판단: 비활성")

        return messages

    # 하위 호환성 유지 (기존 main.py에서 build_alert_message 호출 시)
    def build_alert_message(self, results):
        msgs = self.build_alert_messages(results)
        if not msgs:
            return None
        return "\n\n".join(msgs)


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
        messages = sd.build_alert_messages(results)
        if messages:
            for m in messages:
                print(m)
                print("---")
            print("\n📱 텔레그램 전송 중...")
            asyncio.run(sd.send_telegram(messages))
        else:
            print("수급 신호 없음 (점수 2 미만)")
    else:
        print("❌ 데이터 없음")
