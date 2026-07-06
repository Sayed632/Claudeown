nt """
Dark Horse Screener (Weekly)
-----------------------------
What this does, in plain English:
"Dark horse" is trading slang for a stock quietly building momentum before
most people notice - NOT a magic label, just a name for a specific pattern:
a real price move + rising volume interest + still room to run, in a
mid-cap stock that isn't already one of the most-watched large caps.

This screens for that pattern using 4 measurable criteria (no hype, no
tips, no "insider info" nonsense - just price/volume math):
  1. Meaningful 1-month gain (moving, but not already blown-out/parabolic)
  2. Recent volume clearly above its own recent baseline (rising interest)
  3. RSI between 50-72 (strong momentum, not deeply overbought)
  4. Within 15% of its 52-week high (real strength, not a dead-cat bounce)

Runs once a week (Friday after market close) - this is a slower, more
deliberate screen than the swing/intraday bots, by design.
"""

import os
import sys
import time
from datetime import datetime

import requests
import pandas as pd
import yfinance as yf

# ============================================================
# CONFIG
# ============================================================

# ~50 mid-cap NSE stocks - deliberately NOT the Nifty top-10 mega caps,
# since those are already watched by everyone. Edit this list freely.
MIDCAP_UNIVERSE = [
    "IRCTC.NS", "ZOMATO.NS", "NYKAA.NS", "DIXON.NS", "PERSISTENT.NS",
    "COFORGE.NS", "MPHASIS.NS", "TRENT.NS", "PAGEIND.NS", "RELAXO.NS",
    "VOLTAS.NS", "WHIRLPOOL.NS", "CROMPTON.NS", "POLYCAB.NS", "KEI.NS",
    "APLAPOLLO.NS", "RATNAMANI.NS", "KAJARIACER.NS", "CERA.NS", "ASTRAL.NS",
    "SUPREMEIND.NS", "DEEPAKNTR.NS", "NAVINFLUOR.NS", "GRANULES.NS", "LAURUSLABS.NS",
    "IPCALAB.NS", "SYNGENE.NS", "ABBOTINDIA.NS", "CDSL.NS", "IEX.NS",
    "MCX.NS", "CAMPUS.NS", "VBL.NS", "UBL.NS", "RADICO.NS",
    "JUBLFOOD.NS", "DEVYANI.NS", "KPRMILL.NS", "WELCORP.NS", "HEG.NS",
    "GRAPHITE.NS", "JINDALSTEL.NS", "NMDC.NS", "SAIL.NS", "MOIL.NS",
    "GNFC.NS", "CHAMBLFERT.NS", "COROMANDEL.NS", "PIIND.NS", "RALLIS.NS",
]

MONTH_RETURN_MIN = 8.0      # % - must be up at least this much in ~1 month
MONTH_RETURN_MAX = 40.0     # % - above this, likely already blown out
VOLUME_RATIO_MIN = 1.5      # recent 5-day avg volume vs prior baseline
RSI_MIN = 50.0
RSI_MAX = 72.0
PCT_OF_52W_HIGH_MIN = 0.85  # must be within 15% of its 52-week high
MAX_SIGNALS_TO_SEND = 8

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


def compute_rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def fetch_stock_data(ticker: str, retries: int = 2) -> pd.DataFrame | None:
    """Download 1 year of daily data - needed for 52-week high + 1-month return."""
    for attempt in range(retries):
        try:
            df = yf.download(ticker, period="1y", interval="1d", progress=False, auto_adjust=True)
            if df is None or df.empty or len(df) < 60:
                return None
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            return df
        except Exception as e:
            print(f"  fetch failed for {ticker} (attempt {attempt + 1}): {e}")
            time.sleep(1)
    return None


def analyze_stock(ticker: str, df: pd.DataFrame) -> dict | None:
    try:
        if len(df) < 65:
            return None

        close = df["Close"]
        volume = df["Volume"]

        price = float(close.iloc[-1])
        price_1mo_ago = float(close.iloc[-22])  # ~21 trading days = 1 month
        month_return_pct = ((price - price_1mo_ago) / price_1mo_ago) * 100

        recent_vol_avg = float(volume.iloc[-5:].mean())
        baseline_vol_avg = float(volume.iloc[-65:-5].mean())
        if baseline_vol_avg <= 0:
            return None
        volume_ratio = recent_vol_avg / baseline_vol_avg

        rsi_series = compute_rsi(close, length=14)
        rsi = float(rsi_series.iloc[-1])

        fifty_two_week_high = float(close.iloc[-252:].max()) if len(close) >= 252 else float(close.max())
        pct_of_high = price / fifty_two_week_high

        if pd.isna(rsi) or pd.isna(month_return_pct) or pd.isna(volume_ratio):
            return None

        meets_criteria = (
            MONTH_RETURN_MIN <= month_return_pct <= MONTH_RETURN_MAX
            and volume_ratio >= VOLUME_RATIO_MIN
            and RSI_MIN <= rsi <= RSI_MAX
            and pct_of_high >= PCT_OF_52W_HIGH_MIN
        )

        if meets_criteria:
            score = month_return_pct * volume_ratio  # simple combined ranking score
            return {
                "ticker": ticker.replace(".NS", ""),
                "price": round(price, 2),
                "month_return": round(month_return_pct, 1),
                "volume_ratio": round(volume_ratio, 2),
                "rsi": round(rsi, 1),
                "pct_of_high": round(pct_of_high * 100, 1),
                "score": round(score, 2),
            }
        return None
    except Exception as e:
        print(f"  analysis failed for {ticker}: {e}")
        return None


def run_scan():
    print(f"Screening {len(MIDCAP_UNIVERSE)} mid-cap stocks for dark horse setups...")
    candidates = []
    failed = []

    for ticker in MIDCAP_UNIVERSE:
        df = fetch_stock_data(ticker)
        if df is None:
            failed.append(ticker.replace(".NS", ""))
            continue
        result = analyze_stock(ticker, df)
        if result:
            candidates.append(result)

    candidates.sort(key=lambda x: x["score"], reverse=True)
    top = candidates[:MAX_SIGNALS_TO_SEND]

    today = datetime.now().strftime("%d-%b-%Y")
    lines = [f"🐴 *Dark Horse Screen* — {today}", ""]

    if top:
        lines.append(f"Found {len(candidates)} candidate(s), showing top {len(top)}:\n")
        for s in top:
            lines.append(
                f"🎯 *{s['ticker']}*\n"
                f"   Price: ₹{s['price']} | 1mo: +{s['month_return']}%\n"
                f"   Vol vs baseline: {s['volume_ratio']}x | RSI: {s['rsi']}\n"
                f"   {s['pct_of_high']}% of 52wk high\n"
            )
    else:
        lines.append("No candidates met all criteria this week.")

    lines.append(f"\n_Screened: {len(MIDCAP_UNIVERSE) - len(failed)}/{len(MIDCAP_UNIVERSE)} OK._")
    if failed:
        lines.append(f"_Failed: {', '.join(failed[:8])}{'...' if len(failed) > 8 else ''}_")

    lines.append(
        "\n⚠️ This is a systematic price/volume screen, not a tip or "
        "recommendation. Mid-caps carry higher risk than large caps - "
        "verify fundamentals yourself before acting. Not financial advice."
    )

    message = "\n".join(lines)
    sent = send_telegram(message)

    if not sent:
        print("Message FAILED to send.")
        sys.exit(1)
    print("Done.")


if __name__ == "__main__":
    run_scan()
