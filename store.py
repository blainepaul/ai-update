import json
import os
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STORE_PATH = os.path.join(BASE_DIR, "cache", "articles.json")
MAX_STORE_DAYS = 7


def _ensure_tz(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def load() -> list[dict]:
    if not os.path.exists(STORE_PATH):
        return []
    try:
        with open(STORE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for article in data:
            if isinstance(article["date"], str):
                article["date"] = _ensure_tz(datetime.fromisoformat(article["date"]))
        logger.info(f"Loaded {len(data)} articles from store")
        return data
    except Exception as exc:
        logger.error(f"Failed to load store: {exc}")
        return []


def save(articles: list[dict]) -> None:
    os.makedirs(os.path.dirname(STORE_PATH), exist_ok=True)
    serializable = []
    for article in articles:
        a = article.copy()
        if isinstance(a["date"], datetime):
            a["date"] = a["date"].isoformat()
        serializable.append(a)
    try:
        with open(STORE_PATH, "w", encoding="utf-8") as f:
            json.dump(serializable, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(articles)} articles to store")
    except Exception as exc:
        logger.error(f"Failed to save store: {exc}")


def merge(existing: list[dict], new_articles: list[dict]) -> list[dict]:
    seen_urls = {a["url"] for a in existing}
    added = 0
    for article in new_articles:
        if article["url"] not in seen_urls:
            existing.append(article)
            seen_urls.add(article["url"])
            added += 1
    logger.info(f"Merged: +{added} new articles (total in store: {len(existing)})")
    return existing


def purge_old(articles: list[dict]) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_STORE_DAYS)
    before = len(articles)
    kept = [a for a in articles if _ensure_tz(a["date"]) >= cutoff]
    removed = before - len(kept)
    if removed:
        logger.info(f"Purged {removed} articles older than {MAX_STORE_DAYS} days")
    return kept
