import sys
import os
import json
import sqlite3
from datetime import datetime, timedelta
from dotenv import load_dotenv

sys.path.insert(0, '/home/dps/stock_ai')
load_dotenv('/home/dps/stock_ai/.env')

class AILearning:
    """
    AI 진단 결과 DB 저장 + 결과 추적
    시간이 쌓일수록 AI 판단 정확도 향상
    """
    def __init__(self):
        self.db_file = "/home/dps/stock_ai/data/ai_learning.db"
        self._init_db()

    def _init_db(self):
        """DB 초기화"""
        os.makedirs("/home/dps/stock_ai/data", exist_ok=True)
        conn = sqlite3.connect(self.db_file)
        c    = conn.cursor()

        # AI 진단 기록 테이블
        c.execute('''
            CREATE TABLE IF NOT EXISTS diagnosis_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT NOT NULL,
                ticker      TEXT NOT NULL,
                name        TEXT NOT NULL,
                status      TEXT,
                reason      TEXT,
                action      TEXT,
                price_at    REAL,
                ai_raw      TEXT,
                created_at  TEXT
            )
        ''')

        # 결과 추적 테이블 (다음날 실제 가격과 비교)
        c.execute('''
            CREATE TABLE IF NOT EXISTS result_log (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                diagnosis_id  INTEGER,
                date          TEXT,
                ticker        TEXT,
                name          TEXT,
                ai_status     TEXT,
                ai_action     TEXT,
                price_at      REAL,
                price_next    REAL,
                price_change  REAL,
                ai_correct    INTEGER,
                created_at    TEXT
            )
        ''')

        # 뉴스 기록 테이블
        c.execute('''
            CREATE TABLE IF NOT EXISTS news_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                date       TEXT,
                source     TEXT,
                title      TEXT,
                impact     TEXT,
                created_at TEXT
            )
        ''')

        # 시장 상황 기록 테이블
        c.execute('''
            CREATE TABLE IF NOT EXISTS market_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT,
                regime      TEXT,
                kospi       REAL,
                fear_greed  REAL,
                vix         REAL,
                created_at  TEXT
            )
        ''')

        conn.commit()
        conn.close()
        print("✅ AI 학습 DB 초기화 완료")

    def save_diagnosis(self, diagnosis_text, portfolio_prices):
        """AI 진단 결과 저장"""
        today = datetime.now().strftime("%Y-%m-%d")
        conn  = sqlite3.connect(self.db_file)
        c     = conn.cursor()

        # 진단 텍스트 파싱
        lines   = diagnosis_text.split('\n')
        records = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # "[종목명] 상태: ✅순항" 형식 파싱
            status = None
            action = None
            reason = ""

            if '✅' in line or '순항' in line:
                status = '순항'
            elif '🚨' in line or '위험' in line:
                status = '위험'
            elif '⚠️' in line or '주의' in line:
                status = '주의'

            if '계속보유' in line:
                action = '계속보유'
            elif '익절고려' in line or '익절 고려' in line:
                action = '익절고려'
            elif '손절고려' in line or '손절 고려' in line:
                action = '손절고려'

            if status:
                # 종목명 추출 시도
                for ticker, price in portfolio_prices.items():
                    if ticker in line or str(price) in line:
                        c.execute('''
                            INSERT INTO diagnosis_log
                            (date, ticker, name, status, reason, action,
                             price_at, ai_raw, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            today, ticker, ticker, status, reason, action,
                            price, line, datetime.now().isoformat()
                        ))

        # 전체 진단 텍스트도 저장
        c.execute('''
            INSERT INTO diagnosis_log
            (date, ticker, name, status, reason, action, price_at, ai_raw, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            today, 'ALL', '전체진단', None, None, None,
            None, diagnosis_text, datetime.now().isoformat()
        ))

        conn.commit()
        conn.close()
        print(f"✅ AI 진단 저장 완료 ({today})")

    def save_news(self, news_list, impact_text=""):
        """뉴스 저장"""
        today = datetime.now().strftime("%Y-%m-%d")
        conn  = sqlite3.connect(self.db_file)
        c     = conn.cursor()

        for news in news_list[:20]:
            c.execute('''
                INSERT INTO news_log (date, source, title, impact, created_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                today,
                news.get('source', ''),
                news.get('title', ''),
                impact_text,
                datetime.now().isoformat()
            ))

        conn.commit()
        conn.close()

    def save_market_status(self, regime, kospi, fear_greed, vix):
        """시장 상황 저장"""
        today = datetime.now().strftime("%Y-%m-%d")
        conn  = sqlite3.connect(self.db_file)
        c     = conn.cursor()

        # 오늘 데이터 이미 있으면 업데이트
        c.execute('SELECT id FROM market_log WHERE date=?', (today,))
        existing = c.fetchone()

        if existing:
            c.execute('''
                UPDATE market_log
                SET regime=?, kospi=?, fear_greed=?, vix=?
                WHERE date=?
            ''', (regime, kospi, fear_greed, vix, today))
        else:
            c.execute('''
                INSERT INTO market_log
                (date, regime, kospi, fear_greed, vix, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (today, regime, kospi, fear_greed, vix,
                  datetime.now().isoformat()))

        conn.commit()
        conn.close()

    def track_results(self, portfolio):
        """전날 진단 결과 vs 실제 가격 비교"""
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        conn      = sqlite3.connect(self.db_file)
        c         = conn.cursor()

        # 전날 진단 중 결과 미추적된 것들
        c.execute('''
            SELECT id, ticker, name, status, action, price_at
            FROM diagnosis_log
            WHERE date=? AND ticker != 'ALL' AND status IS NOT NULL
        ''', (yesterday,))
        yesterday_logs = c.fetchall()

        tracked = 0
        for log in yesterday_logs:
            diag_id, ticker, name, ai_status, ai_action, price_at = log

            # 이미 추적했는지 확인
            c.execute('SELECT id FROM result_log WHERE diagnosis_id=?', (diag_id,))
            if c.fetchone():
                continue

            # 현재 가격 조회
            stock = portfolio.get(ticker)
            if not stock:
                continue

            from modules.kis_api import KISApi
            kis = KISApi()
            if stock.get('market') == 'KR':
                data = kis.get_kr_price(ticker)
            else:
                data = kis.get_us_price(ticker)

            if not data:
                continue

            price_now    = data.get('price', 0)
            price_change = ((price_now - price_at) / price_at * 100) if price_at else 0

            # AI 판단이 맞았는지 확인
            ai_correct = 0
            if ai_status == '순항' and price_change >= 0:
                ai_correct = 1
            elif ai_status == '위험' and price_change < 0:
                ai_correct = 1
            elif ai_status == '주의' and abs(price_change) < 3:
                ai_correct = 1

            c.execute('''
                INSERT INTO result_log
                (diagnosis_id, date, ticker, name, ai_status, ai_action,
                 price_at, price_next, price_change, ai_correct, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                diag_id, datetime.now().strftime("%Y-%m-%d"),
                ticker, name, ai_status, ai_action,
                price_at, price_now, round(price_change, 2),
                ai_correct, datetime.now().isoformat()
            ))
            tracked += 1

        conn.commit()
        conn.close()
        if tracked > 0:
            print(f"✅ 결과 추적 완료: {tracked}개")
        return tracked

    def get_accuracy_report(self, days=30):
        """AI 정확도 리포트"""
        conn = sqlite3.connect(self.db_file)
        c    = conn.cursor()

        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        # 전체 정확도
        c.execute('''
            SELECT COUNT(*), SUM(ai_correct)
            FROM result_log
            WHERE date >= ?
        ''', (since,))
        total, correct = c.fetchone()

        if not total or total == 0:
            conn.close()
            return "아직 데이터가 부족해요. 며칠 더 운용 후 확인해주세요."

        accuracy = (correct / total * 100) if total > 0 else 0

        # 상태별 정확도
        c.execute('''
            SELECT ai_status, COUNT(*), SUM(ai_correct)
            FROM result_log
            WHERE date >= ?
            GROUP BY ai_status
        ''', (since,))
        by_status = c.fetchall()

        # 종목별 정확도
        c.execute('''
            SELECT name, COUNT(*), SUM(ai_correct), AVG(price_change)
            FROM result_log
            WHERE date >= ?
            GROUP BY ticker
            ORDER BY SUM(ai_correct) DESC
        ''', (since,))
        by_ticker = c.fetchall()

        # 최근 시장 상황
        c.execute('''
            SELECT regime, COUNT(*) FROM market_log
            WHERE date >= ?
            GROUP BY regime
        ''', (since,))
        regimes = c.fetchall()

        conn.close()

        # 리포트 생성
        msg = f"""📊 <b>AI 정확도 리포트</b> (최근 {days}일)

🎯 <b>전체 정확도: {accuracy:.1f}%</b>
총 {total}회 진단 중 {correct}회 적중

📈 <b>상태별 정확도</b>
"""
        status_emoji = {'순항': '✅', '주의': '⚠️', '위험': '🚨'}
        for status, cnt, cor in by_status:
            acc  = (cor / cnt * 100) if cnt > 0 else 0
            emoji = status_emoji.get(status, '📊')
            msg  += f"  {emoji} {status}: {acc:.0f}% ({cnt}회)\n"

        msg += "\n📋 <b>종목별 적중률</b>\n"
        for name, cnt, cor, avg_change in by_ticker[:5]:
            acc  = (cor / cnt * 100) if cnt > 0 else 0
            msg += f"  • {name}: {acc:.0f}% (평균 {avg_change:+.1f}%)\n"

        if regimes:
            msg += "\n🌍 <b>시장 상황</b>\n"
            for regime, cnt in regimes:
                msg += f"  • {regime}장: {cnt}일\n"

        msg += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return msg

    def get_improved_prompt_context(self):
        """과거 데이터 기반 프롬프트 개선 컨텍스트"""
        conn = sqlite3.connect(self.db_file)
        c    = conn.cursor()

        # 자주 틀린 패턴 찾기
        c.execute('''
            SELECT ai_status, ai_action, COUNT(*),
                   SUM(CASE WHEN ai_correct=0 THEN 1 ELSE 0 END) as wrong
            FROM result_log
            WHERE date >= date('now', '-30 days')
            GROUP BY ai_status, ai_action
            HAVING wrong > 2
            ORDER BY wrong DESC
        ''')
        wrong_patterns = c.fetchall()

        # 잘 맞춘 패턴
        c.execute('''
            SELECT ai_status, ai_action, COUNT(*),
                   SUM(ai_correct) as correct
            FROM result_log
            WHERE date >= date('now', '-30 days')
            GROUP BY ai_status, ai_action
            HAVING correct > 2
            ORDER BY correct DESC
        ''')
        right_patterns = c.fetchall()

        conn.close()

        context = ""
        if wrong_patterns:
            context += "⚠️ 최근 자주 틀린 패턴:\n"
            for status, action, cnt, wrong in wrong_patterns:
                context += f"  - {status}+{action}: {wrong}/{cnt}회 오판\n"

        if right_patterns:
            context += "✅ 최근 잘 맞춘 패턴:\n"
            for status, action, cnt, correct in right_patterns:
                context += f"  - {status}+{action}: {correct}/{cnt}회 적중\n"

        return context if context else ""

if __name__ == "__main__":
    print("=" * 50)
    print("🧠 AI 학습 DB 테스트")
    print("=" * 50)

    al = AILearning()

    # 테스트 진단 저장
    test_diagnosis = """
[NVDA] 상태: ✅순항
이유: AI 수요 지속 증가
판단: 계속보유

[아진산업] 상태: 🚨위험
이유: 자동차 업황 악화
판단: 손절고려

[두산에너빌리티] 상태: ✅순항
이유: 원전 수혜 지속
판단: 계속보유
"""
    test_prices = {
        "NVDA":   174.5,
        "013310": 3345,
        "034020": 115700
    }

    al.save_diagnosis(test_diagnosis, test_prices)

    # 시장 상황 저장
    al.save_market_status("강세", 6343, 42, 18.5)

    # 정확도 리포트
    report = al.get_accuracy_report()
    print(report)

    print("\n✅ AI 학습 DB 완성!")
