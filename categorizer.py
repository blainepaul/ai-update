import json
import logging
import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential
from config import ANTHROPIC_API_KEY, CATEGORIES, CLAUDE_MODEL, CATEGORIZATION_BATCH_SIZE

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an AI news categorization assistant.
Given a list of AI-related news article titles and summaries, classify each one into exactly one of these categories:

- models_research: New AI models, research papers, benchmarks, training techniques
- tools_products: Software tools, APIs, applications, product launches, features
- policy_regulation: Laws, government policy, regulations, hearings, compliance
- business_investment: Funding, acquisitions, partnerships, revenue, market analysis
- ethics_safety: AI safety, alignment, bias, misuse, deepfakes, societal impact
- healthcare: Medical AI applications, drug discovery, diagnostics, clinical trials
- creativity: Art, music, writing, video generation, creative AI applications
- other: Anything that does not fit the above categories

Respond ONLY with a JSON array where each element is: {"index": <integer>, "category": "<category_key>"}
No explanations. No markdown fences. Only the raw JSON array."""


def _build_user_message(batch: list[dict], offset: int) -> str:
    lines = []
    for i, article in enumerate(batch):
        lines.append(f'[{offset + i}] Title: {article["title"]}')
        if article["summary"]:
            lines.append(f'    Summary: {article["summary"][:200]}')
    return "\n".join(lines)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=5, max=30))
def _call_claude(client: anthropic.Anthropic, user_message: str) -> list[dict]:
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    raw = response.content[0].text.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:].strip()
    return json.loads(raw)


def categorize_articles(articles: list[dict]) -> list[dict]:
    if not ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY not set — skipping categorization, all articles -> 'other'")
        for a in articles:
            a["category"] = "other"
        return articles

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    total = len(articles)
    logger.info(f"Categorizing {total} articles in batches of {CATEGORIZATION_BATCH_SIZE}")

    for batch_start in range(0, total, CATEGORIZATION_BATCH_SIZE):
        batch = articles[batch_start: batch_start + CATEGORIZATION_BATCH_SIZE]
        user_msg = _build_user_message(batch, batch_start)

        try:
            results = _call_claude(client, user_msg)
            for result in results:
                idx = result.get("index")
                cat = result.get("category")
                if cat in CATEGORIES and isinstance(idx, int) and 0 <= idx < total:
                    articles[idx]["category"] = cat
        except Exception as exc:
            logger.error(f"Categorization batch starting at {batch_start} failed: {exc}")
            for article in batch:
                if article["category"] is None:
                    article["category"] = "other"

    for article in articles:
        if article["category"] is None:
            article["category"] = "other"

    return articles
