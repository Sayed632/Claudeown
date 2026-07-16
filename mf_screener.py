"""
Mutual Fund Screener
---------------------
Finds the top-performing Direct-Growth equity mutual funds in India,
segmented into Large Cap / Mid Cap / Small Cap, ranked by a transparent
blended-CAGR score.

HONESTY NOTE ON METHODOLOGY:
This does NOT replicate Value Research / Morningstar / CRISIL star
ratings - those are proprietary scoring systems (risk-adjustment,
consistency, manager tenure, etc.) with formulas that aren't publicly
documented. This instead ranks funds purely by their own historical
NAV-derived returns, using a transparent, documented blend:

    Blend Score = 0.20 x (1-Year CAGR) + 0.40 x (3-Year CAGR) + 0.40 x (5-Year CAGR)

This weights sustained multi-year performance over short-term spikes.
Funds without a full 5-year NAV history are excluded from ranking
(newer funds can't be fairly compared on this basis).

Only DIRECT-GROWTH plans are considered - Regular plans bake in
distributor commission, which would make performance comparisons unfair
to Direct plan investors (and most self-directed investors use Direct).

DATA SOURCES (both free, no API key needed):
  - mfapi.in scheme list: https://api.mfapi.in/mf
  - mfapi.in per-scheme history + category metadata: https://api.mfapi.in/mf/{code}
  (mfapi.in is a free community wrapper around AMFI's official NAV data)

This is a WEEKLY job, not daily - mutual fund NAVs update once a day and
category rankings don't meaningfully shift hour to hour, unlike stock
scans. Running this more frequently would just waste API calls.
"""

import os
import re
import json
import time
from datetime import datetime, timedelta

import requests

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("MY_CHAT_ID")

TOP_N = 10
CATEGORIES = {
    "Large Cap": re.compile(r"large\s*cap", re.IGNORECASE),
    "Mid Cap": re.compile(r"\bmid\s*cap\b", re.IGNORECASE),
    "Small Cap": re.compile(r"small\s*cap", re.IGNORECASE),
}
# Explicitly exclude these even if they loosely match, to avoid category confusion
EXCLUDE_PATTERNS = re.compile(r"multi\s*cap|large\s*&\s*mid|flexi\s*cap|hybrid", re.IGNORECASE)

MFAPI_BASE = "https://api.mfapi.in/mf"
OUTPUT_FILE = "mf_rankings.json"


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


def get_candidate_schemes() -> dict:
    """
    Fetch the full lightweight scheme list, filter by name to likely
    Direct-Growth equity funds in our 3 categories. Returns
    {category: [(code, name), ...]}.
    """
    print("Fetching full scheme list from mfapi.in...")
    resp = requests.get(MFAPI_BASE, timeout=60)
    resp.raise_for_status()
    all_schemes = resp.json()
    print(f"Total schemes in AMFI universe: {len(all_schemes)}")

    candidates = {cat: [] for cat in CATEGORIES}
    for scheme in all_schemes:
        name = scheme.get("schemeName", "")
        if "direct" not in name.lower() or "growth" not in name.lower():
            continue
        if EXCLUDE_PATTERNS.search(name):
            continue
        for cat, pattern in CATEGORIES.items():
            if pattern.search(name):
                candidates[cat].append((scheme["schemeCode"], name))
                break

    for cat, schemes in candidates.items():
        print(f"  {cat}: {len(schemes)} candidate schemes")
    return candidates


def calculate_cagr(nav_history: list, years_back: float) -> float:
    """
    nav_history: list of {"date": "DD-MM-YYYY", "nav": "123.45"}, sorted
    newest-first (mfapi.in's default order).
    Returns CAGR as a percentage, or None if not enough history.
    """
    if not nav_history:
        return None
    try:
        latest_date = datetime.strptime(nav_history[0]["date"], "%d-%m-%Y")
        latest_nav = float(nav_history[0]["nav"])
    except (ValueError, KeyError, IndexError):
        return None

    target_date = latest_date - timedelta(days=int(years_back * 365.25))

    # Find the NAV entry closest to (but not after) the target date
    closest = None
    for entry in nav_history:
        try:
            entry_date = datetime.strptime(entry["date"], "%d-%m-%Y")
        except ValueError:
            continue
        if entry_date <= target_date:
            closest = entry
            break

    if closest is None:
        return None  # not enough history

    try:
        past_nav = float(closest["nav"])
        if past_nav <= 0:
            return None
        cagr = ((latest_nav / past_nav) ** (1 / years_back) - 1) * 100
        return cagr
    except (ValueError, ZeroDivisionError):
        return None


def evaluate_fund(code: str, name: str) -> dict | None:
    """Fetch full history for one fund and compute its CAGR + blend score."""
    try:
        resp = requests.get(f"{MFAPI_BASE}/{code}", timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  {code} ({name[:40]}): fetch error - {e}")
        return None

    nav_history = data.get("data", [])
    if len(nav_history) < 100:  # sanity check - not enough data points
        return None

    cagr_1y = calculate_cagr(nav_history, 1)
    cagr_3y = calculate_cagr(nav_history, 3)
    cagr_5y = calculate_cagr(nav_history, 5)

    if cagr_1y is None or cagr_3y is None or cagr_5y is None:
        return None  # exclude funds without full 5-year history

    blend_score = 0.20 * cagr_1y + 0.40 * cagr_3y + 0.40 * cagr_5y

    return {
        "code": code,
        "name": name,
        "cagr_1y": round(cagr_1y, 2),
        "cagr_3y": round(cagr_3y, 2),
        "cagr_5y": round(cagr_5y, 2),
        "blend_score": round(blend_score, 2),
    }


def run_screener():
    candidates = get_candidate_schemes()
    results = {}

    for category, schemes in candidates.items():
        print(f"\nEvaluating {len(schemes)} candidates in {category}...")
        evaluated = []
        for i, (code, name) in enumerate(schemes):
            result = evaluate_fund(code, name)
            if result:
                evaluated.append(result)
            if (i + 1) % 20 == 0:
                print(f"  ...{i + 1}/{len(schemes)} processed")
            time.sleep(0.15)  # be polite to the free API

        evaluated.sort(key=lambda x: x["blend_score"], reverse=True)
        top = evaluated[:TOP_N]
        results[category] = top
        print(f"  {category}: {len(evaluated)} funds had full 5-year history, top {len(top)} selected")

    output = {
        "generated_at": datetime.now().isoformat(),
        "methodology": "Blend Score = 0.20x(1Y CAGR) + 0.40x(3Y CAGR) + 0.40x(5Y CAGR). Direct-Growth plans only. Own calculation, not a Value Research/Morningstar/CRISIL rating.",
        "categories": results,
    }
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nWrote results to {OUTPUT_FILE}")

    send_telegram_summary(results)


def send_telegram_summary(results: dict):
    now_str = datetime.now().strftime("%d-%b-%Y")
    lines = [f"[MFScreener] 📈 *Top Mutual Funds* — {now_str}", "_From Claudeown repo_", ""]
    lines.append(
        "_Methodology: 20% x 1Y-CAGR + 40% x 3Y-CAGR + 40% x 5Y-CAGR, "
        "Direct-Growth plans only. Own calculation - NOT a Value Research "
        "/ Morningstar rating._\n"
    )

    for category, funds in results.items():
        lines.append(f"*{category}* (top {len(funds)}):")
        if not funds:
            lines.append("  No funds with full 5-year history found.")
        for i, f in enumerate(funds, 1):
            short_name = f["name"].split(" - ")[0][:45]
            lines.append(
                f"  {i}. {short_name}\n"
                f"     1Y: {f['cagr_1y']:+.1f}% | 3Y: {f['cagr_3y']:+.1f}% | "
                f"5Y: {f['cagr_5y']:+.1f}% | Score: {f['blend_score']:.1f}"
            )
        lines.append("")

    lines.append(
        "⚠️ Past performance does not guarantee future returns. This is a "
        "systematic ranking tool, not investment advice - verify fund "
        "details, expense ratios, and exit loads yourself before investing."
    )

    message = "\n".join(lines)
    # Telegram caps messages at 4096 chars - split if needed
    if len(message) > 4000:
        for i in range(0, len(message), 3800):
            send_telegram(message[i:i + 3800])
    else:
        send_telegram(message)


if __name__ == "__main__":
    run_screener()
