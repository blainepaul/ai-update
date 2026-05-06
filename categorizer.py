import re
import logging
from config import CATEGORIES

logger = logging.getLogger(__name__)

# Keywords per categoria — ordine = priorità (prima match vince)
RULES: list[tuple[str, list[str]]] = [
    ("policy_regulation", [
        "regulation", "regulat", "law", "legislat", "congress", "senate", "parliament",
        "european union", "eu ai act", "ai act", "ban", "policy", "government", "legal",
        "court", "lawsuit", "gdpr", "compliance", "antitrust", "ftc", "fcc", "fda",
        "ministry", "minister", "governo", "legge", "regolamento", "parlamento",
    ]),
    ("ethics_safety", [
        "safety", "alignment", "bias", "harm", "deepfake", "misuse", "ethics",
        "responsible ai", "trustworthy", "transparent", "explainab", "fairness",
        "risk", "danger", "threat", "concern", "controversial", "censur",
        "disinformation", "misinformation", "fake", "sicurezza", "etica",
    ]),
    ("healthcare", [
        "health", "medical", "doctor", "diagnosis", "drug", "clinical", "hospital",
        "patient", "cancer", "disease", "pharma", "therapeut", "radiology",
        "genomic", "biotech", "mental health", "psychiatr", "salute", "medicina",
    ]),
    ("creativity", [
        "image generat", "video generat", "text-to-image", "text-to-video",
        "music generat", "art", "creative", "design", "sora", "dall-e", "midjourney",
        "stable diffusion", "flux", "runway", "pika", "animation", "film", "creative ai",
        "generative art", "arte", "creatività",
    ]),
    ("business_investment", [
        "funding", "raised", "million", "billion", "valuation", "acquisition",
        "acqui", "merger", "ipo", "startup", "venture", "invest", "partnership",
        "deal", "revenue", "profit", "loss", "layoff", "hiring", "employee",
        "finanziamento", "miliardo", "milione", "acquisizione",
    ]),
    ("models_research", [
        "model", "llm", "large language", "foundation model", "benchmark",
        "research paper", "arxiv", "training", "fine-tun", "weights", "parameter",
        "gpt", "gemini", "claude", "llama", "mistral", "phi", "qwen", "grok",
        "o1", "o3", "o4", "r1", "deepseek", "diffusion", "multimodal",
        "transformer", "attention", "neural network", "algorithm",
    ]),
    ("tools_products", [
        "launch", "release", "new feature", "plugin", "extension", "app",
        "api", "platform", "product", "assistant", "chatbot", "copilot",
        "agent", "workflow", "automat", "integrat", "update", "version",
        "tool", "software", "service", "subscription", "open source",
    ]),
]

_COMPILED: list[tuple[str, re.Pattern]] = [
    (cat, re.compile("|".join(re.escape(kw) for kw in kws), re.IGNORECASE))
    for cat, kws in RULES
]


def _classify(title: str, summary: str) -> str:
    text = f"{title} {summary}"
    for cat, pattern in _COMPILED:
        if pattern.search(text):
            return cat
    return "other"


def categorize_articles(articles: list[dict]) -> list[dict]:
    counts: dict[str, int] = {cat: 0 for cat in CATEGORIES}
    for article in articles:
        cat = _classify(article["title"], article.get("summary", ""))
        article["category"] = cat
        counts[cat] = counts.get(cat, 0) + 1
    logger.info(f"Categorized {len(articles)} articles: " +
                ", ".join(f"{c}={n}" for c, n in counts.items() if n))
    return articles
