"""
Fetches real-world traction data from Hacker News and Reddit
to score articles by actual online engagement.
"""
import re
import logging
import requests
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "AI News Aggregator/1.0 (personal use)"}
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
    """Returns {normalized_url: reddit_score} from AI subreddits."""
    scores: dict[str, float] = {}
    for sub in REDDIT_TRACTION_SUBS:
        try:
            resp = requests.get(
                REDDIT_JSON.format(sub=sub),
                headers=HEADERS, timeout=TIMEOUT,
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


def build_traction_map() -> dict[str, float]:
    """
    Returns {normalized_url: combined_traction_score}.
    Combines HN + Reddit scores, normalized to 0-10 range.
    """
    hn = _fetch_hn()
    reddit = _fetch_reddit_traction()

    combined: dict[str, float] = {}
    for url, score in hn.items():
        combined[url] = combined.get(url, 0) + score
    for url, score in reddit.items():
        combined[url] = combined.get(url, 0) + score

    if not combined:
        return {}

    # Normalize to 0-10 so traction doesn't dwarf keyword scores
    max_score = max(combined.values())
    if max_score > 0:
        combined = {url: (s / max_score) * 10 for url, s in combined.items()}

    logger.info(f"Traction map built: {len(combined)} total URLs")
    return combined


def get_article_traction(article: dict, traction_map: dict[str, float]) -> float:
    """Look up a single article's traction score."""
    key = _normalize_url(article.get("url", ""))
    return traction_map.get(key, 0.0)
