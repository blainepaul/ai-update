import warnings
import feedparser
import requests
import logging
from datetime import datetime, timezone, timedelta
from dateutil import parser as dateparser
from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from config import (
    FEEDS, GENERIC_FEEDS, AI_KEYWORDS, REDDIT_SOURCES,
    MAX_ARTICLES_PER_FEED, FETCH_TIMEOUT_SECONDS, MAX_AGE_HOURS,
)

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (AI News Aggregator; personal use)"}


def _is_ai_relevant(title: str, summary: str) -> bool:
    text = (title + " " + summary).lower()
    return any(kw in text for kw in AI_KEYWORDS)


def _normalize_date(entry) -> datetime:
    for attr in ("published", "updated", "created"):
        raw = getattr(entry, attr, None)
        if raw:
            try:
                dt = dateparser.parse(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                pass
    return datetime.now(timezone.utc)


def _parse_summary(entry) -> str:
    def _clean(raw: str) -> str:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)
            return BeautifulSoup(raw, "html.parser").get_text(separator=" ", strip=True)[:500]

    raw = getattr(entry, "summary", None)
    if raw:
        return _clean(raw)
    if hasattr(entry, "content") and entry.content:
        return _clean(entry.content[0].value)
    return ""


@retry(
    retry=retry_if_exception_type((requests.exceptions.ConnectionError, requests.exceptions.Timeout)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _fetch_raw(url: str):
    resp = requests.get(url, timeout=FETCH_TIMEOUT_SECONDS, headers=HEADERS)
    resp.raise_for_status()
    return feedparser.parse(resp.content)


def fetch_all_articles() -> list[dict]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=MAX_AGE_HOURS)
    all_articles = []
    seen_urls: set[str] = set()

    for feed_cfg in FEEDS:
        name = feed_cfg["name"]
        url = feed_cfg["url"]
        logger.info(f"Fetching: {name}")

        try:
            parsed = _fetch_raw(url)
        except Exception as exc:
            logger.warning(f"SKIP {name}: {exc}")
            continue

        if not parsed.entries:
            logger.warning(f"SKIP {name}: no entries in feed")
            continue

        count = 0
        for entry in parsed.entries:
            if count >= MAX_ARTICLES_PER_FEED:
                break

            link = getattr(entry, "link", "").strip()
            if not link or link in seen_urls:
                continue

            title = getattr(entry, "title", "").strip()
            if not title:
                continue

            summary = _parse_summary(entry)
            pub_date = _normalize_date(entry)

            if pub_date < cutoff:
                continue

            if name in GENERIC_FEEDS and not _is_ai_relevant(title, summary):
                continue

            seen_urls.add(link)
            all_articles.append({
                "title":    title,
                "url":      link,
                "summary":  summary,
                "source":   name,
                "date":     pub_date,
                "category": None,
            })
            count += 1

        logger.info(f"  -> {count} articles from {name}")

    # Reddit link posts from curated AI subreddits
    reddit_articles = fetch_reddit_articles(seen_urls, cutoff)
    all_articles.extend(reddit_articles)

    all_articles.sort(key=lambda a: a["date"], reverse=True)
    logger.info(f"Total articles fetched: {len(all_articles)}")
    return all_articles


def fetch_reddit_articles(seen_urls: set[str], cutoff: datetime) -> list[dict]:
    """
    Fetches top link posts from curated AI subreddits.
    Only includes posts with an external URL and score >= MIN_SCORE.
    """
    articles = []
    reddit_headers = {
        "User-Agent": "AI News Aggregator/1.0 (personal use)",
        "Accept": "application/json",
    }

    for cfg in REDDIT_SOURCES:
        sub = cfg["sub"]
        min_score = cfg.get("min_score", 20)
        url = f"https://www.reddit.com/r/{sub}/top/.json?t=day&limit=50"
        logger.info(f"Fetching Reddit: r/{sub}")
        try:
            resp = requests.get(url, headers=reddit_headers, timeout=FETCH_TIMEOUT_SECONDS)
            resp.raise_for_status()
            posts = resp.json().get("data", {}).get("children", [])
        except Exception as exc:
            logger.warning(f"SKIP r/{sub}: {exc}")
            continue

        count = 0
        for post in posts:
            d = post.get("data", {})
            # Only link posts (not self/text posts)
            if d.get("is_self"):
                continue
            ext_url = d.get("url", "").strip()
            if not ext_url or ext_url in seen_urls:
                continue
            # Skip Reddit-internal links
            if "reddit.com" in ext_url or "redd.it" in ext_url:
                continue
            score = d.get("score", 0)
            if score < min_score:
                continue

            title = d.get("title", "").strip()
            if not title:
                continue

            created = d.get("created_utc")
            pub_date = (datetime.fromtimestamp(created, tz=timezone.utc)
                        if created else datetime.now(timezone.utc))
            if pub_date < cutoff:
                continue

            seen_urls.add(ext_url)
            articles.append({
                "title":    title,
                "url":      ext_url,
                "summary":  d.get("selftext", "")[:300],
                "source":   f"Reddit r/{sub}",
                "date":     pub_date,
                "category": None,
            })
            count += 1
            if count >= MAX_ARTICLES_PER_FEED:
                break

        logger.info(f"  -> {count} articles from r/{sub}")

    return articles
