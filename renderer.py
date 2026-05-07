import os
import re
import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from jinja2 import Environment, FileSystemLoader
from config import CATEGORIES, CATEGORY_LABELS, CATEGORY_ICONS
from traction import get_article_history

logger = logging.getLogger(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

HIGH_IMPACT_SOURCES = {
    "OpenAI Blog", "Anthropic Blog", "Google AI Blog", "DeepMind Blog", "HuggingFace Blog"
}
HIGH_IMPACT_KEYWORDS = re.compile(
    r"launch|release|announc|breakthrough|new model|raises|funding|billion|"
    r"regulation|ban|acqui|open.sourc|gpt|gemini|claude|llama|mistral|"
    r"lancia|annuncia|miliard|regolament",
    re.IGNORECASE
)

# Major AI players and their top executives — any headline featuring these is relevant
_MAJOR_COMPANIES = re.compile(
    r"\b(anthropic|openai|open\s+ai|deepmind|google\s+deepmind|google\s+ai|"
    r"meta\s+ai|xai|x\.ai|grok|mistral|cohere|nvidia|"
    r"microsoft\s+ai|copilot|chatgpt|gemini|claude|perplexity|"
    r"hugging\s+face|stability\s+ai|inflection|"
    # CEOs / key figures — their statements move the industry
    r"sam\s+altman|dario\s+amodei|sundar\s+pichai|demis\s+hassabis|"
    r"jensen\s+huang|satya\s+nadella|yann\s+lecun|geoffrey\s+hinton|"
    r"ilya\s+sutskever|elon\s+musk|mark\s+zuckerberg|greg\s+brockman)\b",
    re.IGNORECASE,
)

# Market-moving events — when paired with a major company, big boost
_MARKET_EVENTS = re.compile(
    r"\b(deal|partnership|acqui|invest|fund|raises|raised|billion|million|"
    r"launches|launch|announces|unveiled|integrat|agreement|contract|"
    r"doubles|expand|collaborat|hired|hires|joins|inks|signs|wins)\b",
    re.IGNORECASE,
)


def _score(article: dict, now: datetime, traction_map: dict) -> float:
    score = 0.0
    age = now - article["date"]
    if age < timedelta(hours=24):
        score += 3
    elif age < timedelta(hours=48):
        score += 1
    if article["source"] in HIGH_IMPACT_SOURCES:
        score += 2

    title = article["title"]
    text = f"{title} {article.get('summary', '')}"
    score += len(HIGH_IMPACT_KEYWORDS.findall(text)) * 1.5

    # Major company mention in the title → relevant by definition
    if _MAJOR_COMPANIES.search(title):
        score += 2
        # Company + market event in the same headline → extra boost
        if _MARKET_EVENTS.search(title):
            score += 2

    # Real traction from HN + Reddit (0-10, normalized)
    if traction_map:
        from traction import get_article_traction
        score += get_article_traction(article, traction_map) * 3
    return score


def pick_highlights(articles: list[dict], traction_map: dict | None = None, n: int = 5) -> list[dict]:
    now = datetime.now(timezone.utc)
    tm = traction_map or {}
    scored = sorted(articles, key=lambda a: _score(a, now, tm), reverse=True)
    return scored[:n]


def _sparkline_svg(scores: list[float]) -> str:
    """Inline SVG bar chart from a list of 0-10 traction scores."""
    if len(scores) < 2:
        return ""
    n = min(len(scores), 8)
    data = scores[-n:]
    w, h = 56, 18
    bar_w = w / n
    max_val = max(data) if max(data) > 0 else 1
    bars = []
    for i, val in enumerate(data):
        bh = max(2.0, (val / max_val) * h)
        x = i * bar_w + 1
        y = h - bh
        if i < n - 1:
            color = "#3d2d6e"
        elif val > data[-2] * 1.05:
            color = "#22c55e"
        elif val < data[-2] * 0.95:
            color = "#ef4444"
        else:
            color = "#7c3aed"
        bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w - 2:.1f}" height="{bh:.1f}" fill="{color}" rx="1"/>')
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'style="vertical-align:middle;flex-shrink:0">{"".join(bars)}</svg>')


def _trend_arrow(scores: list[float]) -> tuple[str, str]:
    """Returns (arrow_char, css_class) based on last vs previous score."""
    if len(scores) < 2:
        return "", ""
    delta = scores[-1] - scores[-2]
    if delta > 0.3:
        return "↑", "trend-up"
    if delta < -0.3:
        return "↓", "trend-down"
    return "→", "trend-flat"


DAYS_IT   = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
MONTHS_IT = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
             "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]


def _day_label(day_key: str) -> str:
    dt = datetime.strptime(day_key, "%Y-%m-%d")
    today = datetime.now(timezone.utc).date()
    delta = (today - dt.date()).days
    prefix = {0: "Oggi", 1: "Ieri"}.get(delta, "")
    full = f"{DAYS_IT[dt.weekday()]} {dt.day} {MONTHS_IT[dt.month]} {dt.year}"
    return f"{prefix} — {full}" if prefix else full


def render_html(articles: list[dict], highlights: list[dict], traction_history: dict | None = None) -> str:
    # Group by day (UTC date key)
    by_day: dict[str, list[dict]] = defaultdict(list)
    for article in articles:
        day_key = article["date"].strftime("%Y-%m-%d")
        by_day[day_key].append(article)

    sorted_days = sorted(by_day.keys(), reverse=True)

    days_data = []
    for day_key in sorted_days:
        day_articles = by_day[day_key]
        by_cat = {cat: [] for cat in CATEGORIES}
        for article in day_articles:
            cat = article.get("category", "other")
            if cat not in by_cat:
                cat = "other"
            by_cat[cat].append(article)

        days_data.append({
            "key":        day_key,
            "label":      _day_label(day_key),
            "categories": by_cat,
            "total":      len(day_articles),
        })

    # Enrich highlights with sparkline SVG + trend arrow
    hist = traction_history or {}
    for article in highlights:
        scores = [p["score"] for p in get_article_history(article, hist)]
        article["_sparkline"] = _sparkline_svg(scores)
        arrow, css = _trend_arrow(scores)
        article["_trend_arrow"] = arrow
        article["_trend_class"] = css

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    active_sources = len(set(a["source"] for a in articles))

    env = Environment(loader=FileSystemLoader(os.path.join(BASE_DIR, "templates")))
    template = env.get_template("dashboard.html")

    return template.render(
        highlights=highlights,
        days=days_data,
        category_order=CATEGORIES,
        labels=CATEGORY_LABELS,
        icons=CATEGORY_ICONS,
        total_articles=len(articles),
        total_sources=active_sources,
        total_days=len(sorted_days),
        generated_at=now_str,
    )


def write_output(html: str) -> str:
    # docs/ is served by GitHub Pages; same file used locally
    output_dir = os.path.join(BASE_DIR, "docs")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "index.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info(f"Output written: {output_path}")
    return output_path
