"""
Swing Signal Scanner
---------------------
What this does, in plain English:
1. Downloads recent daily price data for a fixed list of ~60 liquid NSE stocks.
2. Calculates 3 indicators per stock: RSI, Bollinger Bands, ATR.
3. Flags a "BUY setup" when a stock is oversold and near its lower band
   (a pullback in an otherwise okay stock - swing trade style, not intraday).
4. Sends the results to your Telegram bot - ALWAYS sends a message,
   even if there are zero setups today or if data fetch partially fails.
   This fixes the "silence problem" - you will always know the bot ran.

You are NOT expected to understand every line. Focus on the CONFIG section
below - that's the only part you'll usually touch.
"""

import os
import sys
import time
import requests
import pandas as pd
import yfinance as yf

# ============================================================
# CONFIG - the only section you should need to edit
# ============================================================

# Fixed fallback universe: 60 liquid NSE stocks across sectors.
# Using a fixed list (instead of live-scraping Screener.in / NSE site)
# is WHY this bot will not silently die like the old one did -
# there is nothing external to fail here.
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

# Swing strategy thresholds (matches your earlier backtest logic:
# RSI pullback + Bollinger Bands + ATR)
RSI_OVERSOLD = 35          # RSI below this = potential pullback buy
BB_PROXIMITY_PCT = 3.0     # price within this % of lower Bollinger Band
ATR_STOP_MULT = 1.5        # stop-loss = price - 1.5x ATR
ATR_TARGET_MULT = 3.0      # target = price + 3x ATR (2:1 reward:risk)
MAX_SIGNALS_TO_SEND = 8    # don't flood the Telegram message

# ============================================================
# END CONFIG
# ============================================================

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("MY_CHAT_ID")


def send_telegram(message: str):
    """Send a message to your Telegram chat. Never raises - just prints on failure."""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("ERROR: TELEGRAM_TOKEN or MY_CHAT_ID not set in environment.")
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


def fetch_stock_data(ticker: str, retries: int = 2) -> pd.DataFrame | None:
    """Download 6 months of daily data for one ticker. Retries once on failure."""
    for attempt in range(retries):
        try:
            df = yf.download(ticker, period="6mo", interval="1d", progress=False, auto_adjust=True)
            if df is None or df.empty or len(df) < 30:
                return None
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            return df
        except Exception as e:
            print(f"  fetch failed for {ticker} (attempt {attempt + 1}): {e}")
            time.sleep(1)
    return None


def compute_rsi(close: pd.Series, length: int = 14) -> pd.Series:
    """Manual RSI calculation (Wilder's smoothing) - no external TA library needed."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_bbands(close: pd.Series, length: int = 20, std: float = 2.0):
    """Manual Bollinger Bands - returns (lower, upper) series."""
    mid = close.rolling(length).mean()
    std_dev = close.rolling(length).std()
    lower = mid - (std_dev * std)
    upper = mid + (std_dev * std)
    return lower, upper


def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    """Manual ATR calculation (Wilder's smoothing)."""
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()


def analyze_stock(ticker: str, df: pd.DataFrame) -> dict | None:
    """Compute RSI/BB/ATR and check if a swing BUY setup exists."""
    try:
        df["RSI"] = compute_rsi(df["Close"], length=14)
        df["BB_lower"], df["BB_upper"] = compute_bbands(df["Close"], length=20, std=2)
        df["ATR"] = compute_atr(df["High"], df["Low"], df["Close"], length=14)

        last = df.iloc[-1]
        price = float(last["Close"])
        rsi = float(last["RSI"])
        bb_lower = float(last["BB_lower"])
        atr = float(last["ATR"])

        if pd.isna(rsi) or pd.isna(bb_lower) or pd.isna(atr):
            return None

        distance_to_lower_pct = ((price - bb_lower) / price) * 100

        is_oversold = rsi < RSI_OVERSOLD
        is_near_lower_band = 0 <= distance_to_lower_pct <= BB_PROXIMITY_PCT

        if is_oversold and is_near_lower_band:
            stop = price - (ATR_STOP_MULT * atr)
            target = price + (ATR_TARGET_MULT * atr)
            return {
                "ticker": ticker.replace(".NS", ""),
                "price": round(price, 2),
                "rsi": round(rsi, 1),
                "stop": round(stop, 2),
                "target": round(target, 2),
                "score": round(RSI_OVERSOLD - rsi, 2),  # lower RSI = stronger score
            }
        return None
    except Exception as e:
        print(f"  analysis failed for {ticker}: {e}")
        return None


def run_scan():
    print(f"Scanning {len(NSE_UNIVERSE)} stocks...")
    signals = []
    failed = []

    for ticker in NSE_UNIVERSE:
        df = fetch_stock_data(ticker)
        if df is None:
            failed.append(ticker.replace(".NS", ""))
            continue
        result = analyze_stock(ticker, df)
        if result:
            signals.append(result)

    signals.sort(key=lambda x: x["score"], reverse=True)
    top_signals = signals[:MAX_SIGNALS_TO_SEND]

    # Build the message - ALWAYS send something, this is the key fix.
    today = time.strftime("%d-%b-%Y")
    lines = [f"📊 *Swing Scan* — {today}", ""]

    if top_signals:
        lines.append(f"Found {len(signals)} setup(s), showing top {len(top_signals)}:\n")
        for s in top_signals:
            lines.append(
                f"🎯 *{s['ticker']}*\n"
                f"   Price: ₹{s['price']} | RSI: {s['rsi']}\n"
                f"   Stop: ₹{s['stop']} | Target: ₹{s['target']}\n"
            )
    else:
        lines.append("No qualifying swing setups today. Market may be trending, not pulling back.")

    lines.append(f"\n_Scanned: {len(NSE_UNIVERSE) - len(failed)}/{len(NSE_UNIVERSE)} stocks OK._")
    if failed:
        lines.append(f"_Failed to fetch: {', '.join(failed[:10])}{'...' if len(failed) > 10 else ''}_")

    lines.append("\n⚠️ Educational signal tool, not financial advice. Do your own risk management.")

    message = "\n".join(lines)
    sent = send_telegram(message)

    if sent:
        print("Message sent successfully.")
    else:
        print("Message FAILED to send. Check TELEGRAM_TOKEN / MY_CHAT_ID secrets.")
        sys.exit(1)


if __name__ == "__main__":
    run_scan()
