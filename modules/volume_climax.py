import yfinance as yf


class VolumeClimax:
    def _scan_one(self, ticker):
        hist = yf.Ticker(ticker).history(period="2mo").dropna()
        if len(hist) < 25:
            return None
        row = hist.iloc[-1]
        avg20 = hist["Volume"].iloc[-21:-1].mean()
        if avg20 <= 0:
            return None
        vol_ratio = float(row["Volume"] / avg20)
        open_p = float(row["Open"])
        close_p = float(row["Close"])
        high_p = float(row["High"])
        change = ((close_p - open_p) / open_p) * 100 if open_p > 0 else 0
        close_vs_high = (close_p / high_p) * 100 if high_p > 0 else 0
        drop_from_high = ((close_p - high_p) / high_p) * 100 if high_p > 0 else 0

        entry = vol_ratio >= 10 and change >= 5 and close_vs_high >= 85
        exit1 = vol_ratio >= 10 and change <= -3
        exit2 = vol_ratio >= 10 and drop_from_high <= -10
        clear = exit1 or exit2
        if not (entry or clear):
            return None
        return {
            "ticker": ticker,
            "vol_ratio": vol_ratio,
            "change": change,
            "close_vs_high": close_vs_high,
            "drop_from_high": drop_from_high,
            "entry": entry,
            "clear": clear,
        }

    def scan_holdings(self, tickers):
        return [r for r in (self._scan_one(t) for t in tickers) if r]
