"""
Intraday Opening Range Breakout (ORB) Scanner - v2
-----------------------------------------------------
What this does, in plain English:
1. Every ~15 minutes during market hours, checks recent 15-min price bars
   for a 110-stock list (large + mid cap).
2. Computes each stock's "Opening Range" - the high/low of the first
   30 minutes after market open (9:15-9:45 AM IST).
3. A breakout only counts if THREE things line up (not just price crossing
   a line - this reduces false signals):
     a) Price breaks above/below the Opening Range
     b) Price is on the same side of VWAP (volume-weighted average price -
        confirms real intraday bias, not just noise)
     c) The breakout candle has above-average volume and closes in the
        breakout direction (filters out weak/indecisive candles)
4. Won't repeat the same NEW-signal alert twice in one day.
5. PERFORMANCE TRACKING: every signal is logged (entry/stop/target). On
   each run, earlier signals from today are checked against fresh data
   and marked TARGET_HIT, STOP_HIT, or (at day's end) EOD_UNRESOLVED.
   This builds a real track record over time - the foundation for any
   future data-driven tuning (this script does NOT self-tune yet, it
   just keeps the history that tuning would need).

IMPORTANT LIMITATION: free Yahoo Finance intraday data is typically
delayed 15-20 minutes. This is NOT a live tick-by-tick feed.
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

# Universe loads from the shared stock_universe.json (kept in sync with
# scanner.py and ticker_maintenance.py). Falls back to a small safety-net
# list if that file is ever missing or corrupted.
_FALLBACK_UNIVERSE = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "SBIN.NS", "BHARTIARTL.NS", "ITC.NS", "KOTAKBANK.NS",
]


def _load_universe(key: str = "main_universe") -> list:
    try:
        with open("stock_universe.json") as f:
            data = json.load(f)
        stocks = data.get(key, [])
        if stocks:
            return stocks
    except Exception as e:
        print(f"Could not load stock_universe.json ({e}), using fallback list.")
    return _FALLBACK_UNIVERSE


NSE_UNIVERSE = _load_universe("main_universe")

MARKET_OPEN_HOUR = 9
MARKET_OPEN_MIN = 15
OPENING_RANGE_MINUTES = 30      # first 30 min = the "range" to break out of
BREAKOUT_BUFFER_PCT = 0.15      # price must clear the range by this % (reduces noise)
VOLUME_CONFIRM_MULT = 1.3       # breakout bar's volume vs today's average so far
STATE_FILE = "alerted_today.json"
SIGNAL_LOG_FILE = "signal_log.json"
MAX_SIGNALS_TO_SEND = 6
MAX_LOG_SIZE = 2000              # trim old entries beyond this to keep file small

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


def load_signal_log() -> list:
    """Loads the full historical signal log (grows over time)."""
    if os.path.exists(SIGNAL_LOG_FILE):
        try:
            with open(SIGNAL_LOG_FILE) as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_signal_log(log: list):
    if len(log) > MAX_LOG_SIZE:
        log = log[-MAX_LOG_SIZE:]
    with open(SIGNAL_LOG_FILE, "w") as f:
        json.dump(log, f)


def fetch_intraday(ticker: str) -> pd.DataFrame | None:
    """Download recent 15-min bars for one ticker."""
    try:
        df = yf.download(ticker, period="5d", interval="15m", progress=False, auto_adjust=True)
        if df is None or df.empty:
            return None
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC").tz_convert(IST)
        else:
            df.index = df.index.tz_convert(IST)
        return df
    except Exception as e:
        print(f"  fetch failed for {ticker}: {e}")
        return None


def compute_vwap(today_df: pd.DataFrame) -> pd.Series:
    """Volume-weighted average price, cumulative from today's market open."""
    typical_price = (today_df["High"] + today_df["Low"] + today_df["Close"]) / 3
    cum_pv = (typical_price * today_df["Volume"]).cumsum()
    cum_vol = today_df["Volume"].cumsum().replace(0, pd.NA)
    return cum_pv / cum_vol


def check_breakout(ticker: str, df: pd.DataFrame) -> dict | None:
    """
    Compute today's opening range and check for a CONFIRMED breakout:
    price beyond the range + on the correct side of VWAP + volume/candle
    confirmation on the breakout bar. Returns None if any check fails.
    """
    try:
        today = datetime.now(IST).date()
        today_df = df[df.index.date == today]
        if today_df.empty or len(today_df) < 3:
            return None

        open_start = datetime.combine(today, datetime.min.time(), tzinfo=IST).replace(
            hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MIN
        )
        open_end = open_start + pd.Timedelta(minutes=OPENING_RANGE_MINUTES)

        opening_range_df = today_df[(today_df.index >= open_start) & (today_df.index < open_end)]
        if opening_range_df.empty:
            return None

        or_high = float(opening_range_df["High"].max())
        or_low = float(opening_range_df["Low"].min())

        after_range_df = today_df[today_df.index >= open_end]
        if after_range_df.empty or len(after_range_df) < 1:
            return None

        vwap_series = compute_vwap(today_df)
        last_idx = after_range_df.index[-1]
        last = today_df.loc[last_idx]

        price = float(last["Close"])
        open_price = float(last["Open"])
        volume = float(last["Volume"])
        vwap_now = float(vwap_series.loc[last_idx])

        # Volume confirmation: compare breakout bar to today's average bar
        # volume BEFORE this bar (so it's a genuine spike, not baseline).
        prior_bars = today_df[today_df.index < last_idx]
        avg_volume = float(prior_bars["Volume"].mean()) if len(prior_bars) > 0 else volume
        volume_ratio = (volume / avg_volume) if avg_volume > 0 else 1.0
        volume_confirmed = volume_ratio >= VOLUME_CONFIRM_MULT

        candle_bullish = price > open_price
        candle_bearish = price < open_price

        breakout_level = or_high * (1 + BREAKOUT_BUFFER_PCT / 100)
        breakdown_level = or_low * (1 - BREAKOUT_BUFFER_PCT / 100)

        if price > breakout_level and price > vwap_now and volume_confirmed and candle_bullish:
            return {
                "ticker": ticker.replace(".NS", ""),
                "direction": "Bullish Breakout",
                "emoji": "🚀",
                "price": round(price, 2),
                "stop": round(or_low, 2),
                "target": round(price + (or_high - or_low), 2),
                "volume_ratio": round(volume_ratio, 2),
                "entry_time": last_idx.isoformat(),
            }
        elif price < breakdown_level and price < vwap_now and volume_confirmed and candle_bearish:
            return {
                "ticker": ticker.replace(".NS", ""),
                "direction": "Bearish Breakdown",
                "emoji": "🔻",
                "price": round(price, 2),
                "stop": round(or_high, 2),
                "target": round(price - (or_high - or_low), 2),
                "volume_ratio": round(volume_ratio, 2),
                "entry_time": last_idx.isoformat(),
            }
        return None
    except Exception as e:
        print(f"  breakout check failed for {ticker}: {e}")
        return None


def check_open_signal_outcome(signal: dict, df: pd.DataFrame) -> str | None:
    """
    Checks if an OPEN signal has hit its target or stop since it fired,
    using bars after its entry_time. Returns new status or None if still open.
    """
    try:
        entry_time = pd.Timestamp(signal["entry_time"])
        if entry_time.tzinfo is None:
            entry_time = entry_time.tz_localize(IST)
        else:
            entry_time = entry_time.tz_convert(IST)

        bars_since = df[df.index > entry_time]
        if bars_since.empty:
            return None

        is_bullish = signal["direction"] == "Bullish Breakout"
        target = signal["target"]
        stop = signal["stop"]

        if is_bullish:
            hit_target = (bars_since["High"] >= target).any()
            hit_stop = (bars_since["Low"] <= stop).any()
        else:
            hit_target = (bars_since["Low"] <= target).any()
            hit_stop = (bars_since["High"] >= stop).any()

        # If both happened in this batch of bars, we can't know which came
        # first from 15-min bars alone - conservatively report stop first
        # (safer assumption for a beginner-facing tool).
        if hit_stop:
            return "STOP_HIT"
        if hit_target:
            return "TARGET_HIT"
        return None
    except Exception as e:
        print(f"  outcome check failed for {signal.get('ticker')}: {e}")
        return None


def run_scan():
    now = datetime.now(IST)
    today = now.date()
    today_str = today.isoformat()
    print(f"Intraday scan at {now.strftime('%H:%M IST')}")

    state = load_state()
    already_alerted = set(state["alerted"])
    signal_log = load_signal_log()

    # Mark any OPEN signals from a previous day as unresolved (day trades
    # are expected to close same-day; we have no reliable way to know what
    # happened to them intraday on a prior day from today's fetch alone).
    for sig in signal_log:
        if sig.get("status") == "OPEN" and sig.get("date") != today_str:
            sig["status"] = "EOD_UNRESOLVED"

    new_signals = []
    resolved_this_run = []
    failed = []

    # Group today's OPEN signals by ticker for quick lookup
    open_by_ticker = {}
    for sig in signal_log:
        if sig.get("status") == "OPEN" and sig.get("date") == today_str:
            open_by_ticker.setdefault(sig["ticker"], []).append(sig)

    for ticker in NSE_UNIVERSE:
        clean_ticker = ticker.replace(".NS", "")

        # Fetch once per ticker - needed both for potential new breakout
        # AND to check outcomes of any already-open signal for this stock.
        needs_fetch = (clean_ticker not in already_alerted) or (clean_ticker in open_by_ticker)
        if not needs_fetch:
            continue

        df = fetch_intraday(ticker)
        if df is None:
            failed.append(clean_ticker)
            continue

        # Check outcomes of existing open signals for this ticker
        for sig in open_by_ticker.get(clean_ticker, []):
            new_status = check_open_signal_outcome(sig, df)
            if new_status:
                sig["status"] = new_status
                sig["resolved_time"] = now.isoformat()
                resolved_this_run.append((clean_ticker, sig["direction"], new_status))

        # Check for a new breakout (only if not already alerted today)
        if clean_ticker not in already_alerted:
            result = check_breakout(ticker, df)
            if result:
                new_signals.append(result)
                already_alerted.add(clean_ticker)
                signal_log.append({
                    "date": today_str,
                    "ticker": clean_ticker,
                    "direction": result["direction"],
                    "entry_price": result["price"],
                    "stop": result["stop"],
                    "target": result["target"],
                    "entry_time": result["entry_time"],
                    "status": "OPEN",
                })

    state["alerted"] = list(already_alerted)
    save_state(state)
    save_signal_log(signal_log)

    top_signals = new_signals[:MAX_SIGNALS_TO_SEND]
    time_str = now.strftime("%H:%M")

    lines = [f"[Intraday] ⚡ *Intraday ORB Scan* — {time_str} IST", "_From Claudeown repo_", ""]

    if top_signals:
        for s in top_signals:
            lines.append(
                f"{s['emoji']} *{s['ticker']}* — {s['direction']}\n"
                f"   Price: ₹{s['price']} | Stop: ₹{s['stop']} | Target: ₹{s['target']}\n"
                f"   Volume: {s['volume_ratio']}x avg | VWAP + candle confirmed\n"
            )
    else:
        lines.append(f"No new confirmed breakouts this check. ({len(already_alerted)} already alerted today)")

    if resolved_this_run:
        lines.append("\n📋 *Signal outcomes this check:*")
        for ticker, direction, status in resolved_this_run:
            icon = "✅" if status == "TARGET_HIT" else "🛑"
            lines.append(f"   {icon} {ticker} ({direction}) — {status.replace('_', ' ').title()}")

    if failed:
        lines.append(f"\n_Fetch failed: {', '.join(failed[:8])}{'...' if len(failed) > 8 else ''}_")

    lines.append(
        "\n⚠️ Data may be delayed 15-20 min (free feed). Signals now require "
        "VWAP + volume + candle confirmation, not just a price break. Not financial advice."
    )

    message = "\n".join(lines)
    sent = send_telegram(message)

    if not sent:
        print("Message FAILED to send.")
        sys.exit(1)
    print("Done.")


if __name__ == "__main__":
    run_scan()
