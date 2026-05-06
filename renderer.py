import os
import re
import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from jinja2 import Environment, FileSystemLoader
from config import CATEGORIES, CATEGORY_LABELS, CATEGORY_ICONS

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


def _score(article: dict, now: datetime) -> float:
    score = 0.0
    age = now - article["date"]
    if age < timedelta(hours=24):
        score += 3
    elif age < timedelta(hours=48):
        score += 1
    if article["source"] in HIGH_IMPACT_SOURCES:
        score += 2
    text = f"{article['title']} {article.get('summary', '')}"
    score += len(HIGH_IMPACT_KEYWORDS.findall(text)) * 1.5
    return score


def pick_highlights(articles: list[dict], n: int = 5) -> list[dict]:
    now = datetime.now(timezone.utc)
    scored = sorted(articles, key=lambda a: _score(a, now), reverse=True)
    return scored[:n]


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


def render_html(articles: list[dict]) -> str:
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

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    active_sources = len(set(a["source"] for a in articles))

    highlights = pick_highlights(articles)

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
