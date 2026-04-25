import sys
import os
import json
import asyncio
import time
from datetime import datetime, timedelta

sys.path.insert(0, '/home/dps/stock_ai')
from modules.kis_api import KISApi

ALERT_FILE = "/home/dps/stock_ai/data/realtime_alerts.json"


class RealtimeMonitor:
    """
    실시간 모니터 전면 개편
    
    역할:
    1. 포트폴리오 보유 종목 손절/목표가 감시 (즉시 알림)
    2. AI 선정 섹터 대장주 저점 감지 (장세별 기준)
    3. 미국 대형주 저점 → 23:30 한 번만 알림
    
    알림 원칙:
    - 쿨다운 파일 저장 (재시작해도 유지)
    - 포트폴리오: 손절/목표가 즉시 + 24시간 쿨다운
    - 손절선 -5% 추가 하락: 재알림
    - 대형주 저점: 23:30 Top3만
    - 주말: 완전 스킵
    """

    def __init__(self, alert_callback, monitor, regime):
        self.alert_callback = alert_callback
        self.monitor        = monitor
        self.regime         = regime
        self.kis            = KISApi()
        self.running        = False
        self.alert_history  = self._load_alerts()

        # 23:30 대형주 저점 후보 캐시
        self.us_lowpoint_cache = {}
        self.kr_lowpoint_cache = {}

    # ── 쿨다운 파일 관리 ───────────────────────────

    def _load_alerts(self):
        if os.path.exists(ALERT_FILE):
            with open(ALERT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_alerts(self):
        os.makedirs(os.path.dirname(ALERT_FILE), exist_ok=True)
        with open(ALERT_FILE, "w", encoding="utf-8") as f:
            json.dump(self.alert_history, f, ensure_ascii=False, indent=2)

    def _can_alert(self, key, cooldown_hours=4):
        now = datetime.now().isoformat()
        if key in self.alert_history:
            last = datetime.fromisoformat(self.alert_history[key])
            diff = (datetime.now() - last).total_seconds() / 3600
            if diff < cooldown_hours:
                return False
        self.alert_history[key] = now
        self._save_alerts()
        return True

    # ── 1. 포트폴리오 보유 종목 감시 ──────────────

    async def check_portfolio(self, portfolio):
        """포트폴리오 손절/목표가 실시간 감시"""
        alerts = []

        for ticker, stock in portfolio.items():
            if not isinstance(stock, dict):
                continue

            market    = stock.get('market', 'KR')
            hold_type = stock.get('hold_type', '장기')
            buy_price = stock.get('buy_price', 0)
            stop_loss = stock.get('stop_loss')
            target1   = stock.get('target1')
            target2   = stock.get('target2')
            exit_target = stock.get('exit_target')
            name      = stock.get('name', ticker)

            # 현재가 조회
            current = self._get_price(ticker, market)
            if not current:
                continue

            profit_pct = ((current - buy_price) / buy_price) * 100
            currency   = "$" if market == "US" else "₩"

            # 손절선 도달
            if stop_loss and current <= stop_loss:
                key = f"stoploss_{ticker}"
                if self._can_alert(key, cooldown_hours=24):
                    alerts.append({
                        "type":    "🚨 손절선 도달",
                        "name":    name,
                        "ticker":  ticker,
                        "price":   current,
                        "profit":  profit_pct,
                        "currency": currency,
                        "action":  "즉시 손절 고려",
                        "urgency": "urgent"
                    })

            # 손절선 -5% 추가 하락 재알림
            elif stop_loss and current <= stop_loss * 0.95:
                key = f"stoploss_extra_{ticker}"
                if self._can_alert(key, cooldown_hours=12):
                    alerts.append({
                        "type":    "🚨🚨 손절선 -5% 추가 하락",
                        "name":    name,
                        "ticker":  ticker,
                        "price":   current,
                        "profit":  profit_pct,
                        "currency": currency,
                        "action":  "즉시 손절 강력 권고",
                        "urgency": "urgent"
                    })

            # 1차 목표가 도달
            if target1 and current >= target1:
                key = f"target1_{ticker}"
                if self._can_alert(key, cooldown_hours=24):
                    alerts.append({
                        "type":    "🎯 1차 목표가 도달",
                        "name":    name,
                        "ticker":  ticker,
                        "price":   current,
                        "profit":  profit_pct,
                        "currency": currency,
                        "action":  "절반 익절 고려",
                        "urgency": "high"
                    })

            # 2차 목표가 도달
            if target2 and current >= target2:
                key = f"target2_{ticker}"
                if self._can_alert(key, cooldown_hours=24):
                    alerts.append({
                        "type":    "🎯🎯 2차 목표가 도달",
                        "name":    name,
                        "ticker":  ticker,
                        "price":   current,
                        "profit":  profit_pct,
                        "currency": currency,
                        "action":  "전량 익절 고려",
                        "urgency": "high"
                    })

            # 탈출가 도달
            if exit_target and current >= exit_target:
                key = f"exit_{ticker}"
                if self._can_alert(key, cooldown_hours=12):
                    alerts.append({
                        "type":    "📤 탈출가 도달",
                        "name":    name,
                        "ticker":  ticker,
                        "price":   current,
                        "profit":  profit_pct,
                        "currency": currency,
                        "action":  "반등 구간 → 탈출 고려",
                        "urgency": "high"
                    })

            time.sleep(0.1)

        return alerts

    def build_portfolio_alert_msg(self, alert):
        """포트폴리오 알림 메시지"""
        urgency_emoji = {"urgent": "🚨", "high": "⚡", "medium": "🔔"}.get(alert['urgency'], "🔔")
        msg  = f"{urgency_emoji} <b>{alert['type']}</b>\n"
        msg += f"{alert['name']} ({alert['ticker']})\n\n"
        msg += f"💰 현재가: {alert['currency']}{alert['price']:,}\n"
        msg += f"📊 수익률: {alert['profit']:+.2f}%\n\n"
        msg += f"💡 {alert['action']}\n"
        msg += f"⏰ {datetime.now().strftime('%H:%M:%S')}"
        return msg

    # ── 2. AI 선정 섹터 대장주 저점 감지 ──────────

    def _get_lowpoint_score(self, ticker, market, regime_type):
        """
        장세별 저점 판단
        강세장: RSI 50~60 + 고점 대비 -5~15%
        횡보장: RSI 40~55 + 52주 저점 50% 이내
        약세장: RSI 30~45 + 52주 저점 30% 이내
        """
        try:
            import yfinance as yf
            yf_ticker = f"{ticker}.KS" if market == "KR" else ticker
            hist      = yf.Ticker(yf_ticker).history(period="60d").dropna()
            if len(hist) < 20:
                return 0, []

            close     = hist['Close']
            volume    = hist['Volume']
            current   = close.iloc[-1]
            high_52w  = close.max()
            low_52w   = close.min()
            avg_vol   = volume.mean()
            curr_vol  = volume.iloc[-1]
            vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1

            # RSI
            delta = close.diff()
            gain  = delta.clip(lower=0).rolling(14).mean()
            loss  = (-delta.clip(upper=0)).rolling(14).mean()
            rs    = gain / loss
            rsi   = round((100 - (100 / (1 + rs))).iloc[-1], 1)

            # 고점 대비 하락률
            drawdown = ((current - high_52w) / high_52w) * 100
            # 저점 대비 위치
            low_position = ((current - low_52w) / (high_52w - low_52w)) * 100 if high_52w != low_52w else 50

            score   = 0
            signals = []

            # 장세별 저점 기준
            if regime_type == "강세":
                if 50 <= rsi <= 65:
                    score += 2
                    signals.append(f"✅ RSI {rsi} 눌림목 구간")
                if -15 <= drawdown <= -5:
                    score += 2
                    signals.append(f"📉 고점 대비 {drawdown:.1f}% 조정")
            elif regime_type == "횡보":
                if 40 <= rsi <= 55:
                    score += 2
                    signals.append(f"✅ RSI {rsi} 적정 구간")
                if low_position <= 50:
                    score += 2
                    signals.append(f"📉 52주 저점 근접")
            else:  # 약세/급락
                if 30 <= rsi <= 45:
                    score += 2
                    signals.append(f"✅ RSI {rsi} 과매도 회복")
                if low_position <= 30:
                    score += 2
                    signals.append(f"📉 52주 저점 30% 이내")

            # 거래량 평소 이상
            if vol_ratio >= 1.2:
                score += 1
                signals.append(f"📦 거래량 {vol_ratio:.1f}배")

            # 당일 하락폭 -2% 이내 (바닥 다지는 중)
            day_change = ((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2]) * 100
            if -2 <= day_change <= 1:
                score += 1
                signals.append(f"✅ 당일 {day_change:+.1f}% (안정)")

            return score, signals, round(current, 2), round(rsi, 1), round(drawdown, 1)

        except Exception as e:
            return 0, [], 0, 0, 0

    async def scan_kr_lowpoints(self, sector_stocks):
        """한국 AI 선정 섹터 대장주 저점 스캔"""
        candidates = []
        regime_type = self.regime.current_regime.get('regime', '강세')

        for ticker, info in sector_stocks.items():
            result = self._get_lowpoint_score(ticker, "KR", regime_type)
            if len(result) < 5:
                continue
            score, signals, price, rsi, drawdown = result

            if score >= 4:
                candidates.append({
                    "ticker":   ticker,
                    "name":     info.get("name", ticker),
                    "sector":   info.get("sector", ""),
                    "price":    price,
                    "rsi":      rsi,
                    "drawdown": drawdown,
                    "score":    score,
                    "signals":  signals,
                    "market":   "KR"
                })
            time.sleep(0.2)

        candidates.sort(key=lambda x: x['score'], reverse=True)
        return candidates[:3]

    async def scan_us_lowpoints(self, sector_stocks):
        """미국 대형주 저점 스캔 (23:30 한 번만)"""
        candidates = []
        regime_type = self.regime.current_regime.get('regime', '강세')

        for ticker, info in sector_stocks.items():
            result = self._get_lowpoint_score(ticker, "US", regime_type)
            if len(result) < 5:
                continue
            score, signals, price, rsi, drawdown = result

            if score >= 4:
                candidates.append({
                    "ticker":   ticker,
                    "name":     info.get("name", ticker),
                    "sector":   info.get("sector", ""),
                    "price":    price,
                    "rsi":      rsi,
                    "drawdown": drawdown,
                    "score":    score,
                    "signals":  signals,
                    "market":   "US"
                })
            time.sleep(0.2)

        candidates.sort(key=lambda x: x['score'], reverse=True)
        return candidates[:3]

    def build_lowpoint_message(self, candidates, market="KR"):
        """저점 알림 메시지"""
        if not candidates:
            return None

        flag     = "🇰🇷" if market == "KR" else "🇺🇸"
        currency = "₩" if market == "KR" else "$"
        title    = "한국 대장주" if market == "KR" else "미국 대형주"

        msg  = f"{flag} <b>{title} 저점 진입 타이밍</b> {datetime.now().strftime('%m/%d %H:%M')}\n"
        msg += f"<i>장세별 저점 기준 충족 Top{len(candidates)}</i>\n\n"

        for c in candidates:
            stars    = "★" * min(c['score'], 5)
            sig_text = "\n".join([f"  {s}" for s in c['signals']])
            msg     += f"🎯 <b>{c['name']}</b> ({c['ticker']}) {stars}\n"
            msg     += f"섹터: {c['sector']}\n"
            msg     += f"{sig_text}\n"
            msg     += f"💰 현재가: {currency}{c['price']:,}\n"
            msg     += f"📊 RSI: {c['rsi']} | 고점 대비: {c['drawdown']:+.1f}%\n"
            msg     += "━━━━━━━━━━━━━━━━━━━\n"

        msg += f"⚠️ 최종 판단은 본인이 하세요\n"
        msg += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return msg

    # ── 현재가 조회 ────────────────────────────────

    def _get_price(self, ticker, market):
        try:
            if market == "KR":
                data = self.kis.get_kr_price(ticker)
                return data['price'] if data else None
            else:
                for excd in ["NAS", "NYS"]:
                    data = self.kis.get_us_price(ticker, excd)
                    if data and data.get('price', 0) > 0:
                        return data['price']
        except:
            pass
        return None

    # ── 메인 스캔 루프 ─────────────────────────────

    async def scan_once(self, portfolio, mt_context=None):
        """
        30분마다 실행
        - 포트폴리오 감시
        - 한국 대장주 저점 (장중)
        """
        hour        = datetime.now().hour
        regime_type = self.regime.current_regime.get('regime', '강세')

        # 포트폴리오 감시 (장중 + 미국장 시간)
        if (9 <= hour < 16) or (hour >= 21 or hour < 4):
            alerts = await self.check_portfolio(portfolio)
            for alert in alerts:
                msg = self.build_portfolio_alert_msg(alert)
                await self.alert_callback(msg)

        # 한국 대장주 저점 (장중만)
        if 9 <= hour < 16 and mt_context:
            sector_stocks = self._get_sector_stocks(mt_context, "KR")
            if sector_stocks:
                kr_candidates = await self.scan_kr_lowpoints(sector_stocks)
                if kr_candidates:
                    key = f"kr_lowpoint_{datetime.now().strftime('%Y%m%d%H')}"
                    if self._can_alert(key, cooldown_hours=4):
                        msg = self.build_lowpoint_message(kr_candidates, "KR")
                        if msg:
                            await self.alert_callback(msg)

    async def scan_us_evening(self, mt_context=None):
        """23:30 미국 대형주 저점 스캔 (하루 1번)"""
        key = f"us_lowpoint_{datetime.now().strftime('%Y%m%d')}"
        if not self._can_alert(key, cooldown_hours=20):
            return

        print(f"[{datetime.now().strftime('%H:%M')}] 🌙 미국 대형주 저점 스캔")
        try:
            sector_stocks = self._get_sector_stocks(mt_context, "US")
            if not sector_stocks:
                # 기본 대형주 리스트
                sector_stocks = {
                    "NVDA":  {"name": "NVIDIA",     "sector": "AI반도체"},
                    "AAPL":  {"name": "Apple",      "sector": "빅테크"},
                    "MSFT":  {"name": "Microsoft",  "sector": "빅테크"},
                    "GOOGL": {"name": "Google",     "sector": "빅테크"},
                    "META":  {"name": "META",        "sector": "빅테크"},
                    "TSM":   {"name": "TSMC",        "sector": "반도체"},
                    "AMD":   {"name": "AMD",          "sector": "AI반도체"},
                    "AMZN":  {"name": "Amazon",      "sector": "빅테크"},
                    "AVGO":  {"name": "Broadcom",    "sector": "반도체"},
                    "VST":   {"name": "Vistra",      "sector": "전력"},
                }

            candidates = await self.scan_us_lowpoints(sector_stocks)
            if candidates:
                msg = self.build_lowpoint_message(candidates, "US")
                if msg:
                    await self.alert_callback(msg)
                    print(f"  ✅ 미국 저점 Top{len(candidates)} 알림 발송")
            else:
                print("  ℹ️ 저점 조건 충족 미국 종목 없음")
        except Exception as e:
            print(f"  ❌ 미국 저점 스캔 실패: {e}")

    def _get_sector_stocks(self, mt_context, market="KR"):
        """AI 선정 섹터의 종목 목록"""
        if not mt_context:
            return {}

        try:
            from modules.sector_db import SECTOR_DB
            selected = [s['kr_sector'] for s in mt_context.get('ai_result', {}).get('selected_sectors', [])]
            stocks   = {}

            for sector_name, sector_data in SECTOR_DB.items():
                if sector_data.get('market', 'KR') != market:
                    continue
                matched = any(
                    s.lower() in sector_name.lower() or sector_name.lower() in s.lower()
                    for s in selected
                )
                if not matched:
                    continue
                for tier in ['대장주']:
                    for name, ticker in sector_data.get(tier, {}).items():
                        stocks[ticker] = {"name": name, "sector": sector_name}
            return stocks
        except:
            return {}

    async def run_forever(self, interval_sec=300):
        self.running = True
        print(f"✅ 실시간 모니터 시작 (매 {interval_sec//60}분)")

        while self.running:
            try:
                # 주말 스킵
                if datetime.now().weekday() >= 5:
                    await asyncio.sleep(interval_sec)
                    continue

                hour = datetime.now().hour
                kr_open = (9 <= hour < 16)
                us_open = (hour >= 21 or hour < 4)

                if kr_open or us_open:
                    # 포트폴리오 파일에서 직접 읽기
                    portfolio = self._load_portfolio()
                    await self.scan_once(portfolio)
                else:
                    print(f"[{datetime.now().strftime('%H:%M')}] 💤 장 마감 대기 중")

            except Exception as e:
                print(f"❌ 실시간 스캔 오류: {e}")

            await asyncio.sleep(interval_sec)

    def _load_portfolio(self):
        try:
            with open("/home/dps/stock_ai/data/portfolio.json", "r") as f:
                return json.load(f)
        except:
            return {}

    def stop(self):
        self.running = False
