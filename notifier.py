"""Sends a daily Telegram message with the top 5 highlights and site link."""
import html
import logging
import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SITE_URL, CATEGORY_LABELS, CATEGORY_ICONS

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


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

    lines = ["<b>🔥 AI News — Top 5 di oggi</b>\n"]
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
        logger.info("Telegram notification sent successfully")
        return True
    except Exception as exc:
        logger.error(f"Telegram notification failed: {exc}")
        return False
