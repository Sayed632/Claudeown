"""
FII/DII + Institutional Bulk Deals Tracker (Daily)
-----------------------------------------------------
What this does, in plain English:

1. Fetches the overall daily FII/DII net buy/sell figures for the cash
   market (the single "how much foreign/domestic money moved" number).
2. Fetches today's NSE Bulk Deals (large institutional trades in specific
   stocks - this is the closest free, real data source to "which stocks
   institutions are moving money into/out of").
3. Maps each stock in the bulk deals to a SECTOR and a CAP TIER
   (Large / Mid / Small) using a manually maintained reference table
   (SECTOR_MAP below), then groups today's institutional activity by
   sector so you can see: "IT sector - institutions buying TCS (Large),
   selling PERSISTENT (Mid)" etc.

IMPORTANT HONESTY NOTES:
- NSE does not publish a free "FII/DII flow by sector" feed. This is our
  own approximation, built from real bulk-deal data + a static sector/
  cap-tier lookup table that YOU should periodically review and update
  (companies change cap tiers, sectors get reclassified, etc).
- NSE's website actively resists scripted access. This script uses the
  same technique most free NSE tools use (visit the homepage first to
  get session cookies, then call the data endpoint) but NSE can still
  block it on a given day. When that happens, this script says so
  clearly instead of silently failing.
- Bulk deals only capture LARGE individual trades (above NSE's disclosure
  threshold) - not all institutional activity. Treat this as a partial,
  directional signal, not a complete picture.
"""

import os
import sys
import time
from datetime import date, datetime

import requests

# ============================================================
# CONFIG
# ============================================================

# Manually maintained: symbol -> (sector, cap tier). Approximate and not
# exhaustive - review/update every few months as companies grow, shrink,
# or get reclassified.
SECTOR_MAP = {
    # IT
    "TCS": ("IT", "Large"), "INFY": ("IT", "Large"), "HCLTECH": ("IT", "Large"),
    "WIPRO": ("IT", "Large"), "TECHM": ("IT", "Large"), "LTIM": ("IT", "Large"),
    "PERSISTENT": ("IT", "Mid"), "COFORGE": ("IT", "Mid"), "MPHASIS": ("IT", "Mid"),
    "LTTS": ("IT", "Mid"), "CYIENT": ("IT", "Small"), "ZENSARTECH": ("IT", "Small"),

    # Banking
    "HDFCBANK": ("Banking", "Large"), "ICICIBANK": ("Banking", "Large"),
    "SBIN": ("Banking", "Large"), "KOTAKBANK": ("Banking", "Large"),
    "AXISBANK": ("Banking", "Large"), "INDUSINDBK": ("Banking", "Large"),
    "BANKBARODA": ("Banking", "Mid"), "PNB": ("Banking", "Mid"),
    "FEDERALBNK": ("Banking", "Mid"), "IDFCFIRSTB": ("Banking", "Mid"),
    "AUBANK": ("Banking", "Mid"), "RBLBANK": ("Banking", "Small"),

    # NBFC / Financials
    "BAJFINANCE": ("Financials", "Large"), "BAJAJFINSV": ("Financials", "Large"),
    "SBILIFE": ("Financials", "Large"), "HDFCLIFE": ("Financials", "Large"),
    "ICICIPRULI": ("Financials", "Mid"), "ICICIGI": ("Financials", "Mid"),
    "CHOLAFIN": ("Financials", "Mid"), "MUTHOOTFIN": ("Financials", "Mid"),
    "LICHSGFIN": ("Financials", "Mid"), "PFC": ("Financials", "Mid"),
    "RECLTD": ("Financials", "Mid"), "SBICARD": ("Financials", "Mid"),

    # Auto
    "MARUTI": ("Auto", "Large"), "TATAMOTORS": ("Auto", "Large"),
    "M&M": ("Auto", "Large"), "BAJAJ-AUTO": ("Auto", "Large"),
    "HEROMOTOCO": ("Auto", "Large"), "EICHERMOT": ("Auto", "Large"),
    "TVSMOTOR": ("Auto", "Mid"), "ASHOKLEY": ("Auto", "Mid"),
    "BALKRISIND": ("Auto", "Mid"), "MOTHERSON": ("Auto", "Mid"),
    "BOSCHLTD": ("Auto", "Mid"), "MRF": ("Auto", "Mid"),

    # Pharma
    "SUNPHARMA": ("Pharma", "Large"), "DRREDDY": ("Pharma", "Large"),
    "CIPLA": ("Pharma", "Large"), "DIVISLAB": ("Pharma", "Large"),
    "APOLLOHOSP": ("Pharma", "Large"), "LUPIN": ("Pharma", "Mid"),
    "AUROPHARMA": ("Pharma", "Mid"), "TORNTPHARM": ("Pharma", "Mid"),
    "ALKEM": ("Pharma", "Mid"), "LAURUSLABS": ("Pharma", "Mid"),
    "GLAND": ("Pharma", "Mid"), "SYNGENE": ("Pharma", "Mid"),
    "ABBOTINDIA": ("Pharma", "Mid"), "BIOCON": ("Pharma", "Mid"),
    "GRANULES": ("Pharma", "Small"), "IPCALAB": ("Pharma", "Small"),

    # FMCG
    "HINDUNILVR": ("FMCG", "Large"), "ITC": ("FMCG", "Large"),
    "NESTLEIND": ("FMCG", "Large"), "BRITANNIA": ("FMCG", "Large"),
    "TATACONSUM": ("FMCG", "Large"), "DABUR": ("FMCG", "Mid"),
    "GODREJCP": ("FMCG", "Mid"), "MARICO": ("FMCG", "Mid"),
    "COLPAL": ("FMCG", "Mid"), "VBL": ("FMCG", "Mid"), "UBL": ("FMCG", "Mid"),
    "RADICO": ("FMCG", "Small"), "EMAMILTD": ("FMCG", "Small"),

    # Metals & Mining
    "TATASTEEL": ("Metals", "Large"), "JSWSTEEL": ("Metals", "Large"),
    "HINDALCO": ("Metals", "Large"), "VEDL": ("Metals", "Large"),
    "COALINDIA": ("Metals", "Large"), "HINDZINC": ("Metals", "Mid"),
    "JINDALSTEL": ("Metals", "Mid"), "NMDC": ("Metals", "Mid"),
    "SAIL": ("Metals", "Mid"), "NATIONALUM": ("Metals", "Small"),
    "MOIL": ("Metals", "Small"), "HEG": ("Metals", "Small"),
    "GRAPHITE": ("Metals", "Small"),

    # Energy / Oil & Gas
    "RELIANCE": ("Energy", "Large"), "ONGC": ("Energy", "Large"),
    "BPCL": ("Energy", "Large"), "IOC": ("Energy", "Large"),
    "GAIL": ("Energy", "Mid"), "PETRONET": ("Energy", "Mid"),
    "OIL": ("Energy", "Mid"), "IGL": ("Energy", "Mid"), "MGL": ("Energy", "Mid"),

    # Cement / Infra / Construction
    "ULTRACEMCO": ("Cement & Infra", "Large"), "GRASIM": ("Cement & Infra", "Large"),
    "SHREECEM": ("Cement & Infra", "Large"), "LT": ("Cement & Infra", "Large"),
    "ADANIPORTS": ("Cement & Infra", "Large"), "ADANIENT": ("Cement & Infra", "Large"),
    "AMBUJACEM": ("Cement & Infra", "Mid"), "ACC": ("Cement & Infra", "Mid"),
    "DALBHARAT": ("Cement & Infra", "Mid"),

    # Chemicals
    "PIDILITIND": ("Chemicals", "Large"), "SRF": ("Chemicals", "Mid"),
    "DEEPAKNTR": ("Chemicals", "Mid"), "NAVINFLUOR": ("Chemicals", "Mid"),
    "COROMANDEL": ("Chemicals", "Mid"), "PIIND": ("Chemicals", "Mid"),
    "BAYERCROP": ("Chemicals", "Mid"), "AARTIIND": ("Chemicals", "Small"),
    "ALKYLAMINE": ("Chemicals", "Small"), "FINEORG": ("Chemicals", "Small"),
    "GNFC": ("Chemicals", "Small"), "CHAMBLFERT": ("Chemicals", "Small"),
    "RALLIS": ("Chemicals", "Small"),

    # Consumer Discretionary / Durables
    "TITAN": ("Consumer Discretionary", "Large"), "TRENT": ("Consumer Discretionary", "Large"),
    "ASIANPAINT": ("Consumer Discretionary", "Large"), "PAGEIND": ("Consumer Discretionary", "Mid"),
    "RELAXO": ("Consumer Discretionary", "Mid"), "VOLTAS": ("Consumer Discretionary", "Mid"),
    "CROMPTON": ("Consumer Discretionary", "Mid"), "ASTRAL": ("Consumer Discretionary", "Mid"),
    "POLYCAB": ("Consumer Discretionary", "Mid"), "KEI": ("Consumer Discretionary", "Mid"),
    "APLAPOLLO": ("Consumer Discretionary", "Mid"), "SUPREMEIND": ("Consumer Discretionary", "Mid"),
    "WHIRLPOOL": ("Consumer Discretionary", "Small"), "KAJARIACER": ("Consumer Discretionary", "Small"),
    "CERA": ("Consumer Discretionary", "Small"), "RATNAMANI": ("Consumer Discretionary", "Small"),
    "CAMPUS": ("Consumer Discretionary", "Small"),

    # Telecom
    "BHARTIARTL": ("Telecom", "Large"), "INDUSTOWER": ("Telecom", "Mid"),
    "IDEA": ("Telecom", "Small"),

    # Power / Utilities
    "NTPC": ("Power", "Large"), "POWERGRID": ("Power", "Large"),
    "TATAPOWER": ("Power", "Mid"), "ADANIPOWER": ("Power", "Mid"),
    "ADANIGREEN": ("Power", "Mid"), "JSWENERGY": ("Power", "Mid"),

    # New-age / Internet
    "ZOMATO": ("New-age/Internet", "Mid"), "NYKAA": ("New-age/Internet", "Mid"),
    "PAYTM": ("New-age/Internet", "Mid"), "POLICYBZR": ("New-age/Internet", "Mid"),
    "IRCTC": ("New-age/Internet", "Mid"), "DIXON": ("New-age/Internet", "Mid"),
    "CDSL": ("New-age/Internet", "Mid"), "MCX": ("New-age/Internet", "Mid"),
    "IEX": ("New-age/Internet", "Mid"),

    # Retail / Food Services
    "JUBLFOOD": ("Retail & Food", "Mid"), "DEVYANI": ("Retail & Food", "Small"),
    "KPRMILL": ("Retail & Food", "Small"), "WELCORP": ("Retail & Food", "Small"),
}

NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

MAX_STOCKS_PER_SECTOR = 6

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
    """NSE requires a valid session cookie from visiting the homepage first."""
    s = requests.Session()
    s.headers.update(NSE_HEADERS)
    s.get("https://www.nseindia.com", timeout=15)
    return s


def fetch_fii_dii(session: requests.Session, retries: int = 2):
    """Returns the raw NSE FII/DII JSON list, or None if it fails."""
    for attempt in range(retries):
        try:
            r = session.get("https://www.nseindia.com/api/fiidiiTradeReact", timeout=15)
            if r.status_code == 200:
                return r.json()
            print(f"FII/DII fetch got status {r.status_code}")
        except Exception as e:
            print(f"FII/DII fetch failed (attempt {attempt + 1}): {e}")
        time.sleep(2)
    return None


def fetch_bulk_deals(session: requests.Session, day: date, retries: int = 2):
    """Returns list of bulk deal records for the given day, or [] if none/failed."""
    d_str = day.strftime("%d-%m-%Y")
    url = f"https://www.nseindia.com/api/historical/bulk-deals?from={d_str}&to={d_str}"
    for attempt in range(retries):
        try:
            r = session.get(url, timeout=15)
            if r.status_code == 200:
                data = r.json()
                return data.get("data", []) or []
            print(f"Bulk deals fetch got status {r.status_code}")
        except Exception as e:
            print(f"Bulk deals fetch failed (attempt {attempt + 1}): {e}")
        time.sleep(2)
    return []


def format_fii_dii_section(raw_data) -> str:
    if not raw_data:
        return "⚠️ Could not fetch FII/DII summary today (NSE feed unavailable)."

    try:
        lines = ["💰 *FII/DII Cash Market (₹ Cr)*"]
        for row in raw_data[:2]:  # NSE returns latest FII + DII rows
            category = row.get("category", "?")
            buy = row.get("buyValue", "?")
            sell = row.get("sellValue", "?")
            net = row.get("netValue", "?")
            lines.append(f"   {category}: Buy {buy} | Sell {sell} | Net {net}")
        return "\n".join(lines)
    except Exception as e:
        print(f"FII/DII formatting failed: {e}")
        return "⚠️ Got FII/DII data but couldn't parse it - format may have changed."


def format_bulk_deals_section(deals: list) -> str:
    if not deals:
        return "📭 No bulk deals recorded today (or NSE feed unavailable)."

    # Aggregate net direction per symbol across all deals that day
    symbol_activity = {}
    for deal in deals:
        symbol = (deal.get("BD_SYMBOL") or deal.get("symbol") or "").strip()
        side = (deal.get("BD_BUY_SELL") or deal.get("buySell") or "").strip().upper()
        qty = deal.get("BD_QTY_TRD") or deal.get("qty") or 0
        try:
            qty = float(str(qty).replace(",", ""))
        except Exception:
            qty = 0

        if not symbol:
            continue
        if symbol not in symbol_activity:
            symbol_activity[symbol] = {"buy_qty": 0, "sell_qty": 0}
        if side == "BUY":
            symbol_activity[symbol]["buy_qty"] += qty
        elif side == "SELL":
            symbol_activity[symbol]["sell_qty"] += qty

    # Group by sector
    sector_groups = {}
    for symbol, activity in symbol_activity.items():
        net = activity["buy_qty"] - activity["sell_qty"]
        direction = "BUY" if net > 0 else ("SELL" if net < 0 else "MIXED")
        sector, tier = SECTOR_MAP.get(symbol, ("Other/Unmapped", "Unknown"))

        sector_groups.setdefault(sector, []).append({
            "symbol": symbol, "tier": tier, "direction": direction,
        })

    lines = ["🏦 *Institutional Bulk Deals by Sector*"]
    for sector in sorted(sector_groups.keys()):
        stocks = sector_groups[sector][:MAX_STOCKS_PER_SECTOR]
        stock_strs = [f"{s['symbol']} ({s['tier']}, {s['direction']})" for s in stocks]
        lines.append(f"\n*{sector}*: {', '.join(stock_strs)}")

    return "\n".join(lines)


def run_scan():
    today = date.today()
    print(f"Fetching FII/DII + bulk deals for {today}")

    session = get_nse_session()
    fii_dii_data = fetch_fii_dii(session)
    bulk_deals = fetch_bulk_deals(session, today)

    today_str = today.strftime("%d-%b-%Y")
    lines = [f"[FII-DII] 📊 *FII/DII + Bulk Deals* — {today_str}", "_From Claudeown repo_", ""]
    lines.append(format_fii_dii_section(fii_dii_data))
    lines.append("")
    lines.append(format_bulk_deals_section(bulk_deals))
    lines.append(
        "\n⚠️ Sector/cap-tier mapping is a manually maintained approximation. "
        "Bulk deals only capture large disclosed trades, not all institutional "
        "activity. Not financial advice."
    )

    message = "\n".join(lines)
    sent = send_telegram(message)

    if not sent:
        print("Message FAILED to send.")
        sys.exit(1)
    print("Done.")


if __name__ == "__main__":
    run_scan()
       
