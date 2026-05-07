"""
Fetches real-world traction data from Hacker News and Reddit
to score articles by actual online engagement.
"""
import json
import os
import re
import logging
import requests
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

from reddit_auth import get_reddit_headers

logger = logging.getLogger(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(BASE_DIR, "cache", "traction_history.json")
HISTORY_MAX_POINTS = 14

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0"}
TIMEOUT = 8

# HN via Algolia API — single call, returns scored stories
HN_ALGOLIA = "https://hn.algolia.com/api/v1/search?tags=story&hitsPerPage=60&query=artificial+intelligence+OR+AI+OR+LLM+OR+OpenAI+OR+Anthropic+OR+machine+learning"

# Reddit subreddits for traction data
REDDIT_TRACTION_SUBS = [
    "artificial",
    "MachineLearning",
    "LocalLLaMA",
    "singularity",
    "AINews",
]
REDDIT_JSON = "https://www.reddit.com/r/{sub}/top/.json?t=day&limit=50"


def _normalize_url(url: str) -> str:
    """Strip scheme, www, trailing slash, and utm_* params for comparison."""
    try:
        p = urlparse(url.lower().strip())
        host = p.netloc.removeprefix("www.")
        # Remove tracking params
        qs = {k: v for k, v in parse_qs(p.query).items()
              if not k.startswith("utm_")}
        clean_query = urlencode(qs, doseq=True)
        clean = urlunparse(("", host, p.path.rstrip("/"), "", clean_query, ""))
        return clean
    except Exception:
        return url.lower().strip()


def _fetch_hn() -> dict[str, float]:
    """Returns {normalized_url: hn_score}."""
    scores: dict[str, float] = {}
    try:
        resp = requests.get(HN_ALGOLIA, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
        for hit in hits:
            url = hit.get("url")
            points = hit.get("points") or 0
            comments = hit.get("num_comments") or 0
            if url and points > 0:
                score = points + comments * 0.5
                key = _normalize_url(url)
                scores[key] = max(scores.get(key, 0), score)
        logger.info(f"HN traction: {len(scores)} URLs scored")
    except Exception as exc:
        logger.warning(f"HN traction fetch failed: {exc}")
    return scores


def _fetch_reddit_traction() -> dict[str, float]:
    """Returns {normalized_url: reddit_score} from AI subreddits via OAuth API."""
    headers = get_reddit_headers()
    if not headers:
        return {}

    scores: dict[str, float] = {}
    for sub in REDDIT_TRACTION_SUBS:
        try:
            resp = requests.get(
                f"https://oauth.reddit.com/r/{sub}/top?t=day&limit=50",
                headers=headers,
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            posts = resp.json().get("data", {}).get("children", [])
            for post in posts:
                d = post.get("data", {})
                url = d.get("url", "")
                score = (d.get("score") or 0) + (d.get("num_comments") or 0) * 0.5
                if url and not d.get("is_self") and score > 0:
                    key = _normalize_url(url)
                    scores[key] = max(scores.get(key, 0), score)
        except Exception as exc:
            logger.warning(f"Reddit traction r/{sub} failed: {exc}")
    logger.info(f"Reddit traction: {len(scores)} URLs scored")
    return scores


# Google Trends: fixed batch of AI terms queried each run
# Maps search term (Google Trends) → substrings to match in article titles
_TRENDS_TERMS = [
    ["ChatGPT", "OpenAI", "Anthropic", "Gemini", "Claude"],
    ["DeepMind", "xAI", "Mistral", "NVIDIA", "Grok"],
    ["AI regulation", "AI safety", "LLM", "AI model", "artificial intelligence"],
]
_TRENDS_TITLE_MAP: dict[str, list[str]] = {
    "chatgpt":               ["chatgpt"],
    "openai":                ["openai", "open ai"],
    "anthropic":             ["anthropic"],
    "gemini":                ["gemini"],
    "claude":                ["claude"],
    "deepmind":              ["deepmind"],
    "xai":                   ["xai", "x.ai", "grok"],
    "mistral":               ["mistral"],
    "nvidia":                ["nvidia"],
    "grok":                  ["grok"],
    "ai regulation":         ["ai regulation", "ai act", "eu ai"],
    "ai safety":             ["ai safety", "alignment"],
    "llm":                   ["llm", "language model"],
    "ai model":              ["ai model", "new model"],
    "artificial intelligence": ["artificial intelligence"],
}


def _fetch_google_trends() -> dict[str, float]:
    """
    Returns {term_lowercase: score_0_to_100} for AI keywords over the last 24h.
    Uses pytrends (unofficial Google Trends wrapper, no API key required).
    Gracefully returns {} on any failure.
    """
    try:
        import time
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl="en-US", tz=0, timeout=(10, 30))
        scores: dict[str, float] = {}
        for batch in _TRENDS_TERMS:
            try:
                pytrends.build_payload(batch, timeframe="now 1-d", geo="")
                df = pytrends.interest_over_time()
                if not df.empty:
                    for term in batch:
                        if term in df.columns:
                            scores[term.lower()] = float(df[term].mean())
                time.sleep(2)  # avoid rate-limiting
            except Exception as exc:
                logger.warning(f"Google Trends batch {batch[0]}… failed: {exc}")
        logger.info(f"Google Trends: {len(scores)} terms scored")
        return scores
    except ImportError:
        logger.warning("pytrends not installed — Google Trends skipped")
        return {}
    except Exception as exc:
        logger.warning(f"Google Trends failed: {exc}")
        return {}


def _trends_score_for_article(article: dict, trends: dict[str, float]) -> float:
    """Returns the highest Google Trends score (0-100) matching the article title."""
    if not trends:
        return 0.0
    title = article.get("title", "").lower()
    best = 0.0
    for term, patterns in _TRENDS_TITLE_MAP.items():
        if term in trends and any(p in title for p in patterns):
            best = max(best, trends[term])
    return best


def build_traction_map(articles: list[dict] | None = None) -> dict[str, float]:
    """
    Returns {normalized_url: combined_traction_score}, normalized to 0-10.
    Sources: HN (1x) + Reddit OAuth (2x) + Google Trends (1x, keyword-matched).
    """
    hn = _fetch_hn()
    reddit = _fetch_reddit_traction()
    trends = _fetch_google_trends()

    combined: dict[str, float] = {}
    for url, score in hn.items():
        combined[url] = combined.get(url, 0) + score
    for url, score in reddit.items():
        combined[url] = combined.get(url, 0) + score * 2.0

    # Google Trends: map keyword popularity back to each article URL
    if trends and articles:
        for article in articles:
            t_score = _trends_score_for_article(article, trends)
            if t_score > 0:
                url = _normalize_url(article.get("url", ""))
                if url:
                    combined[url] = combined.get(url, 0) + t_score

    if not combined:
        return {}

    max_score = max(combined.values())
    if max_score > 0:
        combined = {url: (s / max_score) * 10 for url, s in combined.items()}

    logger.info(f"Traction map built: {len(combined)} total URLs")
    return combined


def save_traction_history(traction_map: dict[str, float]) -> dict:
    """Append current run's scores to per-URL history. Returns the full history."""
    try:
        with open(HISTORY_FILE) as f:
            history = json.load(f)
    except (FileNotFoundError, ValueError):
        history = {}

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
    for url, score in traction_map.items():
        entry = {"ts": ts, "score": round(score, 2)}
        history.setdefault(url, []).append(entry)
        history[url] = history[url][-HISTORY_MAX_POINTS:]

    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, separators=(",", ":"))
    return history


def load_traction_history() -> dict:
    try:
        with open(HISTORY_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def get_article_traction(article: dict, traction_map: dict[str, float]) -> float:
    """Look up a single article's traction score."""
    key = _normalize_url(article.get("url", ""))
    return traction_map.get(key, 0.0)


def get_article_history(article: dict, history: dict) -> list[dict]:
    """Returns list of {ts, score} data points for a given article."""
    key = _normalize_url(article.get("url", ""))
    return history.get(key, [])
