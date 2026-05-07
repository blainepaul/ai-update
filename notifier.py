"""Sends a Telegram message (twice a day) with the top 5 highlights and site link."""
import html
import json
import logging
import os
import requests
from datetime import datetime, timezone
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SITE_URL, CATEGORY_LABELS, CATEGORY_ICONS

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SENT_FLAG = os.path.join(BASE_DIR, "cache", "last_notified.txt")

_SLOT_HEADER = {
    "morning":   "🌅 AI News — Top 5 di questa mattina",
    "afternoon": "🌆 AI News — Top 5 di questo pomeriggio",
}


def _current_slot() -> str:
    return "morning" if datetime.now(timezone.utc).hour < 12 else "afternoon"


def _already_sent_today() -> bool:
    """Returns True if a notification was already sent for this slot today."""
    try:
        with open(SENT_FLAG) as f:
            flags = json.load(f)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return flags.get(_current_slot()) == today
    except (FileNotFoundError, ValueError):
        return False


def _mark_sent_today():
    os.makedirs(os.path.dirname(SENT_FLAG), exist_ok=True)
    try:
        with open(SENT_FLAG) as f:
            flags = json.load(f)
    except (FileNotFoundError, ValueError):
        flags = {}
    flags[_current_slot()] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with open(SENT_FLAG, "w") as f:
        json.dump(flags, f)


def _escape(text: str) -> str:
    """Escape HTML special chars for Telegram HTML mode."""
    return html.escape(str(text))


def send_highlights(highlights: list[dict]) -> bool:
    """
    Sends a Telegram message with the top 5 highlights.
    Returns True on success, False if credentials missing or request fails.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.info("Telegram credentials not set — skipping notification")
        return False

    if _already_sent_today():
        logger.info("Telegram notification already sent today — skipping duplicate")
        return False

    header = _SLOT_HEADER.get(_current_slot(), "🔥 AI News — Top 5")
    lines = [f"<b>{header}</b>\n"]
    for i, article in enumerate(highlights, 1):
        cat_key  = article.get("category", "other")
        cat_icon = CATEGORY_ICONS.get(cat_key, "📌")
        cat_label = CATEGORY_LABELS.get(cat_key, "Altro")
        title  = _escape(article["title"])
        source = _escape(article["source"])
        url    = article["url"]
        lines.append(
            f'{i}. <a href="{url}">{title}</a>\n'
            f'   <i>{source} · {cat_icon} {cat_label}</i>'
        )

    lines.append(f'\n📰 <a href="{SITE_URL}">Apri il sito completo</a>')
    message = "\n\n".join(lines)

    try:
        resp = requests.post(
            TELEGRAM_API.format(token=TELEGRAM_BOT_TOKEN),
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        resp.raise_for_status()
        _mark_sent_today()
        logger.info("Telegram notification sent successfully")
        return True
    except Exception as exc:
        logger.error(f"Telegram notification failed: {exc}")
        return False
