# Claudeown
# Swing Signal Bot (Simple Edition)

A minimal, reliable daily swing-trade signal scanner for NSE stocks.
Sends results to your Telegram — every day, even if there are zero setups,
so you always know it ran.

## Why this is different from your older bots
- Fixed list of 60 stocks (no dependency on Screener.in or NSE site scraping
  that can silently fail).
- Always sends a Telegram message, even on a "no signals" day — no more silence.
- One file (`scanner.py`) — everything is readable top to bottom.

## Setup (do this once, ~10 minutes)

### 1. Create the repo
On GitHub (mobile browser or app): New repository → name it e.g.
`swing-signal-bot` → create it.

### 2. Add the 3 files
In the new repo, tap **Add file → Create new file** three times and paste:
- `scanner.py`
- `requirements.txt`
- `.github/workflows/swing_scan.yml` (GitHub will auto-create the folders
  when you type this full path as the filename)

### 3. Add your Telegram secrets
Go to: repo **Settings → Secrets and variables → Actions → New repository secret**

Add two secrets:
- `TELEGRAM_TOKEN` → your bot token (same one you've used before)
- `MY_CHAT_ID` → your Telegram chat ID

### 4. Test it manually (don't wait for the schedule)
Go to the **Actions** tab → click **Daily Swing Scan** → **Run workflow** button
→ Run workflow. Wait ~1-2 minutes, then check Telegram.

If it fails, click into the failed run and read the red error text —
it will usually say exactly what's wrong (e.g. wrong secret name).

### 5. Let it run automatically
Once the manual test works, it will run every weekday at 4:00 PM IST
(after market close) with no further action from you.

## Tuning it later
Everything you'd want to change lives in the `CONFIG` section at the top of
`scanner.py`:
- `NSE_UNIVERSE` — add/remove stocks
- `RSI_OVERSOLD`, `BB_PROXIMITY_PCT` — how strict the setup criteria are
- `ATR_STOP_MULT` / `ATR_TARGET_MULT` — your stop-loss and target distance

## Important
This is a signal tool only — it does not place trades. You review the
Telegram message and decide manually. Not financial advice.
