from datetime import datetime
import time

from modules.kis_api import KISApi


THEME_MAP = {
    "전선/전력": ["선도전기", "제일일렉트릭", "대원전선", "KBI메탈", "LS에코에너지", "제룡전기"],
    "화학/정유": ["롯데케미칼", "대한유화", "S-Oil", "이수화학", "코오롱"],
    "방산": ["한화에어로스페이스", "LIG넥스원", "현대로템", "한국항공우주"],
    "반도체": ["삼성전자", "SK하이닉스", "한미반도체", "이오테크닉스"],
    "2차전지": ["LG에너지솔루션", "삼성SDI", "에코프로비엠", "포스코퓨처엠"],
    "AI/로봇": ["두산로보틱스", "레인보우로보틱스", "HD현대", "삼성SDS"],
    "바이오": ["삼성바이오로직스", "셀트리온", "한미약품", "유한양행"],
}


class ThemeHunter:
    def __init__(self):
        self.kis = KISApi()
        self.log_prefix = "[ThemeHunter]"
        self.alert_state = {}

    def _log(self, level, fn, msg):
        print(f"{self.log_prefix}[{fn}][{level}] {msg}")

    def _group_theme_hits(self, top_rows):
        by_name = {row["name"]: row for row in top_rows}
        fired = {}
        for theme, names in THEME_MAP.items():
            leaders = [by_name[n] for n in names if n in by_name and by_name[n]["change_pct"] >= 8]
            if len(leaders) >= 2:
                laggards = [by_name[n] for n in names if n in by_name and by_name[n]["change_pct"] < 5]
                fired[theme] = {"leaders": sorted(leaders, key=lambda x: x["change_pct"], reverse=True), "laggards": laggards}
        return fired

    def _should_notify(self, key, score=0, cooldown_sec=1800):
        """분석은 계속, 알림만 쿨다운/강도상승 우선 전송"""
        now = time.time()
        prev = self.alert_state.get(key)
        if not prev:
            self.alert_state[key] = {"ts": now, "score": score}
            return True
        elapsed = now - prev["ts"]
        if score >= prev.get("score", 0) + 2:
            self.alert_state[key] = {"ts": now, "score": score}
            return True
        if elapsed >= cooldown_sec:
            self.alert_state[key] = {"ts": now, "score": score}
            return True
        return False

    async def scan_morning_surge(self, send_func):
        rows = self.kis.get_top_fluctuation(market="J", count=50)
        if not rows:
            return
        fired = self._group_theme_hits(rows)
        if not fired:
            return
        top_score = max([d["leaders"][0]["change_pct"] for d in fired.values() if d["leaders"]], default=0)
        if not self._should_notify("morning_surge", score=top_score, cooldown_sec=1200):
            return
        lines = [f"🔥 오전 테마 발화 감지 ({datetime.now().strftime('%H:%M')})", ""]
        for theme, data in fired.items():
            leaders = ", ".join([f"{r['name']} {r['change_pct']:+.2f}%" for r in data["leaders"][:3]])
            lines.append(f"[{theme}]")
            lines.append(f"대장주: {leaders}")
            if data["laggards"]:
                lines.append("아직 안 오른 종목:")
                for r in data["laggards"][:3]:
                    lines.append(f"- {r['name']} 현재 {r['change_pct']:+.2f}% (진입 검토)")
            lines.append("")
        await send_func("\n".join(lines).strip())

    async def scan_pullback(self, send_func):
        rows = self.kis.get_top_fluctuation(market="J", count=50)
        if not rows:
            return
        picks = []
        for row in rows:
            if row["change_pct"] < 5:
                continue
            indicators = self.kis.calc_indicators_kr(row["ticker"], days=60)
            if not indicators:
                continue
            vol_ratio = indicators.get("vol_ratio", 0)
            ma5 = indicators.get("ma5", 0)
            if vol_ratio >= 3 and row["price"] > ma5:
                picks.append((row, indicators))
        if not picks:
            return
        best_score = picks[0][0]["change_pct"]
        if not self._should_notify("pullback", score=best_score, cooldown_sec=1800):
            return
        picks = sorted(picks, key=lambda x: (x[0]["change_pct"], x[1].get("vol_ratio", 0)), reverse=True)[:2]
        msg = [f"📉 09:40 눌림목 후보 ({datetime.now().strftime('%H:%M')})"]
        for row, ind in picks:
            msg.append(f"- {row['name']} {row['change_pct']:+.2f}% | 거래량 {ind.get('vol_ratio', 0)}배 | 5일선 {int(ind.get('ma5', 0)):,}원")
        msg.append("※ 규칙 기반 1차 선별 결과")
        await send_func("\n".join(msg))

    async def scan_afternoon_surge(self, send_func):
        rows = self.kis.get_top_fluctuation(market="J", count=50)
        if not rows:
            return
        candidates = [r for r in rows if 5 <= r["change_pct"] <= 8]
        if not candidates:
            return
        top_score = max([c["change_pct"] for c in candidates], default=0)
        if not self._should_notify("afternoon_surge", score=top_score, cooldown_sec=2400):
            return
        msg = [f"⏱️ 오후 재점화 감시 ({datetime.now().strftime('%H:%M')})", "보합 구간 후보:"]
        for r in candidates[:8]:
            msg.append(f"- {r['name']} {r['change_pct']:+.2f}% / 거래량 {r['volume']:,}")
        await send_func("\n".join(msg))

    async def scan_nxt_preempt(self, send_func):
        rows = self.kis.get_top_fluctuation(market="J", count=50)
        if not rows:
            return
        fired = self._group_theme_hits(rows)
        if not fired:
            return
        top_score = max([d["leaders"][0]["change_pct"] for d in fired.values() if d["leaders"]], default=0)
        if not self._should_notify("nxt_preempt", score=top_score, cooldown_sec=3600):
            return
        lines = [f"🌙 내일 NXT 선점 후보 ({datetime.now().strftime('%m/%d %H:%M')})"]
        for theme, data in fired.items():
            leaders = ", ".join([f"{r['name']} {r['change_pct']:+.2f}%" for r in data["leaders"][:2]])
            lines.append(f"\n[{theme}] 대장주: {leaders}")
            laggards = data["laggards"][:2]
            if laggards:
                lines.append("아직 안 오른 종목:")
                for r in laggards:
                    lines.append(f"- {r['name']} 오늘 {r['change_pct']:+.2f}%")
        await send_func("\n".join(lines))

    async def scan_us_etf_surge(self, send_func):
        etf_map = {
            "XLU": "전선/전력",
            "SOXX": "반도체",
            "XLE": "정유/화학",
            "XLF": "은행/금융",
            "ITB": "건설",
        }
        try:
            import yfinance as yf
            hits = []
            for etf, kr_theme in etf_map.items():
                hist = yf.Ticker(etf).history(period="2d").dropna()
                if len(hist) < 2:
                    continue
                prev = float(hist["Close"].iloc[-2])
                curr = float(hist["Close"].iloc[-1])
                pct = ((curr - prev) / prev) * 100
                if pct >= 3:
                    hits.append((etf, kr_theme, pct))
            if not hits:
                return
            if not self._should_notify("us_etf_surge", score=max([h[2] for h in hits]), cooldown_sec=3600):
                return
            lines = [f"🇺🇸 미국 섹터 ETF 급등 ({datetime.now().strftime('%m/%d %H:%M')})"]
            for etf, kr_theme, pct in hits:
                lines.append(f"- {etf} {pct:+.2f}% → 한국 {kr_theme} 체크")
            await send_func("\n".join(lines))
        except Exception as e:
            self._log("ERROR", "scan_us_etf_surge", str(e))

    async def scan_earnings_preview(self, send_func):
        watch = ["RXRX", "IONQ", "RKLB", "OKLO"]
        try:
            import yfinance as yf
            lines = [f"🗓️ 어닝 프리뷰 ({datetime.now().strftime('%m/%d %H:%M')})"]
            found = 0
            for ticker in watch:
                tk = yf.Ticker(ticker)
                cal = getattr(tk, "calendar", None)
                if cal is None or len(cal) == 0:
                    continue
                found += 1
                lines.append(f"- {ticker}: 어닝 일정 확인 필요 (캘린더 감지)")
            if found == 0:
                return
            if not self._should_notify("earnings_preview", score=found, cooldown_sec=3600):
                return
            lines.append("※ 어닝 당일 변동성 확대 주의")
            await send_func("\n".join(lines))
        except Exception as e:
            self._log("ERROR", "scan_earnings_preview", str(e))

    async def scan_us_top_movers(self, send_func):
        watch = ["APLD", "AMPX", "RXRX", "IONQ", "RKLB", "OKLO", "RGTI", "ASTS"]
        try:
            import yfinance as yf
            hits = []
            for ticker in watch:
                hist = yf.Ticker(ticker).history(period="2d").dropna()
                if len(hist) < 2:
                    continue
                prev = float(hist["Close"].iloc[-2])
                curr = float(hist["Close"].iloc[-1])
                pct = ((curr - prev) / prev) * 100
                if pct >= 10:
                    hits.append((ticker, pct))
            if not hits:
                return
            if not self._should_notify("us_top_movers", score=max([h[1] for h in hits]), cooldown_sec=3600):
                return
            hits.sort(key=lambda x: x[1], reverse=True)
            lines = [f"🚀 미국 급등주 감시 ({datetime.now().strftime('%m/%d %H:%M')})"]
            for ticker, pct in hits[:5]:
                lines.append(f"- {ticker} {pct:+.2f}%")
            await send_func("\n".join(lines))
        except Exception as e:
            self._log("ERROR", "scan_us_top_movers", str(e))
