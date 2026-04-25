import requests
import feedparser
from datetime import datetime
import json
import os

class NewsCollector:
    def __init__(self):
        self.rss_feeds = {
            "한국경제": "https://www.hankyung.com/feed/all-news",
            "매일경제": "https://www.mk.co.kr/rss/40300001/",
            "연합뉴스": "https://www.yonhapnewstv.co.kr/category/news/economy/feed/",
            
            
            "CNBC": "https://www.cnbc.com/id/10000664/device/rss/rss.html",
            "MarketWatch": "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines",
            "Bloomberg": "https://feeds.bloomberg.com/markets/news.rss",
            "Investing_com": "https://www.investing.com/rss/news.rss",
            "Yahoo_Finance": "https://finance.yahoo.com/news/rssindex",
        }

    def collect_news(self, max_per_feed=10):
        all_news = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        for source, url in self.rss_feeds.items():
            try:
                res = requests.get(url, headers=headers, timeout=10)
                feed = feedparser.parse(res.content)
                count = 0
                for entry in feed.entries[:max_per_feed]:
                    title = entry.get("title", "").strip()
                    if not title:
                        continue
                    news = {
                        "source": source,
                        "title": title,
                        "summary": entry.get("summary", "")[:200],
                        "published": entry.get("published", ""),
                        "link": entry.get("link", "")
                    }
                    all_news.append(news)
                    count += 1
                print(f"  ✅ {source}: {count}개 수집")
            except Exception as e:
                print(f"  ❌ {source} 실패: {e}")
        return all_news

    def filter_by_importance(self, news_list):
        """AI가 주식 관련 중요 뉴스만 선별 + 중요도 순 정렬"""
        from anthropic import Anthropic
        from dotenv import load_dotenv
        import os, json, re as _re

        load_dotenv('/home/dps/stock_ai/.env')
        client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

        titles_text = ""
        for i, n in enumerate(news_list):
            titles_text += f"{i}. [{n['source']}] {n['title']}\n"

        prompt = f"""주식 트레이더로서 중요도를 평가해주세요.

뉴스 목록:
{titles_text}

중요도 기준:
high: 금리/Fed, 전쟁, 경제지표, 환율급변, 반도체/AI 빅뉴스, 원자재급등락
medium: 기업뉴스, 섹터이슈, 무역, 중앙은행 발언
low: 그외 경제뉴스
제거: 부동산일반, 생활, 연예, 스포츠, 범죄

최소 10개 이상 선별해주세요.
JSON으로만 답변:
{{"selected": [{{"index": 0, "importance": "high", "reason": "이유"}}]}}"""

        try:
            res  = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=800,
                messages=[{"role": "user", "content": prompt}]
            )
            text = res.content[0].text.strip()
            text = _re.sub(r"```json|```", "", text).strip()
            m    = _re.search(r"\{.*\}", text, _re.DOTALL)
            if m:
                data     = json.loads(m.group())
                selected = data.get("selected", [])

                importance_order = {"high": 0, "medium": 1, "low": 2}
                selected.sort(key=lambda x: importance_order.get(x.get("importance", "low"), 3))

                filtered = []
                seen_idx = set()
                for s in selected:
                    idx = s.get("index", -1)
                    if isinstance(idx, int) and 0 <= idx < len(news_list) and idx not in seen_idx:
                        seen_idx.add(idx)
                        item = dict(news_list[idx])
                        item["importance"] = s.get("importance", "low")
                        item["reason"]     = s.get("reason", "")
                        filtered.append(item)

                print(f"  📰 필터링: {len(news_list)}개 → {len(filtered)}개 선별")
                return filtered
        except Exception as e:
            print(f"  ⚠️ 뉴스 필터링 실패: {e}")
        return news_list

    def save_news(self, news_list):
        os.makedirs("data", exist_ok=True)
        today = datetime.now().strftime("%Y%m%d")
        path = f"data/news_{today}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(news_list, f, ensure_ascii=False, indent=2)
        print(f"💾 뉴스 저장: {path} ({len(news_list)}개)")
        return path

if __name__ == "__main__":
    print("📰 뉴스 수집 테스트")
    collector = NewsCollector()
    news = collector.collect_news(max_per_feed=3)
    collector.save_news(news)
    print(f"\n총 {len(news)}개 수집 완료")
    print("\n--- 샘플 뉴스 ---")
    for n in news[:5]:
        print(f"[{n['source']}] {n['title']}")
