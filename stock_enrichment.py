"""
Stock Enrichment Module (shared by Top Gainers, Early Volume, Penny Stock scans)
----------------------------------------------------------------------------------
Adds due-diligence context to a flagged stock:
  - Business summary (what the company actually does)
  - Book value + Price-to-Book ratio
  - Recent contract/order-win news (Gemini + Search grounding)
  - Delivery % (previous session only - see caveat below)
  - A transparent, auditable scorecard out of 10 - NOT a black-box AI
    number. Every point is tied to a named, visible reason so you can
    see exactly why a stock scored what it did, not just trust a number.

HONEST CAVEATS:
  - DELIVERY % IS FOR THE PREVIOUS COMPLETED SESSION, NOT LIVE. NSE only
    publishes delivery data in its end-of-day bhavcopy file - there is
    no live intraday delivery % anywhere. A same-day alert will show
    yesterday's delivery %, clearly labeled as such.
  - NSE's bhavcopy endpoint may be blocked from GitHub Actions'
    datacenter IPs (same issue as NSE's live quote API) - if so, this
    gracefully omits delivery % rather than failing the whole
    enrichment.
  - The scorecard is a rule-based composite of available signals, not
    a prediction. A high score means "several positive signals present
    and no major red flags found" - it does NOT mean "will go up."
  - Gemini's news search can miss things or occasionally misattribute
    news to the wrong company (especially for tickers with generic
    names) - treat the contract-news section as a lead to verify, not
    a confirmed fact.

CACHING: each ticker is only enriched ONCE PER CALENDAR DAY (IST), no
matter how many times it re-appears across scan runs that day. This
keeps API usage (Gemini calls, yfinance .info calls) bounded instead of
re-analyzing the same stock every 5 minutes.
"""
import os
import json
import re
from datetime import datetime, timezone, timedelta

import requests
import yfinance as yf

IST = timezone(timedelta(hours=5, minutes=30))

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash"  # verify this is still current before relying on it
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

NSE_BHAVCOPY_URL_TEMPLATE = (
    "https://archives.nseindia.com/products/content/sec_bhavdata_full_{date}.csv"
)


def _today_ist_str() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def load_cache(cache_file: str) -> dict:
    if os.path.exists(cache_file):
        try:
            with open(cache_file) as f:
                data = json.load(f)
            # Drop entries from previous days - only same-day dedup matters
            today = _today_ist_str()
            return {k: v for k, v in data.items() if v.get("date") == today}
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def save_cache(cache_file: str, cache: dict):
    with open(cache_file, "w") as f:
        json.dump(cache, f, indent=2)


def already_enriched_today(ticker: str, cache: dict) -> bool:
    return ticker in cache and cache[ticker].get("date") == _today_ist_str()


def get_business_summary_and_book_value(ticker: str) -> dict:
    """yfinance .info - business summary, book value, P/B ratio."""
    try:
        info = yf.Ticker(ticker).info
        summary = info.get("longBusinessSummary", "")
        # Trim to a Telegram-friendly length
        if summary and len(summary) > 280:
            summary = summary[:277].rsplit(" ", 1)[0] + "..."
        book_value = info.get("bookValue")
        current_price = info.get("currentPrice") or info.get("regularMarketPrice")
        pb_ratio = (current_price / book_value) if (book_value and current_price and book_value > 0) else None
        return {
            "summary": summary or "No business summary available.",
            "book_value": book_value,
            "pb_ratio": pb_ratio,
        }
    except Exception as e:
        print(f"  {ticker}: business summary fetch error - {e}")
        return {"summary": "Could not fetch.", "book_value": None, "pb_ratio": None}


def get_contract_news(ticker: str, company_name: str) -> dict:
    """Gemini + Search grounding - specifically hunts for contract/order-win news."""
    if not GEMINI_API_KEY:
        return {"found": False, "text": "GEMINI_API_KEY not configured - skipped."}

    prompt = (
        f"Search for recent news (last 30 days) about {company_name} ({ticker}, NSE-listed India) "
        "specifically regarding: new contracts, order wins, business deals, regulatory "
        "approvals, or major corporate announcements. If you find genuine, verifiable news "
        "from real sources, summarize it in 1-2 sentences. If you find nothing specific or "
        "only speculative/unverifiable claims, say so plainly - do not invent or guess.\n\n"
        "Respond ONLY with valid JSON: "
        '{"found": true or false, "summary": "1-2 sentence summary or empty string"}'
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
    }
    try:
        resp = requests.post(f"{GEMINI_URL}?key={GEMINI_API_KEY}", json=payload, timeout=45)
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        text = re.sub(r"^```json\s*|\s*```$", "", text)
        parsed = json.loads(text)
        return {"found": parsed.get("found", False), "text": parsed.get("summary", "")}
    except Exception as e:
        print(f"  {ticker}: contract news fetch error - {e}")
        return {"found": False, "text": "Could not complete news search this run."}


_nse_bhavcopy_blocked_this_run = False  # circuit breaker - see docstring below


def get_delivery_pct(ticker: str) -> float | None:
    """
    Previous session's delivery % from NSE's bhavcopy. Returns None
    (gracefully) if unavailable.

    CIRCUIT BREAKER: if NSE blocks/times-out on the FIRST attempt for
    any stock in this run, it will almost certainly block every
    subsequent attempt too (same source IP, same block) - so retrying
    up to 3 dates x 20s timeout for every single flagged stock would
    waste minutes for nothing. Once one failure is seen, delivery % is
    skipped for the rest of this run rather than retried per stock.
    """
    global _nse_bhavcopy_blocked_this_run
    if _nse_bhavcopy_blocked_this_run:
        return None

    symbol = ticker.replace(".NS", "")
    try:
        # Try today and, if not yet published, yesterday - but with a
        # short timeout and bailing after the first real failure, not
        # burning 20s x 3 dates on a source that's clearly blocking us.
        for days_back in [0, 1, 2]:
            check_date = datetime.now(IST) - timedelta(days=days_back)
            date_str = check_date.strftime("%d%m%Y")
            url = NSE_BHAVCOPY_URL_TEMPLATE.format(date=date_str)
            try:
                resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
            except requests.exceptions.RequestException:
                _nse_bhavcopy_blocked_this_run = True
                print(f"  {ticker}: NSE bhavcopy unreachable - disabling delivery% for rest of this run")
                return None
            if resp.status_code == 403:
                _nse_bhavcopy_blocked_this_run = True
                print(f"  {ticker}: NSE returned 403 (blocked) - disabling delivery% for rest of this run")
                return None
            if resp.status_code != 200:
                continue
            lines = resp.text.strip().split("\n")
            header = [h.strip() for h in lines[0].split(",")]
            try:
                symbol_idx = header.index("SYMBOL")
                delivery_pct_idx = header.index(" %DLY_QT_TO_TRADED_QTY") if " %DLY_QT_TO_TRADED_QTY" in header else header.index("%DLY_QT_TO_TRADED_QTY")
            except ValueError:
                continue
            for line in lines[1:]:
                parts = [p.strip() for p in line.split(",")]
                if len(parts) > max(symbol_idx, delivery_pct_idx) and parts[symbol_idx] == symbol:
                    try:
                        return float(parts[delivery_pct_idx])
                    except ValueError:
                        continue
        return None
    except Exception as e:
        print(f"  {ticker}: delivery % fetch error - {e}")
        return None


def compute_scorecard(pb_ratio, contract_news_found: bool, delivery_pct, has_red_flags: bool) -> dict:
    """
    Transparent, auditable point-based score out of 10. Every point has
    a named reason - this is NOT a black-box AI-generated confidence
    number. Baseline 5/10 (neutral), adjusted by named factors.
    """
    score = 5.0
    reasons = []

    if pb_ratio is not None:
        if 0 < pb_ratio <= 3:
            score += 1.5
            reasons.append(f"+1.5: reasonable P/B ratio ({pb_ratio:.1f}x)")
        elif pb_ratio > 8:
            score -= 1.5
            reasons.append(f"-1.5: high P/B ratio ({pb_ratio:.1f}x)")
    else:
        reasons.append("+0: P/B ratio unavailable")

    if contract_news_found:
        score += 2.0
        reasons.append("+2.0: verifiable recent contract/order news found")
    else:
        reasons.append("+0: no verifiable recent contract news found")

    if delivery_pct is not None:
        if delivery_pct >= 50:
            score += 1.5
            reasons.append(f"+1.5: healthy delivery % ({delivery_pct:.1f}%, prev session)")
        elif delivery_pct < 20:
            score -= 1.5
            reasons.append(f"-1.5: low delivery % ({delivery_pct:.1f}%, prev session) - mostly intraday trading")
    else:
        reasons.append("+0: delivery % unavailable")

    if has_red_flags:
        score -= 2.0
        reasons.append("-2.0: scanner-level red flags present (e.g. extreme PE, thin volume)")

    score = max(0, min(10, score))
    return {"score": round(score, 1), "reasons": reasons}


def enrich_stock(ticker: str, company_name_hint: str = None, has_red_flags: bool = False) -> str:
    """Returns a formatted Telegram-ready text block for one stock."""
    biz = get_business_summary_and_book_value(ticker)
    company_name = company_name_hint or ticker.replace(".NS", "")
    news = get_contract_news(ticker, company_name)
    delivery_pct = get_delivery_pct(ticker)
    scorecard = compute_scorecard(biz["pb_ratio"], news["found"], delivery_pct, has_red_flags)

    lines = [f"\n📋 *{ticker.replace('.NS', '')} - Enrichment*"]
    lines.append(f"_{biz['summary']}_")
    if biz["book_value"]:
        pb_str = f" (P/B: {biz['pb_ratio']:.1f}x)" if biz["pb_ratio"] else ""
        lines.append(f"Book value: ₹{biz['book_value']:.2f}{pb_str}")
    if news["text"]:
        lines.append(f"📰 {news['text']}")
    if delivery_pct is not None:
        lines.append(f"📦 Delivery % (prev session): {delivery_pct:.1f}%")
    lines.append(f"🎯 Score: {scorecard['score']}/10")
    for reason in scorecard["reasons"]:
        lines.append(f"   {reason}")

    return "\n".join(lines)
