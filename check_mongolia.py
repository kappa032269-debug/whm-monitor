#!/usr/bin/env python3
"""
Mongolia Work and Holiday (subclass 462) cap monitor.

Checks the Australian Home Affairs "Status of country caps" page, reads the
Mongolia row, and sends Telegram alerts:
  - Immediately (3 messages) when Mongolia changes to OPEN
  - A reminder every 30 minutes while it stays OPEN
  - When the status changes to anything else (closed, ballot, unknown...)
  - If the monitor itself keeps failing (so it never breaks silently)
  - A silent daily check-in at ~09:00 Ulaanbaatar time ("still watching")

Environment variables:
  TELEGRAM_BOT_TOKEN  (required)  token from @BotFather
  TELEGRAM_CHAT_ID    (optional)  auto-detected if you message the bot first
  SEND_TEST           (optional)  "true" sends a test message with current status
"""

import html
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ----------------------------------------------------------------- settings --
PAGE_URL = "https://immi.homeaffairs.gov.au/what-we-do/whm-program/status-of-country-caps"
FALLBACK_URL = "https://r.jina.ai/" + PAGE_URL  # reader proxy, used only if direct fetch fails
APPLY_INFO_URL = ("https://immi.homeaffairs.gov.au/visas/getting-a-visa/"
                  "visa-listing/work-holiday-462/first-work-holiday-462")
IMMI_ACCOUNT_URL = "https://online.immi.gov.au/ola/app"
COUNTRY = "mongolia"

STATE_FILE = Path(__file__).resolve().with_name("state.json")
UB_TZ = timezone(timedelta(hours=8))  # Ulaanbaatar, UTC+8, no daylight saving

HEARTBEAT_HOUR_UB = 9          # daily silent check-in after this hour (UB time)
OPEN_REMINDER_MINUTES = 30     # repeat alert while status stays open
OPEN_BURST_MESSAGES = 3        # number of messages sent when it first opens
FAILURE_ALERT_AFTER = 3        # consecutive failed checks before warning you
FAILURE_REPEAT_HOURS = 6       # repeat the failure warning at most this often

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

LABELS = {
    "open": "🟢 OPEN",
    "paused": "⏸ Paused",
    "closed": "🔴 Closed",
    "ballot": "🎟 Ballot",
    "unknown": "❓ Unknown",
}

# The page is full of zero-width spaces, so strip them before reading text.
_INVISIBLE = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"), None)


# ------------------------------------------------------------------ parsing --
def clean(text: str) -> str:
    text = (text or "").translate(_INVISIBLE).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def classify(raw: str) -> str:
    t = clean(raw).lower()
    if "ballot" in t:
        return "ballot"
    if "pause" in t:
        return "paused"
    if "close" in t:
        return "closed"
    if "open" in t:
        return "open"
    return "unknown"


def parse_html(page: str):
    """Return the raw status text of the Mongolia row from the page HTML, or None."""
    soup = BeautifulSoup(page, "html.parser")
    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) >= 2 and clean(cells[0].get_text(" ")).lower() == COUNTRY:
            return clean(cells[1].get_text(" "))
    return None


def parse_markdown(page: str):
    """Same as parse_html, for the markdown returned by the fallback reader."""
    for line in page.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        parts = [clean(p) for p in line.strip("|").split("|")]
        if len(parts) >= 2 and parts[0].lower() == COUNTRY:
            return parts[1]
    return None


def parse_last_updated(page: str):
    m = re.search(r"Last updated:\s*([0-9/]+\s+[0-9:]+\s*[AP]M)", clean(page))
    return m.group(1) if m else None


def fetch_status():
    """Fetch the page and return a dict with the Mongolia status. Raises on failure."""
    errors = []
    attempts = [(PAGE_URL, parse_html, "direct"), (PAGE_URL, parse_html, "direct"),
                (FALLBACK_URL, parse_markdown, "fallback")]
    for i, (url, parser, source) in enumerate(attempts):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            raw = parser(r.text)
            if raw is None:
                raise RuntimeError("Mongolia row not found on page (layout may have changed)")
            return {
                "status": classify(raw),
                "raw": raw,
                "source": source,
                "last_updated": parse_last_updated(r.text),
            }
        except Exception as exc:  # noqa: BLE001 - we want every failure reason
            errors.append(f"{source}: {exc}")
            if i < len(attempts) - 1:
                time.sleep(3)
    raise RuntimeError(" | ".join(errors))


# ----------------------------------------------------------------- telegram --
TG_ATTEMPTS = 3  # retry Telegram calls on network errors/timeouts


def tg(token: str, method: str, **params):
    last_exc = None
    for attempt in range(1, TG_ATTEMPTS + 1):
        try:
            r = requests.post(f"https://api.telegram.org/bot{token}/{method}",
                              json=params, timeout=30)
            break
        except requests.RequestException as exc:
            last_exc = exc
            print(f"Telegram {method} attempt {attempt}/{TG_ATTEMPTS} failed: {exc}")
            if attempt < TG_ATTEMPTS:
                time.sleep(5 * attempt)
    else:
        raise RuntimeError(f"Telegram {method}: failed after {TG_ATTEMPTS} attempts: {last_exc}")
    try:
        data = r.json()
    except ValueError:
        raise RuntimeError(f"Telegram {method}: HTTP {r.status_code}") from None
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method}: {data.get('description', 'unknown error')}")
    return data["result"]


def send(token: str, chat_id, text: str, silent: bool = False):
    tg(token, "sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
       disable_web_page_preview=True, disable_notification=silent)


def discover_chat_id(token: str):
    """Find your chat ID from the most recent message you sent the bot."""
    for update in reversed(tg(token, "getUpdates")):
        msg = update.get("message") or update.get("edited_message")
        if msg and "chat" in msg:
            return msg["chat"]["id"]
    return None


# -------------------------------------------------------------------- state --
def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M") + " (UB time)"


def minutes_since(iso: str, now: datetime) -> float:
    try:
        return (now - datetime.fromisoformat(iso)).total_seconds() / 60
    except (TypeError, ValueError):
        return float("inf")


# ----------------------------------------------------------------- messages --
def status_block(result: dict, now: datetime) -> str:
    lines = [f"Status: <b>{LABELS[result['status']]}</b> "
             f"(page text: “{html.escape(result['raw'])}”)"]
    if result.get("last_updated"):
        lines.append(f"Page last updated: {html.escape(result['last_updated'])} (Canberra time)")
    lines.append(f"Checked: {fmt(now)}")
    return "\n".join(lines)


def open_alert(result: dict, now: datetime, reminder: bool = False) -> str:
    head = ("⏰ REMINDER: Mongolia is STILL OPEN" if reminder
            else "🚨🚨 MONGOLIA WORK &amp; HOLIDAY (462) IS OPEN! 🚨🚨")
    return (f"{head}\n\nApply now — the annual cap is only ~100 places.\n\n"
            f"{status_block(result, now)}\n\n"
            f"👉 <a href=\"{IMMI_ACCOUNT_URL}\">Log in to ImmiAccount</a>\n"
            f"ℹ️ <a href=\"{APPLY_INFO_URL}\">Visa info &amp; requirements</a>\n"
            f"📄 <a href=\"{PAGE_URL}\">Status page</a>")


# --------------------------------------------------------------------- main --
def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN secret is missing. See README step 3.")
        return 1

    state = load_state()
    now = datetime.now(UB_TZ)
    today = now.date().isoformat()

    # --- make sure we know where to send messages
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip() or state.get("chat_id")
    if not chat_id:
        chat_id = discover_chat_id(token)
        if not chat_id:
            print("ERROR: No chat found. Open your bot in Telegram, press START "
                  "(or send it any message), then run the workflow again.")
            return 1
        state["chat_id"] = chat_id
        save_state(state)
        send(token, chat_id, "✅ Connected! This chat will receive Mongolia WHM cap alerts.")

    # --- check the page
    try:
        result = fetch_status()
    except Exception as exc:  # noqa: BLE001
        fails = state.get("consecutive_failures", 0) + 1
        state["consecutive_failures"] = fails
        print(f"Check failed ({fails} in a row): {exc}")
        if fails >= FAILURE_ALERT_AFTER and \
                minutes_since(state.get("last_failure_alert"), now) >= FAILURE_REPEAT_HOURS * 60:
            send(token, chat_id,
                 f"⚠️ Monitor problem: the last {fails} checks failed, so I can't see "
                 f"Mongolia's status right now.\n\nError: <code>{html.escape(str(exc)[:600])}</code>"
                 f"\n\nCheck the page manually until this is fixed:\n{PAGE_URL}")
            state["last_failure_alert"] = now.isoformat()
        if os.environ.get("SEND_TEST", "").lower() == "true":
            send(token, chat_id, f"🧪 Test message: Telegram works, but the page check "
                                 f"failed:\n<code>{html.escape(str(exc)[:600])}</code>")
        save_state(state)
        return 0

    status = result["status"]
    print(f"Mongolia status: {status} (raw: {result['raw']!r}, source: {result['source']}, "
          f"page updated: {result['last_updated']})")

    # --- recovered from failures
    if state.get("consecutive_failures", 0) >= FAILURE_ALERT_AFTER:
        send(token, chat_id, "✅ Monitor recovered — checks are working again.\n\n"
                             + status_block(result, now))
    state["consecutive_failures"] = 0
    state.pop("last_failure_alert", None)

    prev = state.get("status")
    first_run = prev is None
    changed = not first_run and status != prev

    if first_run:
        send(token, chat_id,
             "👀 Monitor started. I'll check Mongolia's Work &amp; Holiday cap every few "
             "minutes and alert you the moment it opens.\n\n" + status_block(result, now))
        if now.hour >= HEARTBEAT_HOUR_UB:
            state["last_heartbeat_date"] = today

    if status == "open" and (first_run or changed):
        for _ in range(OPEN_BURST_MESSAGES):
            send(token, chat_id, open_alert(result, now))
            time.sleep(2)
        state["last_open_alert"] = now.isoformat()
    elif status == "open":
        if minutes_since(state.get("last_open_alert"), now) >= OPEN_REMINDER_MINUTES:
            send(token, chat_id, open_alert(result, now, reminder=True))
            state["last_open_alert"] = now.isoformat()
    elif changed:
        note = {
            "closed": "Closed means all places for this program year are filled; "
                      "it reopens on 2 July.",
            "ballot": "Mongolia has moved to a ballot system — check the page for "
                      "registration instructions.",
            "paused": "It's paused again. I'll keep watching.",
            "unknown": "The status text is something I don't recognise — please check the page.",
        }.get(status, "")
        send(token, chat_id,
             f"ℹ️ Mongolia status changed: {LABELS.get(prev, prev)} → <b>{LABELS[status]}</b>\n"
             f"{note}\n\n{status_block(result, now)}\n\n📄 {PAGE_URL}")

    if changed or first_run:
        state["status"] = status
        state["status_since"] = now.isoformat()
    if status != "open":
        state.pop("last_open_alert", None)

    # --- daily silent check-in, so you know the monitor is still alive
    if now.hour >= HEARTBEAT_HOUR_UB and state.get("last_heartbeat_date") != today:
        try:
            send(token, chat_id, "☀️ Daily check-in: still watching.\n\n" + status_block(result, now),
                 silent=True)
            state["last_heartbeat_date"] = today
        except Exception as exc:  # noqa: BLE001 - a missed check-in must not fail the run
            print(f"Daily check-in not sent (will retry next run): {exc}")

    # --- manual test
    if os.environ.get("SEND_TEST", "").lower() == "true":
        send(token, chat_id, "🧪 Test message: everything works.\n\n" + status_block(result, now))

    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
