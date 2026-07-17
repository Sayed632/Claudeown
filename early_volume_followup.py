"""
Early Volume Follow-Up Checker
-------------------------------
Reads every pending alert file written by early_volume_scanner.py,
checks the ones that are old enough (>= MIN_FOLLOWUP_MINUTES since the
original alert), fetches the current price, and reports whether the
move HELD, REVERSED, or went FLAT since the original volume-spike alert.

This exists because "high volume" alone doesn't tell you which way a
stock will actually go - see the COHANCE example from 17-Jul-2026: it
was flagged +2.3% bullish, then reversed to -1.48% by market close.
This closes that gap by actually checking back, building an honest
track record instead of a one-shot alert with no follow-through.

Run via workflow_dispatch, triggered externally by cron-job.org every
~10 min from ~9:50 AM to 11:15 AM IST - by the time this runs, alerts
from earlier in the 9:15-10:15 window will have had time to develop.
"""
import os
import glob
import json
from datetime import datetime, timedelta

import requests
import yfinance as yf

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("MY_CHAT_ID")

MIN_FOLLOWUP_MINUTES = 30
PENDING_DIR = "alerts/pending"
PROCESSED_DIR = "alerts/processed"


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


def get_current_price(ticker: str):
    try:
        hist = yf.Ticker(ticker).history(period="1d", interval="1m")
        if hist is None or len(hist) == 0:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception as e:
        print(f"  {ticker}: price fetch error - {e}")
        return None


def classify_outcome(alert_pct_move: float, change_since_alert_pct: float) -> str:
    """
    alert_pct_move: the direction it was moving WHEN flagged (+/-)
    change_since_alert_pct: how much price has moved since the alert price
    """
    was_bullish = alert_pct_move > 0
    still_moving_same_way = (change_since_alert_pct > 0.5) if was_bullish else (change_since_alert_pct < -0.5)
    reversed_hard = (change_since_alert_pct < -1.0) if was_bullish else (change_since_alert_pct > 1.0)

    if reversed_hard:
        return "REVERSED"
    elif still_moving_same_way:
        return "HELD"
    else:
        return "FLAT"


def run_followup():
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    pending_files = glob.glob(f"{PENDING_DIR}/*.json")
    print(f"Found {len(pending_files)} pending alert file(s).")

    if not pending_files:
        print("Nothing pending - exiting.")
        return

    now = datetime.now()
    results_by_sector = {}
    any_processed = False

    for filepath in pending_files:
        with open(filepath) as f:
            record = json.load(f)

        alert_time = datetime.fromisoformat(record["alert_time"])
        elapsed_minutes = (now - alert_time).total_seconds() / 60

        if elapsed_minutes < MIN_FOLLOWUP_MINUTES:
            print(f"  {filepath}: only {elapsed_minutes:.0f} min old, waiting for {MIN_FOLLOWUP_MINUTES} min - skipping for now")
            continue

        sector = record["sector"]
        followups = []
        for stock in record["stocks"]:
            current_price = get_current_price(stock["ticker"])
            if current_price is None:
                continue
            change_since_alert = (current_price - stock["alert_price"]) / stock["alert_price"] * 100
            outcome = classify_outcome(stock["alert_pct_move"], change_since_alert)
            followups.append({
                "ticker": stock["ticker"],
                "alert_price": stock["alert_price"],
                "current_price": current_price,
                "change_since_alert_pct": change_since_alert,
                "outcome": outcome,
            })

        if followups:
            results_by_sector.setdefault(sector, []).extend(followups)

        # Move processed file out of pending, regardless of whether we
        # got price data for every stock in it - avoid re-checking forever.
        processed_path = os.path.join(PROCESSED_DIR, os.path.basename(filepath))
        os.rename(filepath, processed_path)
        any_processed = True

    if not any_processed:
        print("No pending files were old enough yet - nothing to report this run.")
        return

    if not results_by_sector:
        print("Processed some files but got no usable follow-up data.")
        return

    send_followup_summary(results_by_sector)


def send_followup_summary(results_by_sector: dict):
    now_str = datetime.now().strftime("%d-%b-%Y %H:%M")
    lines = [f"[EarlyVolume-Followup] 🔍 *Follow-Up Check* — {now_str}", "_From Claudeown repo_", ""]

    outcome_emoji = {"HELD": "✅", "REVERSED": "🔄", "FLAT": "➖"}
    counts = {"HELD": 0, "REVERSED": 0, "FLAT": 0}

    for sector, stocks in results_by_sector.items():
        lines.append(f"*{sector}*:")
        for s in stocks:
            counts[s["outcome"]] += 1
            emoji = outcome_emoji[s["outcome"]]
            lines.append(
                f"  {emoji} {s['ticker']} — {s['outcome']}: "
                f"{s['change_since_alert_pct']:+.1f}% since alert "
                f"(₹{s['alert_price']:.2f} → ₹{s['current_price']:.2f})"
            )
        lines.append("")

    total = sum(counts.values())
    if total > 0:
        lines.append(
            f"Summary: {counts['HELD']}/{total} held direction, "
            f"{counts['REVERSED']}/{total} reversed, {counts['FLAT']}/{total} flat."
        )

    lines.append(
        "\n⚠️ This tracks whether early volume alerts held or reversed - "
        "it's a track-record tool, not a trading signal itself. A high "
        "reversal rate over time means treat volume spikes with more "
        "caution, not less."
    )

    message = "\n".join(lines)
    if len(message) > 4000:
        for i in range(0, len(message), 3800):
            send_telegram(message[i:i + 3800])
    else:
        send_telegram(message)


if __name__ == "__main__":
    run_followup()
