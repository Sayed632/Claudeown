"""
Steady Climber Scanner
-----------------------
The mirror image of the Penny Stock scanner: instead of flagging
surge + red flags (caution), this flags SMOOTH, CONFIRMED uptrends +
quality signals - stocks like OFSS (steady climber, not a volatile
spike) rather than ATVO (speculative pivot story).

METHODOLOGY (deliberately transparent, not a black box):

1. TREND QUALITY (the key differentiator from a volatile stock that
   happens to be up): fit a straight line to the trailing 90-day LOG
   price and measure R² (how well price actually follows that line).
   A smooth, staircase-like climb scores high; a stock that spikes and
   craters back up scores lower even with the same net gain. Verified
   against synthetic cases before deployment: a smooth climb scored
   R²=0.998, a volatile stock with the SAME total gain scored R²=0.759.

2. TREND CONFIRMATION (standard technical filters):
   - Price above both 50-day and 200-day SMA
   - 50-day SMA above 200-day SMA ("golden cross" alignment)
   - Within WITHIN_52W_HIGH_PCT of its 52-week high (persistent
     strength, not a past spike that's since faded)

3. RELATIVE STRENGTH: trailing 90-day return must beat the Nifty 50's
   return over the same window - rewards genuine outperformance, not
   just "the whole market went up."

ALL FOUR conditions must be met (R² threshold, SMA alignment, near
52-week high, beats Nifty) - deliberately strict, matching the
"caution tool" philosophy of Penny Stock scanner but inverted for
quality instead of red flags.

Passing candidates get the SAME enrichment as Penny Stock/Top Gainers/
Early Volume (business summary, book value, contract news, delivery %,
transparent scorecard) - reuses stock_enrichment.py, once per ticker
per day via its own cache file.

HONEST CAVEATS:
  - Trend-following, not predictive - a smooth uptrend can still
    reverse tomorrow. This finds "has been climbing steadily," not
    "will keep climbing."
  - Uses the full Nifty 500 list (493 stocks, same mapping as Sector
    Breadth/Treemap), not the smaller curated 109-stock main_universe -
    the original example that prompted this feature (OFSS) isn't in
    the curated list, so this needed the broader universe to be useful.
    Expect a slower run (~9-16 min, similar to Penny Stock scanner)
    since it's checking 493 stocks instead of 109.
  - R² and SMA thresholds below are configurable and somewhat
    arbitrary judgment calls, documented here for transparency -
    tune them if they're too strict/loose after seeing real results.
"""
import os
import json
from datetime import datetime, timezone, timedelta

import numpy as np
import requests
import yfinance as yf

from stock_enrichment import load_cache, save_cache, already_enriched_today, enrich_stock

IST = timezone(timedelta(hours=5, minutes=30))

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("MY_CHAT_ID")

UNIVERSE_FILE = "sector_stock_lists.json"
ENRICHMENT_CACHE_FILE = "enrichment_cache_steadyclimber.json"
BENCHMARK = "^NSEI"  # Nifty 50

TREND_WINDOW_DAYS = 90     # trailing window for the R² regression + relative strength
MIN_R_SQUARED = 0.70       # minimum "smoothness" to qualify - documented judgment call
WITHIN_52W_HIGH_PCT = 15.0 # must be within this % of its 52-week high
MAX_RESULTS = 10


def send_telegram(message: str) -> bool:
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("ERROR: TELEGRAM_TOKEN or MY_CHAT_ID not set.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        resp = requests.post(
            url, data={"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}, timeout=20
        )
        if resp.status_code != 200:
            print(f"Telegram send failed: {resp.status_code} {resp.text}")
            return False
        return True
    except Exception as e:
        print(f"Telegram send exception: {e}")
        return False


def load_universe() -> list:
    """sector_stock_lists.json is {sector_name: [tickers]} - flatten it."""
    try:
        with open(UNIVERSE_FILE) as f:
            data = json.load(f)
        all_stocks = [ticker for sector_tickers in data.values() for ticker in sector_tickers]
        return list(dict.fromkeys(all_stocks))  # dedupe, preserve order
    except Exception as e:
        print(f"Could not load {UNIVERSE_FILE}: {e}")
        return []


def trend_quality(prices: np.ndarray):
    """Returns (r_squared, slope) for a linear fit to log(prices)."""
    log_prices = np.log(prices)
    x = np.arange(len(log_prices))
    slope, intercept = np.polyfit(x, log_prices, 1)
    fitted = slope * x + intercept
    ss_res = np.sum((log_prices - fitted) ** 2)
    ss_tot = np.sum((log_prices - np.mean(log_prices)) ** 2)
    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
    return r_squared, slope


def get_nifty_return(window_days: int) -> float:
    try:
        hist = yf.Ticker(BENCHMARK).history(period="1y", interval="1d")
        if hist is None or len(hist) < window_days:
            return 0.0
        closes = hist["Close"].values[-window_days:]
        return (closes[-1] - closes[0]) / closes[0] * 100
    except Exception as e:
        print(f"Could not fetch Nifty benchmark: {e}")
        return 0.0


def check_stock(ticker: str, nifty_return: float):
    try:
        hist = yf.Ticker(ticker).history(period="1y", interval="1d")
        if hist is None or len(hist) < 200:
            return None  # need enough history for SMA200

        closes = hist["Close"].values
        current_price = closes[-1]
        sma50 = closes[-50:].mean()
        sma200 = closes[-200:].mean()
        fifty_two_week_high = closes[-252:].max() if len(closes) >= 252 else closes.max()
        pct_below_high = (fifty_two_week_high - current_price) / fifty_two_week_high * 100

        trend_window = closes[-TREND_WINDOW_DAYS:]
        r_squared, slope = trend_quality(trend_window)
        stock_return = (trend_window[-1] - trend_window[0]) / trend_window[0] * 100
        relative_strength = stock_return - nifty_return

        passes = (
            current_price > sma50 > sma200
            and slope > 0
            and r_squared >= MIN_R_SQUARED
            and pct_below_high <= WITHIN_52W_HIGH_PCT
            and relative_strength > 0
        )

        if not passes:
            return None

        return {
            "ticker": ticker,
            "price": current_price,
            "r_squared": r_squared,
            "trend_return_pct": stock_return,
            "relative_strength": relative_strength,
            "pct_below_52w_high": pct_below_high,
        }
    except Exception as e:
        print(f"  {ticker}: error - {e}")
        return None


def run_scanner():
    now_str = datetime.now(IST).strftime("%d-%b-%Y %H:%M")
    universe = load_universe()

    if not universe:
        send_telegram(
            f"[SteadyClimber] ⚠️ *Steady Climber Scan* — {now_str}\n"
            "_From Claudeown repo_\n\nCould not load stock universe."
        )
        return

    print(f"Fetching Nifty 50 benchmark return over trailing {TREND_WINDOW_DAYS} days...")
    nifty_return = get_nifty_return(TREND_WINDOW_DAYS)
    print(f"Nifty 50 trailing return: {nifty_return:+.1f}%")

    print(f"Screening {len(universe)} stocks for steady, confirmed uptrends...")
    hits = []
    for i, ticker in enumerate(universe):
        result = check_stock(ticker, nifty_return)
        if result:
            hits.append(result)
        if (i + 1) % 30 == 0:
            print(f"  ...{i + 1}/{len(universe)} checked, {len(hits)} qualifying so far")

    hits.sort(key=lambda x: x["relative_strength"], reverse=True)
    top = hits[:MAX_RESULTS]

    lines = [f"[SteadyClimber] 📈 *Steady Climber Scan* — {now_str}", "_From Claudeown repo_", ""]
    lines.append(
        f"_Criteria: price > SMA50 > SMA200, trend R\u00b2 \u2265 {MIN_R_SQUARED} over "
        f"{TREND_WINDOW_DAYS}d (smooth, not choppy), within {WITHIN_52W_HIGH_PCT:.0f}% of "
        f"52-week high, beating Nifty 50 ({nifty_return:+.1f}% over same window)._\n"
    )

    if not top:
        lines.append(f"No stocks in your {len(universe)}-stock universe met all criteria today.")
    else:
        for h in top:
            lines.append(
                f"📈 *{h['ticker'].replace('.NS', '')}* — {h['trend_return_pct']:+.1f}% "
                f"({TREND_WINDOW_DAYS}d) | vs Nifty: {h['relative_strength']:+.1f}% | "
                f"R\u00b2: {h['r_squared']:.2f} | ₹{h['price']:.2f}\n"
                f"   {h['pct_below_52w_high']:.1f}% below 52w high"
            )

    lines.append(
        "\n⚠️ Trend-following, not predictive - a steady uptrend can still reverse. "
        "This finds stocks that HAVE BEEN climbing smoothly, not a guarantee they "
        "keep climbing. Not financial advice."
    )

    message = "\n".join(lines)
    send_telegram(message)

    # Enrichment: once per ticker per day
    if top:
        cache = load_cache(ENRICHMENT_CACHE_FILE)
        for h in top:
            if already_enriched_today(h["ticker"], cache):
                print(f"  {h['ticker']}: already enriched today, skipping")
                continue
            print(f"  Enriching {h['ticker']}...")
            enrichment_text = enrich_stock(h["ticker"], has_red_flags=False)
            send_telegram(f"[SteadyClimber]{enrichment_text}")
            cache[h["ticker"]] = {"date": datetime.now(IST).strftime("%Y-%m-%d")}
        save_cache(ENRICHMENT_CACHE_FILE, cache)

    print("Done.")


if __name__ == "__main__":
    run_scanner()
