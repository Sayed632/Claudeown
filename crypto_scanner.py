"""
Crypto Scanner
--------------
Tracks the top 100 cryptocurrencies by market cap (via CoinGecko's free
public API - no key needed) and reports:
  1. Top gainers/losers by 24h price change
  2. Volume spikes - coins trading at unusually high volume relative to
     their OWN recent history (not a fixed threshold), similar in spirit
     to early_volume_scanner.py for stocks.

HONESTY NOTES:
  - Runs during the same active hours as your stock scans (9 AM - 3:30 PM
    IST) for consistency/manageability - crypto itself trades 24/7, so
    this deliberately does NOT cover overnight/weekend moves. A coin
    could surge or crash while this isn't running.
  - Volume-spike detection needs a few runs to build a baseline (stored
    in crypto_volume_history.json) - the first 2-3 runs after this is
    deployed won't have enough history to flag anything yet, that's
    expected, not a bug.
  - CoinGecko's free tier has no published SLA - if it starts rate
    limiting or failing, this scan will just skip that run, not crash
    your other scanners (they're independent workflows).
  - Crypto is far more volatile than stocks - a 10-20% daily move is
    routine, not necessarily "unusual." Thresholds here are calibrated
    higher than the stock scanners for that reason.
"""
import os
import json
from datetime import datetime

import requests

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("MY_CHAT_ID")

COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/markets"
TOP_N_GAINERS_LOSERS = 10
MIN_RELATIVE_VOLUME = 3.0  # higher bar than stocks - crypto volume is naturally choppier
MIN_HISTORY_READINGS = 3   # need this many prior readings before flagging volume spikes
MAX_HISTORY_READINGS = 20  # cap file size - roughly 10 hours of history at 30-min cadence
HISTORY_FILE = "crypto_volume_history.json"


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


def fetch_top_100() -> list:
    params = {
        "vs_currency": "inr",
        "order": "market_cap_desc",
        "per_page": 100,
        "page": 1,
        "price_change_percentage": "24h",
    }
    resp = requests.get(COINGECKO_URL, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def load_history() -> dict:
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def save_history(history: dict):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def find_volume_spikes(coins: list, history: dict) -> list:
    """Compare each coin's current volume to its own recent average."""
    spikes = []
    for coin in coins:
        coin_id = coin["id"]
        current_volume = coin.get("total_volume") or 0
        past_readings = history.get(coin_id, [])

        if len(past_readings) >= MIN_HISTORY_READINGS and current_volume > 0:
            baseline = sum(past_readings) / len(past_readings)
            if baseline > 0:
                relative_volume = current_volume / baseline
                if relative_volume >= MIN_RELATIVE_VOLUME:
                    spikes.append({
                        "symbol": coin["symbol"].upper(),
                        "name": coin["name"],
                        "relative_volume": relative_volume,
                        "price": coin["current_price"],
                        "pct_change_24h": coin.get("price_change_percentage_24h") or 0,
                    })

        # Update history regardless of whether we flagged a spike
        past_readings.append(current_volume)
        history[coin_id] = past_readings[-MAX_HISTORY_READINGS:]

    spikes.sort(key=lambda x: x["relative_volume"], reverse=True)
    return spikes


def run_scanner():
    now_str = datetime.now().strftime("%d-%b-%Y %H:%M")

    try:
        coins = fetch_top_100()
    except Exception as e:
        print(f"Failed to fetch CoinGecko data: {e}")
        send_telegram(
            f"[CryptoScan] ⚠️ *Crypto Scan* — {now_str}\n"
            "_From Claudeown repo_\n\nCould not fetch data from CoinGecko this run."
        )
        return

    if not coins:
        print("No coin data returned.")
        return

    # Filter out coins with missing 24h change data (some newer/illiquid listings)
    valid_coins = [c for c in coins if c.get("price_change_percentage_24h") is not None]
    sorted_by_change = sorted(valid_coins, key=lambda x: x["price_change_percentage_24h"], reverse=True)
    gainers = sorted_by_change[:TOP_N_GAINERS_LOSERS]
    losers = sorted_by_change[-TOP_N_GAINERS_LOSERS:][::-1]

    history = load_history()
    spikes = find_volume_spikes(coins, history)
    save_history(history)

    lines = [f"[CryptoScan] 🪙 *Crypto Scan (Top 100)* — {now_str}", "_From Claudeown repo_", ""]

    lines.append("*📈 Top Gainers (24h):*")
    for c in gainers:
        lines.append(f"  🟢 {c['symbol'].upper()} {c['price_change_percentage_24h']:+.1f}% | ₹{c['current_price']:,.2f}")

    lines.append("\n*📉 Top Losers (24h):*")
    for c in losers:
        lines.append(f"  🔴 {c['symbol'].upper()} {c['price_change_percentage_24h']:+.1f}% | ₹{c['current_price']:,.2f}")

    if spikes:
        lines.append("\n*⚡ Volume Spikes (vs own recent average):*")
        for s in spikes[:10]:
            lines.append(
                f"  {s['symbol']} — {s['relative_volume']:.1f}x normal volume, "
                f"{s['pct_change_24h']:+.1f}% (24h) | ₹{s['price']:,.2f}"
            )
    else:
        lines.append("\n*⚡ Volume Spikes:* none detected this run (or still building baseline history).")

    lines.append(
        "\n⚠️ Crypto is highly volatile - large daily moves are routine, not "
        "necessarily meaningful. Runs only during stock-market hours (9 AM - "
        "3:30 PM IST), NOT 24/7 - overnight/weekend moves aren't covered. "
        "Not financial advice."
    )

    message = "\n".join(lines)
    if len(message) > 4000:
        for i in range(0, len(message), 3800):
            send_telegram(message[i:i + 3800])
    else:
        send_telegram(message)


if __name__ == "__main__":
    run_scanner()
