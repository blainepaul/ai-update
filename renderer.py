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

# Named executives — separate from _MAJOR_COMPANIES for targeted declaration boost
_EXEC_NAMES = re.compile(
    r"\b(sam\s+altman|dario\s+amodei|sundar\s+pichai|demis\s+hassabis|"
    r"jensen\s+huang|satya\s+nadella|yann\s+lecun|geoffrey\s+hinton|"
    r"ilya\s+sutskever|elon\s+musk|mark\s+zuckerberg|greg\s+brockman|"
    r"altman|amodei|hassabis|nadella|lecun|hinton|sutskever|brockman)\b",
    re.IGNORECASE,
)

# Statement verbs — declaration by a named executive is industry-relevant
_EXEC_STATEMENT = re.compile(
    r"\b(says|said|warns|warning|predicts|believes|claims|argues|"
    r"interview|keynote|speech|statement|declares|urges|reveals|"
    r"admits|confirms|calls\s+for|thinks|suggests|responds|fires\s+back)\b",
    re.IGNORECASE,
)


def _score(article: dict, now: datetime, traction_map: dict, llm_map: dict | None = None) -> float:
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

    # Named executive + statement verb → declaration boost (+2)
    if _EXEC_NAMES.search(title) and _EXEC_STATEMENT.search(title):
        score += 2

    # Traction from HN + Reddit + Serper + Google Trends (0-10 normalized → max +20)
    if traction_map:
        from traction import get_article_traction
        score += get_article_traction(article, traction_map) * 2

    # LLM strategic importance score (0-10 → max +15)
    if llm_map:
        from llm_scorer import get_article_llm_score
        score += get_article_llm_score(article, llm_map) * 1.5

    # Malus for articles already shown in previous highlights (-8 pts)
    if article.get("_in_prev_highlights"):
        score -= 8

    return score


def pick_highlights(articles: list[dict], traction_map: dict | None = None,
                    llm_map: dict | None = None, n: int = 7) -> list[dict]:
    now = datetime.now(timezone.utc)
    tm = traction_map or {}
    lm = llm_map or {}
    scored = sorted(articles, key=lambda a: _score(a, now, tm, lm), reverse=True)
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


_DEDUP_STOP = frozenset({
    "the","and","for","with","that","this","its","from","about",
    "are","was","were","been","has","have","had","will","can",
    "could","would","may","might","not","but","also","more",
    "than","just","all","when","into","out","over","after",
    "their","how","what","why","says","said","one","two",
})


def _title_tokens(title: str) -> frozenset:
    tokens = re.findall(r'\b[a-z0-9]{3,}\b', title.lower())
    return frozenset(t for t in tokens if t not in _DEDUP_STOP)


def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def dedup_articles(articles: list[dict], threshold: float = 0.55) -> list[dict]:
    """
    Collapse near-duplicate articles (same story, multiple sources) within each day.
    Keeps the best article per cluster: official source first, then most recent.
    Articles are never merged across different days.
    """
    by_day: dict[str, list[dict]] = defaultdict(list)
    for a in articles:
        by_day[a["date"].strftime("%Y-%m-%d")].append(a)

    kept: list[dict] = []
    for day_arts in by_day.values():
        tok_cache = {id(a): _title_tokens(a["title"]) for a in day_arts}
        clusters: list[list[dict]] = []
        for article in day_arts:
            kw = tok_cache[id(article)]
            placed = False
            for cluster in clusters:
                if any(_jaccard(kw, tok_cache[id(m)]) >= threshold for m in cluster):
                    cluster.append(article)
                    placed = True
                    break
            if not placed:
                clusters.append([article])
        for cluster in clusters:
            best = max(cluster, key=lambda a: (
                a["source"] in HIGH_IMPACT_SOURCES,
                a["date"],
            ))
            kept.append(best)
    return kept


DAYS_IT   = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
MONTHS_IT = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
             "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
_SLOT_LABELS = {"morning": "Mattina", "afternoon": "Pomeriggio"}
_SLOT_ICONS  = {"morning": "🌅", "afternoon": "🌆"}


def _slot_label(slot_date: str, slot: str) -> str:
    dt = datetime.strptime(slot_date, "%Y-%m-%d")
    today = datetime.now(timezone.utc).date()
    delta = (today - dt.date()).days
    day_prefix = {0: "Oggi", 1: "Ieri"}.get(delta, "")
    date_str = f"{DAYS_IT[dt.weekday()]} {dt.day} {MONTHS_IT[dt.month]}"
    slot_str = _SLOT_LABELS.get(slot, "")
    if day_prefix:
        return f"{day_prefix} — {slot_str}" if slot_str else day_prefix
    return f"{slot_str} — {date_str}" if slot_str else date_str


def render_html(articles: list[dict], highlights: list[dict], traction_history: dict | None = None) -> str:
    now = datetime.now(timezone.utc)

    # Group by run slot (date + morning/afternoon).
    # Old articles without _slot default to "morning" of their date.
    by_slot: dict[str, list[dict]] = defaultdict(list)
    for article in articles:
        slot = article.get("_slot") or "morning"
        slot_date = article.get("_slot_date") or article["date"].strftime("%Y-%m-%d")
        by_slot[f"{slot_date}__{slot}"].append(article)

    sorted_slots = sorted(by_slot.keys(), reverse=True)

    slots_data = []
    for slot_key in sorted_slots:
        slot_date, slot = slot_key.split("__", 1)
        slot_articles = by_slot[slot_key]

        # Sort by relevance score (pre-computed in main.py), keep top 20
        slot_articles.sort(key=lambda a: a.get("_computed_score", 0), reverse=True)
        slot_articles = slot_articles[:20]

        by_cat = {cat: [] for cat in CATEGORIES}
        for article in slot_articles:
            cat = article.get("category", "other")
            if cat not in by_cat:
                cat = "other"
            by_cat[cat].append(article)

        new_count = sum(1 for a in slot_articles if a.get("_is_new"))
        is_today = slot_date == now.strftime("%Y-%m-%d")

        slots_data.append({
            "key":       slot_key,
            "slot_date": slot_date,
            "slot":      slot,
            "icon":      _SLOT_ICONS.get(slot, "📅"),
            "label":     _slot_label(slot_date, slot),
            "categories": by_cat,
            "total":     len(slot_articles),
            "new_count": new_count,
            "is_today":  is_today,
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
        slots=slots_data,
        category_order=CATEGORIES,
        labels=CATEGORY_LABELS,
        icons=CATEGORY_ICONS,
        total_articles=len(articles),
        total_sources=active_sources,
        total_slots=len(slots_data),
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
