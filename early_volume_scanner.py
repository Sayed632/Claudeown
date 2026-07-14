"""
Early Volume Spike Scanner
---------------------------
What this does, in plain English:
Your existing Top Gainers scan catches stocks AFTER they've already
moved (e.g. +15-20% by the time it runs). This scanner runs more
frequently, ONLY during the first hour after market open, and looks
for something different: unusually high VOLUME relative to a stock's
own recent normal volume, even if the price hasn't moved much yet.

Big same-day movers (like the PPAP-style surges you asked about)
often show abnormal volume in their first 15-30 minutes, before the
price has fully caught up. This gets you an earlier heads-up than
waiting for a stock to already be top of the gainers list - it does
NOT predict anything, it just shrinks the detection lag.

HONESTY NOTE: this uses your existing 109-stock main_universe (fixed
list), not the whole NSE market - unlike Top Gainers, which asks NSE
directly for market-wide movers. A true market-wide early-volume
scan would need the same NSE live-analysis endpoint your Top Gainers
scanner uses, filtered differently; this version is deliberately
simpler and cheaper to run every 5 minutes. If you want market-wide
coverage instead of just your fixed list, let Claude know and this
can be rebuilt on top of the NSE endpoint instead of yfinance.
"""

import os
import sys
import json
from datetime import datetime

import requests
import yfinance as yf

# ============================================================
# CONFIG
# ============================================================

MIN_RELATIVE_VOLUME = 3.0   # today's volume-so-far vs. average same-time-of-day volume
MIN_PRICE_MOVE_PCT = 1.0    # ignore near-zero moves even if volume is high (likely noise/data glitch)
MAX_RESULTS = 12
UNIVERSE_FILE = "stock_universe.json"

# ============================================================
# END CONFIG
# ============================================================

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("MY_CHAT_ID")


def send_telegram(message: str) -> bool:
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("ERROR: TELEGRAM_TOKEN or MY_CHAT_ID not set.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        resp = requests.post(
            url,
            data={"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"},
            timeout=20,
        )
        if resp.status_code != 200:
            print(f"Telegram send failed: {resp.status_code} {resp.text}")
            return False
        return True
    except Exception as e:
        print(f"Telegram send exception: {e}")
        return False


def load_universe() -> list:
    try:
        with open(UNIVERSE_FILE) as f:
            data = json.load(f)
        return data.get("main_universe", [])
    except Exception as e:
        print(f"Could not load {UNIVERSE_FILE}: {e}")
        return []


def check_stock(ticker: str):
    """
    Returns a dict with today's relative volume and % move so far, or None
    if data wasn't available / usable for this ticker.
    """
    try:
        tk = yf.Ticker(ticker)
        # 1-minute bars for today, to compute volume-so-far vs. a normal day
        intraday = tk.history(period="1d", interval="1m")
        if intraday is None or len(intraday) < 5:
            return None

        vol_so_far = intraday["Volume"].sum()
        open_price = intraday["Open"].iloc[0]
        last_price = intraday["Close"].iloc[-1]
        if open_price == 0:
            return None
        pct_move = (last_price - open_price) / open_price * 100

        # Average volume over the last 10 sessions, same elapsed-time-of-day
        # (approximated here as: 10-day average daily volume * fraction of
        # the session elapsed so far, since fetching per-minute history for
        # 10 prior days is expensive to run every 5 minutes).
        daily = tk.history(period="15d", interval="1d")
        if daily is None or len(daily) < 5:
            return None
        avg_daily_vol = daily["Volume"].iloc[:-1].mean()  # exclude today (partial)
        if avg_daily_vol == 0 or avg_daily_vol != avg_daily_vol:  # NaN check
            return None

        minutes_elapsed = len(intraday)  # each row ~1 minute
        session_minutes = 375  # NSE session length, 9:15-15:30
        expected_vol_so_far = avg_daily_vol * (minutes_elapsed / session_minutes)
        if expected_vol_so_far == 0:
            return None

        relative_volume = vol_so_far / expected_vol_so_far

        return {
            "ticker": ticker,
            "relative_volume": relative_volume,
            "pct_move": pct_move,
            "last_price": last_price,
        }
    except Exception as e:
        print(f"  {ticker}: error - {e}")
        return None


def run_scan():
    universe = load_universe()
    now_str = datetime.now().strftime("%d-%b-%Y %H:%M")

    if not universe:
        message = (
            f"[EarlyVolume] ⚡ *Early Volume Spike Scan* — {now_str}\n"
            "_From Claudeown repo_\n\n"
            "⚠️ Could not load stock_universe.json - nothing scanned."
        )
        send_telegram(message)
        sys.exit(1)

    print(f"Scanning {len(universe)} stocks for early volume spikes...")
    hits = []
    checked = 0
    for ticker in universe:
        result = check_stock(ticker)
        checked += 1
        if result is None:
            continue
        if (
            result["relative_volume"] >= MIN_RELATIVE_VOLUME
            and abs(result["pct_move"]) >= MIN_PRICE_MOVE_PCT
        ):
            hits.append(result)

    hits.sort(key=lambda x: x["relative_volume"], reverse=True)
    top = hits[:MAX_RESULTS]

    lines = [f"[EarlyVolume] ⚡ *Early Volume Spike Scan* — {now_str}", "_From Claudeown repo_", ""]

    if not top:
        lines.append(f"No unusual early volume detected. Screened: {checked}/{len(universe)} OK.")
    else:
        for h in top:
            direction = "🟢" if h["pct_move"] > 0 else "🔴"
            lines.append(
                f"{direction} *{h['ticker']}* — {h['relative_volume']:.1f}x normal volume, "
                f"{h['pct_move']:+.1f}% so far | ₹{h['last_price']:.2f}"
            )
        lines.append(f"\nScreened: {checked}/{len(universe)} OK.")

    lines.append(
        "\n⚠️ Detects unusual volume EARLY in a potential move - it does not "
        "predict direction or confirm a sustained trend. Verify with your "
        "other scans and news before acting. Fixed 109-stock universe only, "
        "not market-wide. Not financial advice."
    )

    message = "\n".join(lines)
    sent = send_telegram(message)

    if not sent:
        print("Message FAILED to send.")
        sys.exit(1)
    print("Done.")


if __name__ == "__main__":
    run_scan()
