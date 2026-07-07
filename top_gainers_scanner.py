"""
Live Top Gainers Scanner
---------------------------
What this does, in plain English:
Unlike your other bots (which only check a fixed list of stocks), this
one asks NSE directly: "across the WHOLE market, what's rising right
now?" This catches stocks outside your fixed lists too.

HONESTY NOTE: NSE's exact JSON field names for this endpoint aren't
something I can verify without actually calling it live, so this parser
is written DEFENSIVELY - it searches for gainer data under several
possible key names, and if NSE's response doesn't match any of them,
it tells you clearly ("couldn't parse the response") instead of
crashing or showing wrong numbers. If that happens on your first run,
send me the raw output and I'll fix the parsing in one pass.
"""

import os
import sys
import time
from datetime import datetime

import requests

try:
    from fii_dii_scanner import SECTOR_MAP  # reuse the same sector/tier map
except Exception:
    SECTOR_MAP = {}

# ============================================================
# CONFIG
# ============================================================

NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

MIN_PCT_CHANGE = 3.0     # only show stocks up at least this much today
MAX_RESULTS = 12

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


def get_nse_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(NSE_HEADERS)
    s.get("https://www.nseindia.com", timeout=15)
    return s


def fetch_gainers_raw(session: requests.Session, retries: int = 2):
    """Returns the raw JSON from NSE's live-analysis-variations endpoint, or None."""
    url = "https://www.nseindia.com/api/live-analysis-variations?index=gainers"
    for attempt in range(retries):
        try:
            r = session.get(url, timeout=15)
            if r.status_code == 200:
                return r.json()
            print(f"Gainers fetch got status {r.status_code}")
        except Exception as e:
            print(f"Gainers fetch failed (attempt {attempt + 1}): {e}")
        time.sleep(2)
    return None


def extract_gainer_list(raw_data) -> list:
    """
    Defensively pulls out a flat list of {symbol, pct_change, ltp} dicts
    from whatever shape NSE's response actually has. Tries several known
    possible structures; returns [] if nothing recognizable is found.
    """
    if not raw_data or not isinstance(raw_data, dict):
        return []

    candidates = []

    def try_extract(entries):
        out = []
        if not isinstance(entries, list):
            return out
        for item in entries:
            if not isinstance(item, dict):
                continue
            symbol = item.get("symbol") or item.get("Symbol")
            pct = (
                item.get("perChange")
                or item.get("pChange")
                or item.get("netPrice")
                or item.get("per_change")
            )
            ltp = item.get("ltp") or item.get("LTP") or item.get("lastPrice")
            if symbol is None or pct is None:
                continue
            try:
                pct_val = float(pct)
            except Exception:
                continue
            out.append({"symbol": str(symbol).strip(), "pct_change": pct_val, "ltp": ltp})
        return out

    # NSE's response is usually segmented by index (NIFTY, allSec, etc).
    # Search every top-level segment for a "data" list we can parse.
    for key, value in raw_data.items():
        if isinstance(value, dict):
            inner_data = value.get("data")
            candidates.extend(try_extract(inner_data))
        elif isinstance(value, list):
            candidates.extend(try_extract(value))

    return candidates


def run_scan():
    print("Fetching live top gainers from NSE...")
    session = get_nse_session()
    raw_data = fetch_gainers_raw(session)

    now_str = datetime.now().strftime("%d-%b-%Y %H:%M")
    lines = [f"[TopGainers] 📈 *Live Top Gainers* — {now_str}", "_From Claudeown repo_", ""]

    if raw_data is None:
        lines.append("⚠️ Could not fetch data from NSE (feed unavailable right now).")
    else:
        gainers = extract_gainer_list(raw_data)
        if not gainers:
            lines.append(
                "⚠️ Got a response from NSE but couldn't parse it into a gainers "
                "list - the format may differ from expected. Send this data to "
                "Claude to fix the parser."
            )
            print("RAW KEYS FOR DEBUGGING:", list(raw_data.keys()) if isinstance(raw_data, dict) else type(raw_data))
        else:
            # Dedupe by symbol (a stock can appear in multiple segments), keep highest % seen
            best_by_symbol = {}
            for g in gainers:
                sym = g["symbol"]
                if sym not in best_by_symbol or g["pct_change"] > best_by_symbol[sym]["pct_change"]:
                    best_by_symbol[sym] = g

            filtered = [g for g in best_by_symbol.values() if g["pct_change"] >= MIN_PCT_CHANGE]
            filtered.sort(key=lambda x: x["pct_change"], reverse=True)
            top = filtered[:MAX_RESULTS]

            if not top:
                lines.append(f"No stocks up {MIN_PCT_CHANGE}%+ right now.")
            else:
                for g in top:
                    sector, tier = SECTOR_MAP.get(g["symbol"], ("Unmapped", "Unknown"))
                    ltp_str = f" | ₹{g['ltp']}" if g["ltp"] else ""
                    lines.append(f"🚀 *{g['symbol']}* +{g['pct_change']:.1f}%{ltp_str} ({sector}, {tier})")

    lines.append(
        "\n⚠️ Live market-wide feed, not limited to your fixed stock lists. "
        "Not financial advice."
    )

    message = "\n".join(lines)
    sent = send_telegram(message)

    if not sent:
        print("Message FAILED to send.")
        sys.exit(1)
    print("Done.")


if __name__ == "__main__":
    run_scan()
          
