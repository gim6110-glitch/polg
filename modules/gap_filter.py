def classify_gap(market: str, gap_pct: float) -> str:
    """
    KR:
      +1~3%  : 진입 유리
      +3~5%  : 주의
      +5%+   : 추격 위험
    US:
      +1~2%  : 진입 유리
      +2~4%  : 주의
      +4%+   : 추격 위험
    """
    m = (market or "").upper()
    if m == "US":
        if gap_pct >= 4:
            return "추격 위험"
        if gap_pct >= 2:
            return "주의"
        if gap_pct >= 1:
            return "진입 유리"
        return "중립"
    # KR default
    if gap_pct >= 5:
        return "추격 위험"
    if gap_pct >= 3:
        return "주의"
    if gap_pct >= 1:
        return "진입 유리"
    return "중립"
