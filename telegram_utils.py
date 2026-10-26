"""
telegram_utils.py

Resilient Telegram sender, built after a real failure pattern was found
in the Sectorwise Early Volume scan (Oct 2026): ~15 parallel sector jobs
each fire alerts in the same second, Telegram throttles a bot to roughly
one message per second per chat, and the old send_telegram() treated ANY
non-200 as fatal - so a throttled job exited(1) and its alert (plus its
follow-up record and enrichment) was lost.

Behaviour, by response:
  200                      -> success
  429 (flood control)      -> wait the `retry_after` Telegram asks for
                              (+ small jitter, capped), then retry
  400 "can't parse entities" -> retry ONCE as plain text, so a stray
                              Markdown character can never drop an alert
  5xx / network error      -> exponential backoff (2s, 4s, 8s...), retry
  401/403/404 & other 4xx  -> permanent (bad token, bot blocked, wrong
                              chat) - report and give up, retrying
                              cannot help

Returns True/False just like the old helper, so callers don't change.
"""
import time
import random
import requests

DEFAULT_API_BASE = "https://api.telegram.org"
MAX_RETRY_AFTER_SECONDS = 30  # never let one throttled message hang a job for minutes


def send_with_retry(token, chat_id, text, parse_mode="Markdown",
                    max_attempts=6, api_base=DEFAULT_API_BASE, sleep=time.sleep) -> bool:
    if not token or not chat_id:
        print("ERROR: Telegram token or chat id not set.")
        return False

    url = f"{api_base}/bot{token}/sendMessage"
    use_parse_mode = parse_mode
    backoff = 2

    for attempt in range(1, max_attempts + 1):
        payload = {"chat_id": chat_id, "text": text}
        if use_parse_mode:
            payload["parse_mode"] = use_parse_mode

        try:
            resp = requests.post(url, data=payload, timeout=20)
        except requests.exceptions.RequestException as e:
            print(f"Telegram network error (attempt {attempt}/{max_attempts}): {e}")
            if attempt < max_attempts:
                sleep(backoff + random.random())
                backoff = min(backoff * 2, 20)
            continue

        if resp.status_code == 200:
            if attempt > 1:
                print(f"Telegram send succeeded on attempt {attempt}.")
            return True

        body = resp.text[:300]

        if resp.status_code == 429:
            try:
                wait = int(resp.json().get("parameters", {}).get("retry_after", 3))
            except Exception:
                wait = 3
            wait = min(wait, MAX_RETRY_AFTER_SECONDS) + random.random() * 1.5
            if attempt < max_attempts:
                print(f"Telegram flood control (attempt {attempt}/{max_attempts}) - waiting {wait:.1f}s")
                sleep(wait)
            else:
                print(f"Telegram flood control (attempt {attempt}/{max_attempts}) - out of retries")
            continue

        if resp.status_code == 400 and "parse entities" in body.lower() and use_parse_mode:
            print("Telegram rejected Markdown formatting - resending as plain text.")
            use_parse_mode = None
            continue  # immediate retry, no sleep needed

        if resp.status_code >= 500:
            print(f"Telegram server error {resp.status_code} (attempt {attempt}/{max_attempts})")
            if attempt < max_attempts:
                sleep(backoff + random.random())
                backoff = min(backoff * 2, 20)
            continue

        # Permanent client error (401 bad token, 403 bot blocked, 400 bad chat, ...)
        print(f"Telegram send failed permanently: {resp.status_code} {body}")
        return False

    print(f"Telegram send gave up after {max_attempts} attempts.")
    return False
