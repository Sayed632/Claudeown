"""
Self-Troubleshooter / Daily Health Check
-------------------------------------------
What this does, in plain English:
Runs before market open each day and checks the 3 things that make your
other 4 bots work: yfinance (data), NSE's website (for FII/DII + Top
Gainers), and Telegram (delivery). If everything's fine, you get a short
"all clear" message. If something's broken, you get a specific diagnosis
and a concrete fix - not just "something failed."

IMPORTANT HONESTY NOTE: this script does NOT rewrite your other bots'
code automatically. Safely auto-patching code with no human review is
how bots silently break in worse ways. What it DOES do:
  - Retries with a fresh connection for known transient glitches
  - Tells you clearly and specifically what's wrong and how to fix it,
    so you stay in control of any actual code changes.
"""

import os
import sys
import time
from datetime import datetime

import requests
import pandas as pd
import yfinance as yf

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("MY_CHAT_ID")

NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Referer": "https://www.nseindia.com/",
}

TEST_TICKER = "RELIANCE.NS"  # a stock that should always have data


def send_telegram_raw(token: str, chat_id: str, message: str) -> tuple:
    """Returns (success: bool, detail: str) - doesn't raise."""
    if not token or not chat_id:
        return False, "TELEGRAM_TOKEN or MY_CHAT_ID not set as secrets."
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(
            url, data={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=20
        )
        if resp.status_code == 200:
            return True, "OK"
        return False, f"HTTP {resp.status_code}: {resp.text[:150]}"
    except Exception as e:
        return False, f"Exception: {e}"


def check_telegram_token() -> tuple:
    """Checks the bot token is valid, WITHOUT sending a message (uses getMe)."""
    if not TELEGRAM_TOKEN:
        return False, "TELEGRAM_TOKEN secret is missing.", "Add it under repo Settings -> Secrets and variables -> Actions."
    try:
        r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getMe", timeout=15)
        if r.status_code == 200 and r.json().get("ok"):
            return True, "Bot token is valid.", ""
        return False, f"Telegram rejected the token (HTTP {r.status_code}).", "Your bot token may have been revoked. Generate a new one via @BotFather and update the TELEGRAM_TOKEN secret."
    except Exception as e:
        return False, f"Could not reach Telegram API: {e}", "This may be a temporary network issue - check again shortly."


def check_telegram_chat() -> tuple:
    """Checks the bot can see the target chat."""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return False, "TELEGRAM_TOKEN or MY_CHAT_ID missing.", "Add both as repo secrets."
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getChat",
            params={"chat_id": CHAT_ID}, timeout=15,
        )
        if r.status_code == 200 and r.json().get("ok"):
            return True, "Chat ID is valid and reachable.", ""
        return False, f"Telegram couldn't find/access this chat (HTTP {r.status_code}).", "Double-check MY_CHAT_ID is correct, and that the bot is still a member/admin of that chat."
    except Exception as e:
        return False, f"Could not verify chat: {e}", "Temporary network issue - check again shortly."


def check_yfinance() -> tuple:
    """
    Fetches a known-reliable stock and checks the data shape is what our
    bots expect. This is the main defense against 'yfinance changed its
    output format' silently breaking everything downstream.
    """
    for attempt in range(2):
        try:
            df = yf.download(TEST_TICKER, period="5d", interval="1d", progress=False, auto_adjust=True)
            if df is None or df.empty:
                if attempt == 0:
                    time.sleep(2)
                    continue
                return False, "yfinance returned no data for a stock that should always have data.", "Could be a temporary Yahoo Finance outage, or yfinance's library needs updating. Try: pip install --upgrade yfinance in requirements.txt."

            # Self-heal attempt: yfinance sometimes returns MultiIndex columns.
            columns = df.columns
            if isinstance(columns, pd.MultiIndex):
                df.columns = [c[0] if isinstance(c, tuple) else c for c in columns]

            required = {"Open", "High", "Low", "Close", "Volume"}
            missing = required - set(df.columns)
            if missing:
                return False, f"yfinance's column layout changed - missing: {missing}. Got columns: {list(df.columns)}", "yfinance likely updated its output format. Send this exact message to Claude - the fix is a small code update to column handling."

            if len(df) < 3:
                return False, f"Got data but only {len(df)} rows - expected at least 3.", "May be a market holiday period or a data gap. Not urgent unless it persists."

            return True, f"yfinance OK - fetched {len(df)} rows with correct columns.", ""
        except Exception as e:
            if attempt == 0:
                time.sleep(2)
                continue
            return False, f"yfinance raised an exception: {e}", "Could be a temporary network/library issue. If this repeats daily, the yfinance library may need an update - send this error to Claude."
    return False, "Unexpected failure path.", "Send this to Claude for review."


def check_nse_access() -> tuple:
    """Checks whether NSE's website is reachable and returning valid session cookies."""
    try:
        s = requests.Session()
        s.headers.update(NSE_HEADERS)
        r = s.get("https://www.nseindia.com", timeout=15)
        if r.status_code != 200:
            return False, f"NSE homepage returned HTTP {r.status_code}.", "NSE may be blocking automated access today. This affects the FII/DII and Top Gainers bots only - often resolves on its own within a day or two."

        # Try a lightweight authenticated endpoint
        r2 = s.get("https://www.nseindia.com/api/fiidiiTradeReact", timeout=15)
        if r2.status_code == 200:
            return True, "NSE session + data endpoint both working.", ""
        return False, f"NSE homepage OK but data endpoint returned HTTP {r2.status_code}.", "NSE may have changed its API or added stricter bot detection. This affects FII/DII and Top Gainers bots. Not urgent for Swing/Intraday bots (those use yfinance, not NSE directly)."
    except Exception as e:
        return False, f"Could not reach NSE at all: {e}", "Check the network settings, or NSE may be temporarily down."


def run_health_check():
    today_str = datetime.now().strftime("%d-%b-%Y %H:%M")
    print(f"Running self-check at {today_str}")

    results = []

    ok, detail, fix = check_yfinance()
    results.append(("yfinance (Swing/Intraday/DarkHorse data)", ok, detail, fix))

    ok, detail, fix = check_nse_access()
    results.append(("NSE access (FII/DII + Top Gainers)", ok, detail, fix))

    ok, detail, fix = check_telegram_token()
    results.append(("Telegram bot token", ok, detail, fix))

    ok, detail, fix = check_telegram_chat()
    results.append(("Telegram chat delivery", ok, detail, fix))

    all_ok = all(r[1] for r in results)

    lines = [f"[HealthCheck] 🩺 *System Self-Check* — {today_str}", "_From Claudeown repo_", ""]

    if all_ok:
        lines.append("✅ Self-troubleshooting complete — everything works fine.")
        lines.append("")
        for name, ok, detail, fix in results:
            lines.append(f"✅ {name}: {detail}")
    else:
        lines.append("⚠️ Self-troubleshooting found issues:\n")
        for name, ok, detail, fix in results:
            icon = "✅" if ok else "❌"
            lines.append(f"{icon} *{name}*")
            lines.append(f"   {detail}")
            if not ok and fix:
                lines.append(f"   💡 Fix: {fix}")
            lines.append("")

    message = "\n".join(lines)

    # Use raw send here (not the checked token) since we've already validated
    # what we can - if Telegram itself is fully down, this print at least
    # shows in the Actions log.
    sent, send_detail = send_telegram_raw(TELEGRAM_TOKEN, CHAT_ID, message)
    print(message)
    if not sent:
        print(f"\nCould not deliver health report to Telegram either: {send_detail}")
        print("Check TELEGRAM_TOKEN / MY_CHAT_ID secrets directly in GitHub repo settings.")
        sys.exit(1)

    print("\nHealth check delivered.")


if __name__ == "__main__":
    run_health_check()
  
