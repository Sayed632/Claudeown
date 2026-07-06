"""
Intraday Opening Range Breakout (ORB) Scanner
-----------------------------------------------
What this does, in plain English:
1. Every ~15 minutes during market hours, checks recent 15-min price bars
   for the same 60-stock list used by the swing scanner.
2. Computes each stock's "Opening Range" - the high/low of the first
   30 minutes after market open (9:15-9:45 AM IST).
3. If the current price breaks above the Opening Range high -> Bullish
   breakout signal. Breaks below the low -> Bearish breakdown signal.
4. Won't repeat the same alert twice in one day (tracked in alerted_today.json).
5. Sends a short status message each run either way, so you know it's alive.

IMPORTANT LIMITATION: free Yahoo Finance intraday data is typically
delayed 15-20 minutes. This is NOT a live tick-by-tick feed. Treat signals
as "recently happened," not "happening right now."
"""

import os
import sys
import json
import time
from datetime import datetime, date
from zoneinfo import ZoneInfo

import requests
import pandas as pd
import yfinance as yf

# ============================================================
# CONFIG
# ============================================================

NSE_UNIVERSE = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "SBIN.NS", "BHARTIARTL.NS", "ITC.NS", "KOTAKBANK.NS",
    "LT.NS", "AXISBANK.NS", "BAJFINANCE.NS", "MARUTI.NS", "TITAN.NS",
    "SUNPHARMA.NS", "TATAMOTORS.NS", "M&M.NS", "ULTRACEMCO.NS", "NTPC.NS",
    "POWERGRID.NS", "ADANIENT.NS", "TATASTEEL.NS", "HCLTECH.NS", "WIPRO.NS",
    "BAJAJFINSV.NS", "ASIANPAINT.NS", "NESTLEIND.NS", "JSWSTEEL.NS", "COALINDIA.NS",
    "DRREDDY.NS", "GRASIM.NS", "EICHERMOT.NS", "HEROMOTOCO.NS", "BAJAJ-AUTO.NS",
    "TATACONSUM.NS", "BRITANNIA.NS", "DIVISLAB.NS", "APOLLOHOSP.NS", "CIPLA.NS",
    "SBILIFE.NS", "HDFCLIFE.NS", "INDUSINDBK.NS", "TECHM.NS", "ADANIPORTS.NS",
    "ONGC.NS", "BPCL.NS", "IOC.NS", "HINDALCO.NS", "VEDL.NS",
    "PIDILITIND.NS", "DABUR.NS", "GODREJCP.NS", "SIEMENS.NS", "ABB.NS",
    "BOSCHLTD.NS", "MOTHERSON.NS", "TVSMOTOR.NS", "ASHOKLEY.NS", "BALKRISIND.NS",
]

MARKET_OPEN_HOUR = 9
MARKET_OPEN_MIN = 15
OPENING_RANGE_MINUTES = 30      # first 30 min = the "range" to break out of
BREAKOUT_BUFFER_PCT = 0.15      # price must clear the range by this % (reduces noise)
STATE_FILE = "alerted_today.json"
MAX_SIGNALS_TO_SEND = 6

IST = ZoneInfo("Asia/Kolkata")

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


def load_state() -> dict:
    """Load today's already-alerted tickers. Resets automatically on a new day."""
    today_str = date.today().isoformat()
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                data = json.load(f)
            if data.get("date") == today_str:
                return data
        except Exception:
            pass
    return {"date": today_str, "alerted": []}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def fetch_intraday(ticker: str) -> pd.DataFrame | None:
    """Download recent 15-min bars for one ticker."""
    try:
        df = yf.download(ticker, period="5d", interval="15m", progress=False, auto_adjust=True)
        if df is None or df.empty:
            return None
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        # Convert to IST so we can filter "today" and "opening range" correctly
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC").tz_convert(IST)
        else:
            df.index = df.index.tz_convert(IST)
        return df
    except Exception as e:
        print(f"  fetch failed for {ticker}: {e}")
        return None


def check_breakout(ticker: str, df: pd.DataFrame) -> dict | None:
    """Compute today's opening range and check if the latest bar broke out of it."""
    try:
        today = datetime.now(IST).date()
        today_df = df[df.index.date == today]
        if today_df.empty or len(today_df) < 2:
            return None

        open_start = datetime.combine(today, datetime.min.time(), tzinfo=IST).replace(
            hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MIN
        )
        open_end = open_start + pd.Timedelta(minutes=OPENING_RANGE_MINUTES)

        opening_range_df = today_df[(today_df.index >= open_start) & (today_df.index < open_end)]
        if opening_range_df.empty:
            return None  # opening range not formed yet

        or_high = float(opening_range_df["High"].max())
        or_low = float(opening_range_df["Low"].min())

        after_range_df = today_df[today_df.index >= open_end]
        if after_range_df.empty:
            return None  # still within the opening range window

        last = after_range_df.iloc[-1]
        price = float(last["Close"])

        breakout_level = or_high * (1 + BREAKOUT_BUFFER_PCT / 100)
        breakdown_level = or_low * (1 - BREAKOUT_BUFFER_PCT / 100)

        if price > breakout_level:
            return {
                "ticker": ticker.replace(".NS", ""),
                "direction": "Bullish Breakout",
                "emoji": "🚀",
                "price": round(price, 2),
                "or_high": round(or_high, 2),
                "or_low": round(or_low, 2),
                "stop": round(or_low, 2),
                "target": round(price + (or_high - or_low), 2),
            }
        elif price < breakdown_level:
            return {
                "ticker": ticker.replace(".NS", ""),
                "direction": "Bearish Breakdown",
                "emoji": "🔻",
                "price": round(price, 2),
                "or_high": round(or_high, 2),
                "or_low": round(or_low, 2),
                "stop": round(or_high, 2),
                "target": round(price - (or_high - or_low), 2),
            }
        return None
    except Exception as e:
        print(f"  breakout check failed for {ticker}: {e}")
        return None


def run_scan():
    now = datetime.now(IST)
    print(f"Intraday scan at {now.strftime('%H:%M IST')}")

    state = load_state()
    already_alerted = set(state["alerted"])

    new_signals = []
    failed = []

    for ticker in NSE_UNIVERSE:
        clean_ticker = ticker.replace(".NS", "")
        if clean_ticker in already_alerted:
            continue  # don't re-alert the same stock today

        df = fetch_intraday(ticker)
        if df is None:
            failed.append(clean_ticker)
            continue

        result = check_breakout(ticker, df)
        if result:
            new_signals.append(result)
            already_alerted.add(clean_ticker)

    state["alerted"] = list(already_alerted)
    save_state(state)

    top_signals = new_signals[:MAX_SIGNALS_TO_SEND]
    time_str = now.strftime("%H:%M")

    lines = [f"⚡ *Intraday ORB Scan* — {time_str} IST", ""]

    if top_signals:
        for s in top_signals:
            lines.append(
                f"{s['emoji']} *{s['ticker']}* — {s['direction']}\n"
                f"   Price: ₹{s['price']} | Stop: ₹{s['stop']} | Target: ₹{s['target']}\n"
            )
    else:
        lines.append(f"No new breakouts this check. ({len(already_alerted)} already alerted today)")

    if failed:
        lines.append(f"\n_Fetch failed: {', '.join(failed[:8])}{'...' if len(failed) > 8 else ''}_")

    lines.append(
        "\n⚠️ Data may be delayed 15-20 min (free feed). Not financial advice."
    )

    message = "\n".join(lines)
    sent = send_telegram(message)

    if not sent:
        print("Message FAILED to send.")
        sys.exit(1)
    print("Done.")


if __name__ == "__main__":
    run_scan()
