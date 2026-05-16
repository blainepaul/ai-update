"""
LLM utilities using Gemini 2.0 Flash Lite (Google AI Studio free tier: 1500 req/day).

- build_llm_score_map(): scores headlines 0-10 for strategic importance
- dedup_with_llm(): identifies true duplicate articles within each day
"""
import json
import logging
import os
import re
import time
import requests
from collections import defaultdict
from datetime import datetime, timezone, timedelta

from traction import _normalize_url

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash-lite:generateContent"
)
_BATCH_SIZE = 8
_MAX_ARTICLES = 60  # safety cap; actual filtering happens upstream in main.py
_TIMEOUT = 20

# Official sources — preferred when picking the canonical article within a cluster
_OFFICIAL_SOURCES = {
    "OpenAI Blog", "Anthropic Blog", "Google AI Blog", "DeepMind Blog", "HuggingFace Blog"
}

_PROMPT = """\
You are an expert AI industry analyst. Score each news headline 0-10 for \
strategic importance to AI professionals.

Scoring guide:
9-10: Major model release, flagship product launch, large acquisition/funding, \
key executive statement that shifts industry direction
7-8: Significant product update, notable partnership, important policy/regulation, \
major research paper
5-6: Relevant but incremental update, industry analysis worth reading
3-4: Opinion without new data, minor feature, tangentially related
0-2: Not relevant to the AI industry

Headlines:
{headlines}

Reply ONLY with a compact JSON array — one object per headline: \
[{{"i":0,"s":8}},{{"i":1,"s":5}},...] \
where "i" is the 0-based index and "s" is the integer score. No other text."""


def _parse_json_response(raw: str) -> list[dict]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def build_llm_score_map(articles: list[dict]) -> dict[str, float]:
    """
    Returns {normalized_url: llm_score (0-10)} for recent articles.
    Gracefully returns {} if GEMINI_API_KEY is unset or every batch fails.
    """
    if not GEMINI_API_KEY:
        logger.info("GEMINI_API_KEY not set — LLM scoring skipped")
        return {}

    # articles already pre-filtered and sorted by caller; apply safety cap
    candidates = articles[:_MAX_ARTICLES]

    scores: dict[str, float] = {}
    total_batches = (len(candidates) + _BATCH_SIZE - 1) // _BATCH_SIZE

    for b_idx in range(total_batches):
        batch = candidates[b_idx * _BATCH_SIZE : (b_idx + 1) * _BATCH_SIZE]
        headlines = "\n".join(f"{i}. {a['title']}" for i, a in enumerate(batch))
        prompt = _PROMPT.format(headlines=headlines)
        try:
            raw = _gemini_call(prompt, max_tokens=300)
            results = _parse_json_response(raw)
            for item in results:
                idx = item.get("i")
                s = float(item.get("s", 0))
                if idx is not None and 0 <= idx < len(batch):
                    key = _normalize_url(batch[idx].get("url", ""))
                    if key:
                        scores[key] = min(10.0, max(0.0, s))
        except Exception as exc:
            logger.warning(f"LLM scoring batch {b_idx + 1}/{total_batches} failed: {exc}")

    logger.info(f"LLM scoring: {len(scores)} articles scored ({len(candidates)} candidates)")
    return scores


def get_article_llm_score(article: dict, llm_map: dict) -> float:
    key = _normalize_url(article.get("url", ""))
    return llm_map.get(key, 0.0)


_DESCRIPTION_PROMPT = """\
You are an AI news editor writing for Italian readers. For each headline below, \
write ONE description in Italian of at most 140 characters (spaces included) that \
explains what the news is about. Be specific: mention companies, products, numbers \
when relevant. No filler phrases like "un articolo su" or "questa notizia riguarda".

Headlines:
{headlines}

Reply ONLY with a JSON array: [{{"i":0,"d":"descrizione"}},...]
where "i" is the 0-based index and "d" is the Italian description (max 140 chars). No other text."""

_WEEKLY_TOOLS_PROMPT = """\
You are an AI product editor writing for Italian readers. Below are {n} headlines \
from the past 7 days. Your task:

1. SELECT the 7 headlines that represent genuine new AI tool launches, product \
releases, or significant feature updates. Exclude pure news/analysis/funding \
stories that don't describe a specific tool or feature a user can actually use.
2. For each selected headline, provide:
   - d: description in Italian of at most 140 characters (spaces included). Specific and factual. No filler phrases.
   - c: category key from: productivity, audio, video, images, code, writing, search, agents, data, other
   - u: the official URL where users can access, install, or read the official \
announcement of the tool/feature (e.g. openai.com/blog/..., anthropic.com/news/..., \
platform.openai.com, gemini.google.com, etc.). If you are not confident about the \
exact URL, return null.

Headlines:
{headlines}

Reply ONLY with a JSON array of up to 7 objects: \
[{{"i":0,"d":"descrizione","c":"category","u":"https://... or null"}},...]
where "i" is the 0-based index from the list above. No other text."""


def build_top7_descriptions(highlights: list[dict]) -> None:
    """
    Generates 140-char Italian descriptions for the Top 7 highlights.
    Adds '_description' key to each article dict in-place.
    Silently skips if GEMINI_API_KEY is not set or API call fails.
    """
    if not GEMINI_API_KEY or not highlights:
        return
    headlines = "\n".join(f"{i}. {a['title']}" for i, a in enumerate(highlights))
    try:
        raw = _gemini_call(_DESCRIPTION_PROMPT.format(headlines=headlines), max_tokens=700)
        results = _parse_json_response(raw)
        for item in results:
            idx = item.get("i")
            desc = str(item.get("d", "")).strip()
            if idx is not None and 0 <= idx < len(highlights) and desc:
                highlights[idx]["_description"] = desc[:140]
        logger.info(f"Top 7 descriptions: {sum(1 for a in highlights if a.get('_description'))} generated")
    except Exception as exc:
        logger.warning(f"Top 7 descriptions failed: {exc}")


_TOOL_KEYWORDS = re.compile(
    r"launch|feature|update|release|introduc|announc|debut|unveil|present|integrat|"
    r"new model|new version|now available|rolls out|ships|plugin|extension|api|sdk|"
    r"lancia|annuncia|introduce|aggiorna|disponibil",
    re.IGNORECASE,
)


def _fetch_tools_feeds(max_age_days: int = 7) -> list[dict]:
    """Fetch recent articles from TOOLS_FEEDS (tracking platforms + company pages)."""
    import feedparser
    from config import TOOLS_FEEDS

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    articles = []
    for feed_info in TOOLS_FEEDS:
        try:
            feed = feedparser.parse(feed_info["url"])
            for entry in feed.entries[:30]:
                published = entry.get("published_parsed") or entry.get("updated_parsed")
                if published:
                    from calendar import timegm
                    date = datetime.utcfromtimestamp(timegm(published)).replace(tzinfo=timezone.utc)
                else:
                    date = datetime.now(timezone.utc)
                if date < cutoff:
                    continue
                title = entry.get("title", "").strip()
                url = entry.get("link", "").strip()
                if not title or not url:
                    continue
                articles.append({
                    "title":    title,
                    "url":      url,
                    "source":   feed_info["name"],
                    "date":     date,
                    "summary":  entry.get("summary", ""),
                    "category": "tools_products",
                })
            logger.debug(f"Tools feed '{feed_info['name']}': {len(feed.entries)} entries fetched")
        except Exception as exc:
            logger.warning(f"Tools feed failed ({feed_info['name']}): {exc}")
    logger.info(f"Tools feeds: {len(articles)} articles from {len(TOOLS_FEEDS)} feeds")
    return articles


def build_weekly_tools_section(articles: list[dict], traction_map: dict, llm_map: dict) -> list[dict]:
    """
    Picks the 7 most relevant tool/feature articles from the past 7 days.
    Candidates come from all categories (not just tools_products) filtered by
    tool/feature keywords, then scored; Gemini selects the final 7 and writes
    Italian descriptions + category labels.
    Returns a list of {title, url, source, description, category} dicts.
    """
    if not GEMINI_API_KEY:
        logger.info("GEMINI_API_KEY not set — weekly tools section skipped")
        return []

    from datetime import timedelta
    from renderer import _score as compute_score

    now = datetime.now(timezone.utc)

    # Broad candidate pool: tools_products OR any article with launch/feature keywords
    candidates = [
        a for a in articles
        if (now - a["date"]) < timedelta(days=7)
        and (
            a.get("category") == "tools_products"
            or _TOOL_KEYWORDS.search(a.get("title", ""))
        )
    ]

    # Add fresh articles from dedicated tools feeds (Product Hunt, TAAFT, company blogs…)
    tools_feed_articles = _fetch_tools_feeds(max_age_days=7)
    seen_urls = {a["url"] for a in candidates}
    for a in tools_feed_articles:
        if a["url"] not in seen_urls:
            candidates.append(a)
            seen_urls.add(a["url"])
    logger.info(f"Weekly tools candidate pool: {len(candidates)} articles total")

    if not candidates:
        logger.info("Weekly tools: no candidates in past 7 days")
        return []

    # Score and take top 30 to send to Gemini
    scored = sorted(candidates, key=lambda a: compute_score(a, now, traction_map, llm_map), reverse=True)[:30]
    headlines = "\n".join(f"{i}. {a['title']}" for i, a in enumerate(scored))

    try:
        raw = _gemini_call(
            _WEEKLY_TOOLS_PROMPT.format(n=len(scored), headlines=headlines),
            max_tokens=900,
        )
        results = _parse_json_response(raw)
        output = []
        for item in results:
            idx = item.get("i")
            if idx is None or not (0 <= idx < len(scored)):
                continue
            a = scored[idx]
            official_url = item.get("u")
            url = (
                official_url
                if official_url and isinstance(official_url, str) and official_url.startswith("http")
                else a["url"]
            )
            output.append({
                "title":       a["title"],
                "url":         url,
                "source":      a["source"],
                "description": str(item.get("d", "")).strip()[:140],
                "category":    item.get("c", "other"),
            })
        logger.info(f"Weekly tools section: {len(output)} items generated from {len(scored)} candidates")
        return output[:7]
    except Exception as exc:
        logger.warning(f"Weekly tools section failed: {exc}")
        return []


_DEDUP_PROMPT = """\
You are an AI news editor. The headlines below were all published on the same day.
Identify groups of headlines that cover THE EXACT SAME event or announcement \
(i.e. different outlets reporting on the identical news item).

DO NOT group:
- Follow-up articles or updates that add new information
- Articles about related but distinct events
- Articles sharing a general topic but reporting different angles

Only group true duplicates: same event, multiple sources, no new information added.

Headlines:
{headlines}

Reply ONLY with a JSON array of clusters (arrays of 0-based indices).
Only include groups with 2+ articles. Return [] if no duplicates exist.
Example: [[0,2],[4,5,7]]
No other text."""


def _gemini_call(prompt: str, max_tokens: int = 400) -> str:
    """Single Gemini call, paced to respect the 30 RPM free tier. Retries on 429."""
    time.sleep(2.5)  # pre-call delay: 2.5s → max 24 RPM, safely under 30 RPM limit
    retry_delays = [15, 45]  # wait 15s then 45s before giving up
    attempt = 0
    while True:
        resp = requests.post(
            f"{_GEMINI_URL}?key={GEMINI_API_KEY}",
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0, "maxOutputTokens": max_tokens},
            },
            timeout=_TIMEOUT,
        )
        if resp.status_code == 429 and attempt < len(retry_delays):
            try:
                detail = resp.json().get("error", {}).get("message", "")
            except Exception:
                detail = resp.text[:200]
            delay = retry_delays[attempt]
            logger.warning(f"Gemini 429 (attempt {attempt + 1}): {detail} — retrying in {delay}s")
            time.sleep(delay)
            attempt += 1
            continue
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


def dedup_with_llm(articles: list[dict]) -> list[dict]:
    """
    Remove true duplicate articles (same event, multiple sources) within each day.
    Uses Gemini to distinguish duplicates from updates/follow-ups.
    Falls back to keyword-based dedup (renderer.dedup_articles) if no API key.
    """
    if not GEMINI_API_KEY:
        logger.info("GEMINI_API_KEY not set — falling back to keyword dedup")
        from renderer import dedup_articles
        return dedup_articles(articles)

    from renderer import dedup_articles as kw_dedup

    by_day: defaultdict[str, list[dict]] = defaultdict(list)
    for a in articles:
        by_day[a["date"].strftime("%Y-%m-%d")].append(a)

    # LLM dedup only for today — older days use fast keyword dedup (no API quota spent)
    today_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    kept: list[dict] = []
    total_removed = 0

    for day_key, day_arts in by_day.items():
        if day_key != today_key:
            kept.extend(kw_dedup(day_arts))
            continue

        if len(day_arts) <= 1:
            kept.extend(day_arts)
            continue

        # Indices to drop (duplicates that lost to a better canonical article)
        drop_ids: set[int] = set()

        # Process in batches of 40 (prompt stays well under token limits)
        for b_start in range(0, len(day_arts), 40):
            batch = day_arts[b_start : b_start + 40]
            headlines = "\n".join(f"{i}. {a['title']}" for i, a in enumerate(batch))
            try:
                raw = _gemini_call(_DEDUP_PROMPT.format(headlines=headlines))
                clusters = _parse_json_response(raw)
                if not isinstance(clusters, list):
                    raise ValueError("unexpected response shape")
                for cluster in clusters:
                    if not isinstance(cluster, list) or len(cluster) < 2:
                        continue
                    # Resolve global indices
                    global_cluster = [b_start + i for i in cluster if 0 <= i < len(batch)]
                    if len(global_cluster) < 2:
                        continue
                    # Keep official source, then most recent; drop the rest
                    best_idx = max(
                        global_cluster,
                        key=lambda gi: (
                            day_arts[gi]["source"] in _OFFICIAL_SOURCES,
                            day_arts[gi]["date"],
                        ),
                    )
                    for gi in global_cluster:
                        if gi != best_idx:
                            drop_ids.add(gi)
            except Exception as exc:
                logger.warning(f"LLM dedup failed for {day_key} batch {b_start//40+1}: {exc}")

        removed = len(drop_ids)
        total_removed += removed
        kept.extend(a for i, a in enumerate(day_arts) if i not in drop_ids)

    logger.info(f"LLM dedup: removed {total_removed} duplicates (LLM for today, keyword for older days)")
    return kept
