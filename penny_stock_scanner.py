"""
Penny Stock / Small-Cap Speculative Mover Scanner
---------------------------------------------------
Flags penny stocks (price < ₹20) and small caps (market cap < ₹1,000 Cr)
that are BOTH surging AND showing red flags typical of speculative,
narrative-driven moves rather than fundamentals-driven ones - the same
pattern discussed for ATVO Enterprises (business-pivot story, thin
volume, extreme PE, tiny actual earnings).

DESIGN: two-stage filtering to stay fast and free-tier friendly:
  Stage 1 (cheap, fast): price + market cap screen across the full NSE
    equity list (~2,200 stocks) using yfinance's lightweight fast_info.
  Stage 2 (slower, but only run on the small Stage-1 survivor set):
    5-day price surge %, PE ratio, average volume - the actual red-flag
    checks.

ALERT LOGIC (deliberately conservative - both conditions required):
  SURGE:      5-day price change >= SURGE_THRESHOLD_PCT
  RED FLAGS:  PE ratio missing/negative/> PE_RED_FLAG_THRESHOLD,
              OR average daily volume < THIN_VOLUME_THRESHOLD
  ALERT ONLY IF: surge AND at least one red flag - matching the
  explicit "only flag if BOTH surge and red flags present" requirement.

HONESTY NOTE: this is a CAUTION tool, not a buy signal generator. A hit
here means "this is moving AND shows classic speculative-mover
warning signs" - it does not mean the move will continue or reverse.
Penny stocks are also the most common vehicle for pump-and-dump
schemes - treat any hit here with extra skepticism, not less.
"""
import os
import time
from datetime import datetime, timezone, timedelta

import requests
import yfinance as yf

from stock_enrichment import load_cache, save_cache, already_enriched_today, enrich_stock

ENRICHMENT_CACHE_FILE = "enrichment_cache_pennystock.json"

IST = timezone(timedelta(hours=5, minutes=30))

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("MY_CHAT_ID")

EQUITY_LIST_URL = "https://raw.githubusercontent.com/Sayed632/PKScreener/main/results/Indices/EQUITY_L.csv"

MAX_PRICE = 20.0
MAX_MARKET_CAP_CR = 1000  # ₹1,000 Cr
MAX_MARKET_CAP = MAX_MARKET_CAP_CR * 1e7  # 1 Cr = 1e7, so 1000 Cr = 1e10

SURGE_THRESHOLD_PCT = 20.0     # 5-day price change
PE_RED_FLAG_THRESHOLD = 100.0  # PE above this (or missing/negative) counts as a red flag
THIN_VOLUME_THRESHOLD = 50000  # avg daily volume below this counts as a red flag

MAX_RESULTS = 15


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


def load_equity_universe() -> list:
    """Pull the full NSE equity list (already maintained in PKScreener)."""
    try:
        resp = requests.get(EQUITY_LIST_URL, timeout=30)
        resp.raise_for_status()
        lines = resp.text.strip().split("\n")
        symbols = []
        for line in lines[1:]:  # skip header
            parts = line.split(",")
            if parts and parts[0].strip():
                symbols.append(parts[0].strip() + ".NS")
        return symbols
    except Exception as e:
        print(f"Failed to load equity universe: {e}")
        return []


def stage1_filter(symbol: str):
    """Cheap check: price and market cap. Returns dict or None."""
    try:
        tk = yf.Ticker(symbol)
        info = tk.fast_info
        price = info.get("lastPrice") or info.get("last_price")
        market_cap = info.get("marketCap") or info.get("market_cap")
        if price is None or market_cap is None:
            return None
        if price < MAX_PRICE and market_cap < MAX_MARKET_CAP:
            return {"symbol": symbol, "price": price, "market_cap": market_cap}
    except Exception:
        pass
    return None


def stage2_check(candidate: dict):
    """Slower check on the narrowed candidate set: surge % + red flags."""
    symbol = candidate["symbol"]
    try:
        tk = yf.Ticker(symbol)
        hist = tk.history(period="10d", interval="1d")
        if hist is None or len(hist) < 6:
            return None

        close_now = hist["Close"].iloc[-1]
        close_5d_ago = hist["Close"].iloc[-6]
        if close_5d_ago == 0:
            return None
        surge_pct = (close_now - close_5d_ago) / close_5d_ago * 100

        if surge_pct < SURGE_THRESHOLD_PCT:
            return None  # no surge, skip regardless of red flags

        avg_volume = hist["Volume"].mean()

        info = tk.info  # slower full call - only reached for surge candidates
        pe_ratio = info.get("trailingPE")

        red_flags = []
        if pe_ratio is None or pe_ratio < 0 or pe_ratio > PE_RED_FLAG_THRESHOLD:
            red_flags.append(f"PE {'N/A or negative' if not pe_ratio or pe_ratio < 0 else f'{pe_ratio:.0f}x'}")
        if avg_volume < THIN_VOLUME_THRESHOLD:
            red_flags.append(f"thin volume ({avg_volume:.0f}/day avg)")

        if not red_flags:
            return None  # surging but no red flags - doesn't meet "both" requirement

        return {
            "symbol": symbol.replace(".NS", ""),
            "price": close_now,
            "market_cap_cr": candidate["market_cap"] / 1e7,
            "surge_pct": surge_pct,
            "red_flags": red_flags,
        }
    except Exception as e:
        print(f"  {symbol}: stage 2 error - {e}")
        return None


def run_scanner():
    now_str = datetime.now(IST).strftime("%d-%b-%Y %H:%M")

    universe = load_equity_universe()
    if not universe:
        send_telegram(
            f"[PennyStockScan] ⚠️ *Penny/Small-Cap Scan* — {now_str}\n"
            "_From Claudeown repo_\n\nCould not load NSE equity list this run."
        )
        return

    print(f"Loaded {len(universe)} NSE-listed symbols. Running Stage 1 filter (price + market cap)...")

    stage1_survivors = []
    for i, symbol in enumerate(universe):
        result = stage1_filter(symbol)
        if result:
            stage1_survivors.append(result)
        if (i + 1) % 200 == 0:
            print(f"  ...{i + 1}/{len(universe)} checked, {len(stage1_survivors)} survivors so far")
        time.sleep(0.05)

    print(f"Stage 1 complete: {len(stage1_survivors)} candidates match price < ₹{MAX_PRICE} and market cap < ₹{MAX_MARKET_CAP_CR} Cr")

    hits = []
    for i, candidate in enumerate(stage1_survivors):
        result = stage2_check(candidate)
        if result:
            hits.append(result)
        time.sleep(0.1)

    hits.sort(key=lambda x: x["surge_pct"], reverse=True)
    top = hits[:MAX_RESULTS]

    print(f"Stage 2 complete: {len(hits)} stocks had BOTH surge AND red flags")

    lines = [f"[PennyStockScan] 🚩 *Penny/Small-Cap Speculative Movers* — {now_str}", "_From Claudeown repo_", ""]
    lines.append(
        f"_Criteria: price < ₹{MAX_PRICE:.0f}, market cap < ₹{MAX_MARKET_CAP_CR:,} Cr, "
        f"5-day surge >= {SURGE_THRESHOLD_PCT:.0f}%, AND at least one red flag "
        f"(PE > {PE_RED_FLAG_THRESHOLD:.0f}x/missing, or avg volume < {THIN_VOLUME_THRESHOLD:,}/day)._\n"
    )

    if not top:
        lines.append("No stocks matched all criteria this run.")
    else:
        for h in top:
            lines.append(
                f"🚩 *{h['symbol']}* — {h['surge_pct']:+.1f}% (5d) | ₹{h['price']:.2f} | "
                f"MCap ₹{h['market_cap_cr']:.0f} Cr\n"
                f"   Red flags: {', '.join(h['red_flags'])}"
            )

    lines.append(
        "\n⚠️ This is a CAUTION tool, not a buy signal - a hit means the stock is "
        "surging AND showing classic speculative-mover warning signs (weak "
        "fundamentals, thin liquidity). Penny stocks are the most common vehicle "
        "for pump-and-dump schemes - treat hits here with MORE skepticism, not "
        "less. Verify independently. Not financial advice."
    )

    message = "\n".join(lines)
    if len(message) > 4000:
        for i in range(0, len(message), 3800):
            send_telegram(message[i:i + 3800])
    else:
        send_telegram(message)

    # Enrichment: business summary, book value, contract news, delivery %,
    # transparent scorecard. Once per ticker per day - skip if already done.
    if top:
        cache = load_cache(ENRICHMENT_CACHE_FILE)
        for h in top:
            ticker_full = h["symbol"] + ".NS"
            if already_enriched_today(ticker_full, cache):
                print(f"  {ticker_full}: already enriched today, skipping")
                continue
            print(f"  Enriching {ticker_full}...")
            enrichment_text = enrich_stock(ticker_full, has_red_flags=True)
            send_telegram(f"[PennyStockScan]{enrichment_text}")
            cache[ticker_full] = {"date": datetime.now(IST).strftime("%Y-%m-%d")}
        save_cache(ENRICHMENT_CACHE_FILE, cache)


if __name__ == "__main__":
    run_scanner()
