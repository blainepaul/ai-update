"""
Scores article headlines by strategic importance using Gemini 2.0 Flash Lite
(Google AI Studio free tier: 1500 req/day, no credit card needed).
Returns {normalized_url: score 0-10}.
"""
import json
import logging
import os
import requests
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
            resp = requests.post(
                f"{_GEMINI_URL}?key={GEMINI_API_KEY}",
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0, "maxOutputTokens": 300},
                },
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
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
