"""
Ticker Maintenance (Auto-Update)
-----------------------------------
What this does, in plain English:
1. Applies any KNOWN renames (a manually maintained list - e.g. we already
   know ZOMATO became ETERNAL) automatically to the shared stock list.
2. Tests every ticker in the shared universe with a real data fetch.
3. If a ticker fails 3 days IN A ROW, it's automatically removed from the
   active universe (not guessed-replaced - guessing wrong would silently
   feed bad data into your bots, which is worse than just dropping it).
4. Sends a report so you know exactly what changed and can investigate
   any removed ticker yourself (find its new symbol if it was renamed,
   or confirm it was delisted).

HONESTY NOTE: this does NOT auto-discover what a delisted/renamed ticker's
new symbol is - there's no reliable free data source for that. When you
(or I) learn of a rename, add it to "known_renames" in stock_universe.json
and this script will apply it everywhere automatically going forward.
"""

import os
import sys
import json
from datetime import date

import requests
import yfinance as yf

UNIVERSE_FILE = "stock_universe.json"
FAILURE_LOG_FILE = "ticker_failures.json"
FAILURE_THRESHOLD = 3  # consecutive failed days before auto-removal

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
        return resp.status_code == 200
    except Exception as e:
        print(f"Telegram send exception: {e}")
        return False


def load_universe() -> dict:
    with open(UNIVERSE_FILE) as f:
        return json.load(f)


def save_universe(data: dict):
    with open(UNIVERSE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def load_failures() -> dict:
    if os.path.exists(FAILURE_LOG_FILE):
        try:
            with open(FAILURE_LOG_FILE) as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_failures(data: dict):
    with open(FAILURE_LOG_FILE, "w") as f:
        json.dump(data, f, indent=2)


def apply_known_renames(universe: dict) -> list:
    """Returns list of (old, new) renames actually applied this run."""
    applied = []
    renames = universe.get("known_renames", {})
    for list_key in ("main_universe", "darkhorse_universe"):
        stock_list = universe.get(list_key, [])
        for i, ticker in enumerate(stock_list):
            symbol = ticker.replace(".NS", "")
            if symbol in renames:
                new_symbol = renames[symbol]
                new_ticker = f"{new_symbol}.NS"
                if ticker != new_ticker:
                    stock_list[i] = new_ticker
                    applied.append((symbol, new_symbol))
    return applied


def test_ticker(ticker: str) -> bool:
    """Quick check: can we get any recent data for this ticker?"""
    try:
        df = yf.download(ticker, period="5d", interval="1d", progress=False, auto_adjust=True)
        return df is not None and not df.empty
    except Exception as e:
        print(f"  test failed for {ticker}: {e}")
        return False


def run_maintenance():
    today_str = date.today().isoformat()
    print(f"Running ticker maintenance for {today_str}")

    universe = load_universe()
    failures = load_failures()

    # Step 1: apply any known renames
    renames_applied = apply_known_renames(universe)

    # Step 2: test every unique ticker across both lists
    all_tickers = set(universe.get("main_universe", [])) | set(universe.get("darkhorse_universe", []))
    removed_this_run = []
    still_failing = []

    for ticker in sorted(all_tickers):
        symbol = ticker.replace(".NS", "")
        ok = test_ticker(ticker)

        if ok:
            if symbol in failures:
                del failures[symbol]  # reset on success
            continue

        # Failed today - only count once per day even if this script runs more than once
        record = failures.get(symbol, {"count": 0, "last_fail_date": None})
        if record["last_fail_date"] != today_str:
            record["count"] += 1
            record["last_fail_date"] = today_str
        failures[symbol] = record

        if record["count"] >= FAILURE_THRESHOLD:
            # Remove from both lists
            for list_key in ("main_universe", "darkhorse_universe"):
                universe[list_key] = [t for t in universe.get(list_key, []) if t != ticker]
            universe.setdefault("removed_tickers", {})[symbol] = today_str
            removed_this_run.append(symbol)
            del failures[symbol]
        else:
            still_failing.append((symbol, record["count"]))

    save_universe(universe)
    save_failures(failures)

    # Build report
    lines = [f"[TickerMaintenance] 🔧 *Ticker Auto-Update* — {today_str}", "_From Claudeown repo_", ""]

    if not renames_applied and not removed_this_run and not still_failing:
        lines.append("✅ All tickers healthy - no changes needed.")
    else:
        if renames_applied:
            lines.append("🔁 *Renames applied:*")
            for old, new in renames_applied:
                lines.append(f"   {old} → {new}")
            lines.append("")

        if removed_this_run:
            lines.append(f"🗑️ *Auto-removed (failed {FAILURE_THRESHOLD}+ days in a row):*")
            for symbol in removed_this_run:
                lines.append(f"   {symbol}")
            lines.append("   💡 Investigate these manually - may be delisted, renamed, or suspended.")
            lines.append("")

        if still_failing:
            lines.append(f"⚠️ *Currently failing (not yet at {FAILURE_THRESHOLD}-day threshold):*")
            for symbol, count in still_failing:
                lines.append(f"   {symbol} ({count}/{FAILURE_THRESHOLD} days)")

    message = "\n".join(lines)
    sent = send_telegram(message)

    if not sent:
        print("Message FAILED to send.")
        print(message)
        sys.exit(1)
    print("Done.")


if __name__ == "__main__":
    run_maintenance()
      
