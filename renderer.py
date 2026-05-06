import os
import logging
from collections import defaultdict
from datetime import datetime, timezone
from jinja2 import Environment, FileSystemLoader
from config import CATEGORIES, CATEGORY_LABELS, CATEGORY_ICONS

logger = logging.getLogger(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

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

    env = Environment(loader=FileSystemLoader(os.path.join(BASE_DIR, "templates")))
    template = env.get_template("dashboard.html")

    return template.render(
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
