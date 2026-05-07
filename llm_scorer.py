"""
LLM utilities using Gemini 2.0 Flash Lite (Google AI Studio free tier: 1500 req/day).

- build_llm_score_map(): scores headlines 0-10 for strategic importance
- dedup_with_llm(): identifies true duplicate articles within each day
"""
import json
import logging
import os
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
_MAX_ARTICLES = 40
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

    now = datetime.now(timezone.utc)
    candidates = sorted(
        [a for a in articles if (now - a["date"]) < timedelta(hours=48)],
        key=lambda a: a["date"],
        reverse=True,
    )[:_MAX_ARTICLES]

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
    """Single Gemini call with a post-request sleep to respect the 30 RPM free tier."""
    resp = requests.post(
        f"{_GEMINI_URL}?key={GEMINI_API_KEY}",
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": max_tokens},
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    result = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    time.sleep(2.5)  # 30 RPM limit → 1 call per 2s; 2.5s gives comfortable headroom
    return result


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

    by_day: defaultdict[str, list[dict]] = defaultdict(list)
    for a in articles:
        by_day[a["date"].strftime("%Y-%m-%d")].append(a)

    kept: list[dict] = []
    total_removed = 0

    for day_key, day_arts in by_day.items():
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

    logger.info(f"LLM dedup: removed {total_removed} duplicates across {len(by_day)} days")
    return kept
