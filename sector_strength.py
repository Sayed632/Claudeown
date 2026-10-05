"""
sector_strength.py

Classifies sectors into RRG-style quadrants (LEADING / IMPROVING /
WEAKENING / LAGGING) using REAL NSE sector index tickers - the same
approach your Sectorial-RRG app's own RRG chart uses (established
earlier as more accurate than a stock-composite approximation).

METHODOLOGY (transparent, matches standard RRG quadrant logic):
  1. Build a relative-strength series: sector_index_close / nifty_close,
     normalized so the value ~90 days ago = 100 (a neutral baseline).
  2. rs_now = current value of that series
     rs_20d_ago = its value 20 trading days ago
  3. Quadrant:
       rs_now >= 100 and rs_now >= rs_20d_ago  -> LEADING    (strong, still strengthening)
       rs_now >= 100 and rs_now <  rs_20d_ago  -> WEAKENING  (strong, but fading)
       rs_now <  100 and rs_now <  rs_20d_ago  -> LAGGING    (weak, still weakening)
       rs_now <  100 and rs_now >= rs_20d_ago  -> IMPROVING  (weak, but turning up)
  Verified against synthetic data for all four cases before deployment.

HONEST COVERAGE LIMITATION: only 8 of the 18 Nifty 500 sectors have a
confident, well-established free Yahoo Finance NSE sectoral index
ticker. The other 10 (Capital Goods, Consumer Services, Consumer
Durables, Power, Services, Construction, Construction Materials,
Telecommunication, Textiles, Chemicals) have no solid index proxy
available this way and are treated as UNKNOWN.

Design choice for the "fewer, higher-conviction hits" goal: stocks in
UNKNOWN sectors are EXCLUDED from the sector-strength filter (not
passed through by default) - a real trade-off, since some genuinely
good stocks in unmapped sectors will be filtered out not because
they're weak, but because we can't verify their sector's current
strength. Documented here so it's not a silent/hidden limitation.

Could not live-verify these exact tickers are still valid against
Yahoo Finance from this sandbox (network restricted) - first real run
should be treated as a validation test, same caveat pattern as other
modules in this repo.
"""
import yfinance as yf

SECTOR_INDEX_MAP = {
    "Financial Services": "^NSEBANK",
    "Information Technology": "^CNXIT",
    "Healthcare": "^CNXPHARMA",
    "Automobile and Auto Components": "^CNXAUTO",
    "Fast Moving Consumer Goods": "^CNXFMCG",
    "Metals & Mining": "^CNXMETAL",
    "Realty": "^CNXREALTY",
    "Oil Gas & Consumable Fuels": "^CNXENERGY",
}

NIFTY_BENCHMARK = "^NSEI"
RS_WINDOW_DAYS = 90
MOMENTUM_LOOKBACK_DAYS = 20

_nifty_cache = None  # module-level cache: fetch Nifty benchmark once per run, not once per sector


def _get_nifty_series():
    global _nifty_cache
    if _nifty_cache is not None:
        return _nifty_cache
    try:
        hist = yf.Ticker(NIFTY_BENCHMARK).history(period="6mo", interval="1d")
        if hist is None or len(hist) < RS_WINDOW_DAYS:
            return None
        _nifty_cache = hist["Close"]
        return _nifty_cache
    except Exception as e:
        print(f"Could not fetch Nifty benchmark for sector strength: {e}")
        return None


def get_sector_quadrant(sector_name: str) -> str:
    """Returns 'LEADING', 'IMPROVING', 'WEAKENING', 'LAGGING', or 'UNKNOWN'."""
    index_ticker = SECTOR_INDEX_MAP.get(sector_name)
    if not index_ticker:
        return "UNKNOWN"  # no confident index proxy for this sector

    nifty_series = _get_nifty_series()
    if nifty_series is None:
        return "UNKNOWN"

    try:
        sector_hist = yf.Ticker(index_ticker).history(period="6mo", interval="1d")
        if sector_hist is None or len(sector_hist) < RS_WINDOW_DAYS:
            return "UNKNOWN"
        sector_series = sector_hist["Close"]

        aligned = sector_series.tail(RS_WINDOW_DAYS).reset_index(drop=True) / \
                  nifty_series.tail(RS_WINDOW_DAYS).reset_index(drop=True)
        if len(aligned) < RS_WINDOW_DAYS:
            return "UNKNOWN"

        baseline = aligned.iloc[0]
        if baseline == 0:
            return "UNKNOWN"
        rs_normalized = (aligned / baseline) * 100

        rs_now = rs_normalized.iloc[-1]
        rs_earlier = rs_normalized.iloc[-MOMENTUM_LOOKBACK_DAYS] if len(rs_normalized) >= MOMENTUM_LOOKBACK_DAYS else rs_normalized.iloc[0]

        if rs_now >= 100 and rs_now >= rs_earlier:
            return "LEADING"
        elif rs_now >= 100 and rs_now < rs_earlier:
            return "WEAKENING"
        elif rs_now < 100 and rs_now < rs_earlier:
            return "LAGGING"
        else:
            return "IMPROVING"
    except Exception as e:
        print(f"  Sector strength check failed for {sector_name} ({index_ticker}): {e}")
        return "UNKNOWN"


def build_ticker_to_sector_map(sector_stock_lists: dict) -> dict:
    """Reverse-maps ticker -> sector name, from the {sector: [tickers]} structure."""
    ticker_to_sector = {}
    for sector, tickers in sector_stock_lists.items():
        for ticker in tickers:
            ticker_to_sector[ticker] = sector
    return ticker_to_sector
