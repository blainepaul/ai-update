import re
import logging
from config import CATEGORIES

logger = logging.getLogger(__name__)

# --- Rules: order = priority (first match wins) ---
# Single-word keywords get \b word boundaries automatically.
# Multi-word phrases match as substrings (e.g. "image generat" catches "image generation").

RULES: list[tuple[str, list[str]]] = [
    ("policy_regulation", [
        "regulation", "regulat", "legislation", "congress", "senate", "parliament",
        "eu ai act", "ai act", "policy", "government", "legal", "court", "lawsuit",
        "gdpr", "compliance", "antitrust", "ftc", "fcc", "fda", "ban on ai",
        "ministry", "minister", "governo", "legge", "regolamento", "parlamento",
        "executive order", "white house", "european commission",
    ]),
    ("ethics_safety", [
        "ai safety", "alignment", "deepfake", "responsible ai", "trustworthy ai",
        "ai ethics", "ai bias", "ai risk", "ai harm", "disinformation", "misinformation",
        "ai regulation", "existential risk", "superintelligence", "agi risk",
        "warning about", "warns about", "raises concern", "concerned about ai",
        "ai danger", "ai threat", "ai fear", "criticizes ai", "critiques ai",
        "amodei", "altman warns", "hinton", "bengio",
        "sicurezza ai", "etica ai",
    ]),
    ("healthcare", [
        "medical ai", "ai health", "ai diagnosis", "ai drug", "clinical trial",
        "ai in medicine", "ai doctor", "ai radiology", "ai genomic",
        "ai therapy", "mental health ai", "ai pathology", "drug discovery ai",
        "salute", "medicina ai", "ai chirurgi",
    ]),
    ("business_investment", [
        "raises", "raised", "funding round", "series a", "series b", "series c",
        "seed round", "valuation", "acquisition", "acquires", "acquired", "merger",
        "ipo", "venture capital", "invested", "investment round",
        "$\\d", "billion deal", "million deal",
        "partnership deal", "revenue", "layoff", "hired", "ceo",
        "neocloud", "data center", "hyperscaler", "cloud provider",
        "market share", "profit", "earnings", "quarterly", "startup",
        "finanziamento", "miliard", "milion", "acquisizion",
    ]),
    ("models_research", [
        "new model", "model release", "language model", "foundation model",
        "benchmark", "research paper", "arxiv", "fine-tuning", "fine-tune",
        "training run", "model weights", "open-weight", "open weight",
        "gpt-", "gemini ", "claude ", "llama", "mistral", "phi-", "qwen",
        "grok", "deepseek", "o1 model", "o3 model", "reasoning model",
        "multimodal model", "diffusion model", "transformer model",
        "neural network", "pretraining", "rlhf", "reinforcement learning",
        "context window", "token", "inference", "vllm", "ollama",
        "frontier model", "intelligence density", "model architecture",
        "parameter", "embedding", "vector", "attention mechanism",
        "lab release", "ai lab", "weights released",
    ]),
    ("tools_products", [
        "product launch", "now available", "new feature", "plugin", "extension",
        "api launch", "sdk", "open source tool", "app launch", "platform launch",
        "ai assistant", "ai chatbot", "ai agent", "ai copilot", "ai workflow",
        "integrates with", "update version", "v2.0", "v3.0",
        "chrome extension", "vs code", "microsoft 365", "google workspace",
        "ai search", "ai browser", "chatgpt ", "gemini app", "claude app",
        "shuts down", "discontinu", "deprecated", "sunsets", "killed",
        "project mariner", "launches", "releases tool", "rolls out",
        "announces", "unveils", "introduces",
    ]),
    ("creativity", [
        "image generat", "video generat", "text-to-image", "text-to-video",
        "text to image", "text to video", "ai art", "generative art",
        "music generat", "ai music", "ai film", "ai animation",
        "sora", "dall-e", "midjourney", "stable diffusion", "flux model",
        "runway ml", "pika labs", "kling ai", "ai creative",
        "arte ai", "creatività",
    ]),
]


def _make_pattern(kw: str) -> str:
    """Add word boundaries for single words, plain match for phrases."""
    escaped = re.escape(kw)
    if " " in kw or "-" in kw:
        return escaped
    return r"\b" + escaped + r"\b"


_COMPILED: list[tuple[str, re.Pattern]] = [
    (cat, re.compile("|".join(_make_pattern(kw) for kw in kws), re.IGNORECASE))
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
    logger.info("Categorized %d articles: %s", len(articles),
                ", ".join(f"{c}={n}" for c, n in counts.items() if n))
    return articles
