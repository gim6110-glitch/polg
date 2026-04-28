import os
import sys
import json
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

sys.path.insert(0, '/media/dps/T7/stock_ai')
load_dotenv('/media/dps/T7/stock_ai/.env')

GUARD_FILE    = "/media/dps/T7/stock_ai/data/trade_guard.json"
SNAPSHOT_FILE = "/media/dps/T7/stock_ai/data/asset_snapshots.json"


class TradeGuard:
    """
    매매 금지 조건 + 손실 한도 + 신호 등급 + 포지션 사이징
    규칙 기반으로만 동작 (AI 없음 → 빠르고 확실하게)
    AI는 VIX 40 이상일 때만 호출
    """

    def __init__(self):
        self.data      = self._load()
        self.snapshots = self._load_snapshots()

    # ── 파일 관리 ──────────────────────────────────

    def _load(self):
        if os.path.exists(GUARD_FILE):
            with open(GUARD_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        default = {
            "rest_until":        None,   # 3일 휴식 종료일
            "rest_reason":       None,
            "monthly_start":     None,   # 이번 달 시작 총자산
            "weekly_start":      None,   # 이번 주 시작 총자산
            "consecutive_losses": 0,     # 연속 손절 카운트
        }
        self._save(default)
        return default

    def _save(self, data=None):
        os.makedirs(os.path.dirname(GUARD_FILE), exist_ok=True)
        if data is None:
            data = self.data
        with open(GUARD_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load_snapshots(self):
        if os.path.exists(SNAPSHOT_FILE):
            with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_snapshots(self):
        os.makedirs(os.path.dirname(SNAPSHOT_FILE), exist_ok=True)
        with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
            json.dump(self.snapshots, f, ensure_ascii=False, indent=2)

    # ── 총자산 스냅샷 ──────────────────────────────

    def save_snapshot(self, total_assets_krw, exchange_rate=1300.0):
        """매일 08:00 총자산 스냅샷 저장 (환율 반영)"""
        today = datetime.now().strftime("%Y-%m-%d")
        week  = datetime.now().strftime("%Y-W%W")
        month = datetime.now().strftime("%Y-%m")

        self.snapshots[today] = {
            "total_krw":    total_assets_krw,
            "exchange_rate": exchange_rate,
            "timestamp":    datetime.now().isoformat()
        }
        self._save_snapshots()

        # 주간/월간 시작값 업데이트
        if not self.data.get("weekly_start") or datetime.now().weekday() == 0:
            self.data["weekly_start"] = total_assets_krw
        if not self.data.get("monthly_start") or datetime.now().day == 1:
            self.data["monthly_start"] = total_assets_krw
        self._save()

        print(f"  💾 총자산 스냅샷 저장: {total_assets_krw:,.0f}원")

    def get_total_assets(self, portfolio, exchange_rate=None):
        """총자산 계산 (환율 반영)"""
        try:
            import yfinance as yf

            # 환율 조회
            if exchange_rate is None:
                try:
                    fx   = yf.Ticker("KRW=X").history(period="2d").dropna()
                    exchange_rate = fx['Close'].iloc[-1] if not fx.empty else 1300.0
                except:
                    exchange_rate = 1300.0

            # 예수금
            cash_krw = portfolio.get("_cash", 0)
            cash_usd = portfolio.get("_cash_usd", 0)

            total = cash_krw + (cash_usd * exchange_rate)

            # 주식 평가액
            from modules.kis_api import KISApi
            kis = KISApi()

            for ticker, stock in portfolio.items():
                if not isinstance(stock, dict):
                    continue
                market    = stock.get('market', 'KR')
                quantity  = stock.get('quantity', 0)
                buy_price = stock.get('buy_price', 0)

                try:
                    if market == "KR":
                        data = kis.get_kr_price(ticker)
                        price = data['price'] if data else buy_price
                        total += price * quantity
                    else:
                        price = buy_price
                        for excd in ["NAS", "NYS"]:
                            data = kis.get_us_price(ticker, excd)
                            if data and data.get('price', 0) > 0:
                                price = data['price']
                                break
                        total += price * quantity * exchange_rate
                    time.sleep(0.1)
                except:
                    total += buy_price * quantity * (exchange_rate if market == "US" else 1)

            return round(total, 0), exchange_rate

        except Exception as e:
            print(f"  ⚠️ 총자산 계산 실패: {e}")
            return 0, 1300.0

    # ── 장세 신뢰도 ────────────────────────────────

    def calc_regime_confidence(self, mt_context):
        """
        market_temperature 결과로 장세 신뢰도 점수 계산
        60점 미만 → 진입 금지
        """
        if not mt_context:
            return 40, "낮음"

        ai_result  = mt_context.get("ai_result", {})
        kr_temp    = mt_context.get("kr_temp", {})
        confidence = ai_result.get("regime_confidence", "낮음")

        # 기본 점수
        score = {"높음": 80, "보통": 60, "낮음": 40}.get(confidence, 40)

        # VIX 보정
        vix = kr_temp.get("vix", 20)
        if vix >= 30:
            score -= 20
        elif vix >= 25:
            score -= 10

        # 외국인 수급 보정
        foreign_dir  = kr_temp.get("foreign_direction", "불명")
        foreign_cons = kr_temp.get("foreign_consecutive", 0)
        if foreign_dir == "매도" and foreign_cons >= 3:
            score -= 20
        elif foreign_dir == "매도":
            score -= 10

        score = max(0, min(100, score))
        level = "높음" if score >= 80 else "보통" if score >= 60 else "낮음"
        return score, level

    # ── 손실 한도 체크 ─────────────────────────────

    def check_loss_limits(self, current_total):
        """일/주/월 손실 한도 체크"""
        violations = []
        today      = datetime.now().strftime("%Y-%m-%d")
        yesterday  = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        # 일간 손실
        if yesterday in self.snapshots:
            prev    = self.snapshots[yesterday]["total_krw"]
            day_pct = ((current_total - prev) / prev) * 100 if prev > 0 else 0
            if day_pct <= -1.0:
                violations.append({
                    "type":    "일간",
                    "limit":   -1.0,
                    "actual":  round(day_pct, 2),
                    "action":  "당일 신규 매수 중단"
                })

        # 주간 손실
        weekly_start = self.data.get("weekly_start")
        if weekly_start and weekly_start > 0:
            week_pct = ((current_total - weekly_start) / weekly_start) * 100
            if week_pct <= -3.0:
                violations.append({
                    "type":   "주간",
                    "limit":  -3.0,
                    "actual": round(week_pct, 2),
                    "action": "주간 신규 매수 중단"
                })

        # 월간 손실
        monthly_start = self.data.get("monthly_start")
        if monthly_start and monthly_start > 0:
            month_pct = ((current_total - monthly_start) / monthly_start) * 100
            if month_pct <= -7.0:
                violations.append({
                    "type":   "월간",
                    "limit":  -7.0,
                    "actual": round(month_pct, 2),
                    "action": "월간 신규 매수 중단 + AI 진단 요청"
                })

        return violations

    # ── 연속 손절 체크 ─────────────────────────────

    def record_stop_loss(self):
        """손절 발생 시 호출"""
        self.data["consecutive_losses"] = self.data.get("consecutive_losses", 0) + 1
        count = self.data["consecutive_losses"]

        if count >= 3:
            rest_until = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
            self.data["rest_until"]  = rest_until
            self.data["rest_reason"] = f"연속 {count}회 손절 → 3일 휴식"
            self._save()
            return True, f"연속 {count}회 손절 감지 → {rest_until}까지 신규 매수 금지"

        self._save()
        return False, None

    def reset_consecutive_losses(self):
        """익절 성공 시 연속 손절 초기화"""
        self.data["consecutive_losses"] = 0
        self._save()

    def is_in_rest(self):
        """휴식 기간 중인지 확인"""
        rest_until = self.data.get("rest_until")
        if not rest_until:
            return False, None
        if datetime.now().strftime("%Y-%m-%d") <= rest_until:
            return True, self.data.get("rest_reason", "휴식 기간")
        # 휴식 종료
        self.data["rest_until"]         = None
        self.data["rest_reason"]        = None
        self.data["consecutive_losses"] = 0
        self._save()
        return False, None

    # ── 시장 조건 체크 ─────────────────────────────

    def check_market_conditions(self, mt_context=None):
        """
        매매 금지 조건 체크
        규칙 기반으로만 (AI 없음)
        """
        conditions = []

        try:
            import yfinance as yf

            # 코스피 5일 연속 하락
            try:
                ks   = yf.Ticker("^KS11").history(period="10d").dropna()
                if len(ks) >= 5:
                    last5      = ks['Close'].tail(5).tolist()
                    kr_falling = all(last5[i] > last5[i+1] for i in range(4))
                    if kr_falling:
                        conditions.append({
                            "type":   "코스피_연속하락",
                            "reason": "코스피 5일 연속 하락",
                            "action": "한국 신규 진입 금지"
                        })
            except:
                pass

            # 나스닥 5일 연속 하락
            try:
                nas  = yf.Ticker("^IXIC").history(period="10d").dropna()
                if len(nas) >= 5:
                    last5      = nas['Close'].tail(5).tolist()
                    us_falling = all(last5[i] > last5[i+1] for i in range(4))
                    if us_falling:
                        conditions.append({
                            "type":   "나스닥_연속하락",
                            "reason": "나스닥 5일 연속 하락",
                            "action": "미국 신규 진입 금지"
                        })
            except:
                pass

            # VIX 체크
            try:
                vix_data = yf.Ticker("^VIX").history(period="2d").dropna()
                vix      = vix_data['Close'].iloc[-1] if not vix_data.empty else 20

                if vix >= 40:
                    conditions.append({
                        "type":    "VIX_극공포",
                        "reason":  f"VIX {vix:.1f} (극공포)",
                        "action":  "AI 판단 요청 (기회 or 위기)",
                        "vix":     vix,
                        "needs_ai": True
                    })
                elif vix >= 30:
                    conditions.append({
                        "type":   "VIX_공포",
                        "reason": f"VIX {vix:.1f} (공포)",
                        "action": "신규 진입 주의"
                    })
            except:
                pass

            # FOMC/CPI 체크
            today = datetime.now().strftime("%Y-%m-%d")
            from modules.event_calendar import EventCalendar
            _ec = EventCalendar()
            fomc_dates = _ec.data.get("fomc", [])
            cpi_dates  = _ec.data.get("cpi", [])

            if today in fomc_dates:
                conditions.append({
                    "type":   "FOMC",
                    "reason": "FOMC 발표 당일",
                    "action": "장전 신규 진입 금지 (결과 후 진입)"
                })
            if today in cpi_dates:
                conditions.append({
                    "type":   "CPI",
                    "reason": "CPI 발표 당일",
                    "action": "변동성 주의"
                })

        except Exception as e:
            print(f"  ⚠️ 시장 조건 체크 실패: {e}")

        return conditions

    def _get_fomc_dates(self):
        """FOMC 예정일 (수동 업데이트 필요)"""
        return [
            "2026-01-28", "2026-03-18", "2026-05-06",
            "2026-06-17", "2026-07-29", "2026-09-16",
            "2026-11-04", "2026-12-16",
        ]

    def _get_cpi_dates(self):
        """CPI 발표 예정일 (수동 업데이트 필요)"""
        return [
            "2026-01-15", "2026-02-12", "2026-03-12",
            "2026-04-10", "2026-05-13", "2026-06-11",
            "2026-07-15", "2026-08-12", "2026-09-11",
            "2026-10-14", "2026-11-12", "2026-12-11",
        ]

    # ── 신호 등급 + 포지션 사이징 ──────────────────

    def grade_signal(self, ticker, stock_data, mt_context=None,
                     supply_score=0, total_assets=0):
        """
        신호 등급 A/B/C/D 산출 + 포지션 사이징
        규칙 기반으로만
        """
        score  = 0
        detail = []

        # 1. 수급 (외국인/기관 순매수)
        if supply_score >= 3:
            score += 1
            detail.append("✅ 수급")
        else:
            detail.append("❌ 수급")

        # 2. 섹터 (오늘 AI 선정 섹터 해당)
        if mt_context:
            selected = [s['kr_sector'] for s in mt_context.get('ai_result', {}).get('selected_sectors', [])]
            sector   = stock_data.get('sector', '')
            if any(s.lower() in sector.lower() or sector.lower() in s.lower() for s in selected):
                score += 1
                detail.append("✅ 섹터")
            else:
                detail.append("❌ 섹터")
        else:
            detail.append("❌ 섹터")

        # 3. 거래량 (평균 대비 1.5배 이상)
        vol_ratio = stock_data.get('vol_ratio', 1)
        if vol_ratio >= 1.5:
            score += 1
            detail.append(f"✅ 거래량({vol_ratio}배)")
        else:
            detail.append(f"❌ 거래량({vol_ratio}배)")

        # 4. 차트 (VWAP 위 + 5일선 위)
        above_vwap = stock_data.get('above_vwap', False)
        above_ma5  = stock_data.get('above_ma5', False)
        if above_vwap and above_ma5:
            score += 1
            detail.append("✅ 차트")
        else:
            detail.append("❌ 차트")

        # 5. AI 판단 (긍정)
        ai_positive = stock_data.get('ai_positive', False)
        if ai_positive:
            score += 1
            detail.append("✅ AI")
        else:
            detail.append("❌ AI")

        # 등급 산출
        if score == 5:
            grade = "A"
        elif score == 4:
            grade = "B"
        elif score == 3:
            grade = "C"
        else:
            grade = "D"

        # 포지션 사이징
        position = self._calc_position(grade, stock_data.get('price', 0), total_assets)

        return {
            "grade":    grade,
            "score":    score,
            "detail":   detail,
            "position": position,
        }

    def _calc_position(self, grade, price, total_assets):
        """등급별 포지션 사이징"""
        if grade == "A":
            ratio = 0.05  # 총자산 5%
        elif grade == "B":
            ratio = 0.03  # 총자산 3%
        else:
            return {"investable": False, "reason": f"{grade}등급 매수 금지"}

        if total_assets <= 0 or price <= 0:
            return {"investable": True, "ratio": ratio, "amount": 0, "quantity": 0}

        amount   = total_assets * ratio
        quantity = int(amount / price)

        return {
            "investable": True,
            "grade":      grade,
            "ratio":      ratio,
            "amount":     round(amount, 0),
            "quantity":   quantity,
            "price":      price,
        }

    # ── 전체 체크 ──────────────────────────────────

    def full_check(self, mt_context=None, current_total=0):
        """
        모든 매매 금지 조건 한 번에 체크
        returns: (is_blocked, reasons, warnings)
        """
        blocked  = []
        warnings = []

        # 1. 휴식 기간
        in_rest, rest_reason = self.is_in_rest()
        if in_rest:
            blocked.append(f"🛑 휴식 기간: {rest_reason}")

        # 2. 장세 신뢰도
        if mt_context:
            score, level = self.calc_regime_confidence(mt_context)
            if score < 60:
                blocked.append(f"🛑 장세 신뢰도 부족: {score}점 ({level})")
            elif score < 70:
                warnings.append(f"⚠️ 장세 신뢰도 주의: {score}점")

        # 3. 손실 한도
        if current_total > 0:
            violations = self.check_loss_limits(current_total)
            for v in violations:
                blocked.append(f"🛑 {v['type']} 손실 한도 초과: {v['actual']:+.1f}% → {v['action']}")

        # 4. 시장 조건
        conditions = self.check_market_conditions(mt_context)
        for c in conditions:
            if c.get("needs_ai"):
                warnings.append(f"⚠️ {c['reason']} → {c['action']}")
            elif c['type'] in ["코스피_연속하락", "나스닥_연속하락", "FOMC"]:
                blocked.append(f"🛑 {c['reason']} → {c['action']}")
            else:
                warnings.append(f"⚠️ {c['reason']}")

        is_blocked = len(blocked) > 0
        return is_blocked, blocked, warnings

    # ── VIX 40 이상 AI 판단 ────────────────────────

    async def ai_vix_judgment(self, vix, mt_context=None):
        """VIX 40 이상일 때만 AI 호출 (기회 vs 위기)"""
        from anthropic import Anthropic
        import re, json as _json

        macro_text = ""
        if mt_context:
            macro = mt_context.get("macro", {})
            for name, data in list(macro.items())[:5]:
                macro_text += f"{name}: {data.get('change', 0):+.2f}%\n"

        prompt = f"""VIX {vix:.1f}로 극공포 구간입니다.
지금이 매수 기회인지 위기인지 판단해주세요.

=== 매크로 ===
{macro_text}

판단 기준:
- 기회: 펀더멘털 이상 없음 + 수급 전환 조짐 + 패닉셀
- 위기: 구조적 문제 + 수급 지속 악화 + 추세적 하락

JSON으로만:
{{
  "judgment": "기회 or 위기",
  "confidence": "높음 or 보통",
  "reason": "한줄 이유",
  "action": "중장기/도박 소액 매수 허용 or 전면 관망",
  "sectors": ["수혜 섹터1", "섹터2"]
}}"""

        try:
            client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
            res    = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )
            text = re.sub(r'```json|```', '', res.content[0].text.strip()).strip()
            m    = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                return _json.loads(m.group())
        except Exception as e:
            print(f"  ❌ VIX AI 판단 실패: {e}")
        return None

    # ── 메시지 생성 ────────────────────────────────

    def build_guard_message(self, is_blocked, blocked, warnings,
                            score=None, grade_info=None):
        """매매 가드 상태 메시지"""
        if is_blocked:
            msg  = f"🛑 <b>매매 금지 조건 발동</b>\n\n"
            for b in blocked:
                msg += f"{b}\n"
        else:
            msg  = f"✅ <b>매매 가능</b>\n\n"

        if warnings:
            msg += f"\n⚠️ <b>주의사항</b>\n"
            for w in warnings:
                msg += f"{w}\n"

        if score is not None:
            msg += f"\n📊 장세 신뢰도: {score}점\n"

        if grade_info:
            grade    = grade_info.get('grade', '?')
            position = grade_info.get('position', {})
            msg     += f"\n🎯 신호 등급: {grade}등급\n"
            if position.get('investable'):
                msg += f"💰 투자 가능 금액: {position.get('amount', 0):,.0f}원\n"
                msg += f"📦 추천 수량: {position.get('quantity', 0)}주\n"
            else:
                msg += f"🚫 {position.get('reason', '매수 금지')}\n"

        msg += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return msg

    def build_snapshot_message(self, current_total, exchange_rate):
        """총자산 스냅샷 메시지"""
        today         = datetime.now().strftime("%Y-%m-%d")
        yesterday_key = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        msg  = f"💰 <b>총자산 현황</b> {datetime.now().strftime('%m/%d')}\n\n"
        msg += f"총자산: {current_total:,.0f}원\n"
        msg += f"환율: {exchange_rate:,.1f}원/달러\n"

        if yesterday_key in self.snapshots:
            prev    = self.snapshots[yesterday_key]["total_krw"]
            day_pct = ((current_total - prev) / prev) * 100 if prev > 0 else 0
            arrow   = "▲" if day_pct > 0 else "▼"
            msg    += f"전일 대비: {arrow}{day_pct:+.2f}%\n"

        weekly_start = self.data.get("weekly_start")
        if weekly_start:
            week_pct = ((current_total - weekly_start) / weekly_start) * 100
            msg     += f"주간 수익률: {week_pct:+.2f}%\n"

        monthly_start = self.data.get("monthly_start")
        if monthly_start:
            month_pct = ((current_total - monthly_start) / monthly_start) * 100
            msg      += f"월간 수익률: {month_pct:+.2f}%\n"

        msg += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return msg
