import json
import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_RUN_FLAG = os.path.join(BASE_DIR, "cache", "last_run.txt")


def _current_slot() -> str:
    """morning = UTC 0-11, afternoon = UTC 12-23."""
    return "morning" if datetime.now(timezone.utc).hour < 12 else "afternoon"


def _already_ran_today() -> bool:
    try:
        with open(_RUN_FLAG) as f:
            flags = json.load(f)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return flags.get(_current_slot()) == today
    except (FileNotFoundError, ValueError):
        return False


def _mark_ran_today():
    os.makedirs(os.path.dirname(_RUN_FLAG), exist_ok=True)
    try:
        with open(_RUN_FLAG) as f:
            flags = json.load(f)
    except (FileNotFoundError, ValueError):
        flags = {}
    flags[_current_slot()] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with open(_RUN_FLAG, "w") as f:
        json.dump(flags, f)


def setup_logging():
    log_dir = os.path.join(BASE_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "aggregator.log")
    handler = RotatingFileHandler(log_path, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[handler, logging.StreamHandler(sys.stdout)],
    )


def open_in_browser(path: str):
    import sys as _sys
    if _sys.platform != "win32":
        return
    try:
        os.startfile(path)
    except Exception as exc:
        logging.getLogger("main").warning(f"Could not open browser: {exc}")


def main():
    setup_logging()
    logger = logging.getLogger("main")

    if _already_ran_today():
        logger.info("Already ran successfully today — skipping duplicate run")
        sys.exit(0)

    logger.info("=== AI News Aggregator starting ===")

    # Load existing store
    import store
    existing = store.load()
    existing_urls = {a["url"] for a in existing}

    # Fetch new articles (RSS + Reddit)
    from fetcher import fetch_all_articles
    fetched = fetch_all_articles()

    new_articles = [a for a in fetched if a["url"] not in existing_urls]
    new_urls = {a["url"] for a in new_articles}
    logger.info(f"New articles to process: {len(new_articles)}")

    if new_articles:
        merged = store.merge(existing, new_articles)
    else:
        merged = existing

    # Always recategorize the full store so rule changes take effect immediately
    from categorizer import categorize_articles
    merged = categorize_articles(merged)

    merged = store.purge_old(merged)
    merged.sort(key=lambda a: a["date"], reverse=True)

    if not merged:
        logger.warning("Store is empty after purge — keeping previous output")
        sys.exit(0)

    store.save(merged)

    # Build traction map from HN + Reddit + Serper + Google Trends, then save history
    from traction import build_traction_map, save_traction_history
    traction_map = build_traction_map(merged)
    traction_history = save_traction_history(traction_map)

    from renderer import render_html, write_output, pick_highlights

    # Deduplicate for display using LLM (store keeps full history)
    from llm_scorer import dedup_with_llm, build_llm_score_map
    display = dedup_with_llm(merged)

    # Mark articles added in this run
    for a in display:
        a["_is_new"] = a["url"] in new_urls
    logger.info(f"Dedup: {len(merged)} → {len(display)} articles for display")

    # LLM strategic importance scoring via Gemini Flash (free tier)
    llm_map = build_llm_score_map(display)

    # Compute highlights ONCE — used both for the site and the Telegram message
    highlights = pick_highlights(display, traction_map, llm_map)

    html = render_html(display, highlights, traction_history)
    output_path = write_output(html)

    from notifier import send_highlights
    send_highlights(highlights)

    _mark_ran_today()
    open_in_browser(output_path)
    logger.info(f"=== Done — {len(merged)} articles in store ===")


if __name__ == "__main__":
    main()
