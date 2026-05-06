import os
import sys
import logging
from logging.handlers import RotatingFileHandler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


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
        return  # no browser on GitHub Actions / Linux
    try:
        os.startfile(path)
    except Exception as exc:
        logging.getLogger("main").warning(f"Could not open browser: {exc}")


def main():
    setup_logging()
    logger = logging.getLogger("main")
    logger.info("=== AI News Aggregator starting ===")

    from config import ANTHROPIC_API_KEY
    if not ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY is not set — articles will all be assigned to 'other'")

    # Load existing store (articles from past 7 days)
    import store
    existing = store.load()
    existing_urls = {a["url"] for a in existing}

    # Fetch fresh articles from RSS feeds
    from fetcher import fetch_all_articles
    fetched = fetch_all_articles()

    # Only process articles we haven't seen before
    new_articles = [a for a in fetched if a["url"] not in existing_urls]
    logger.info(f"New articles to process: {len(new_articles)}")

    if new_articles:
        from categorizer import categorize_articles
        new_articles = categorize_articles(new_articles)
        merged = store.merge(existing, new_articles)
    else:
        logger.info("No new articles — store unchanged")
        merged = existing

    # Remove articles older than 7 days
    merged = store.purge_old(merged)

    # Sort newest first before saving and rendering
    merged.sort(key=lambda a: a["date"], reverse=True)

    if not merged:
        logger.warning("Store is empty after purge — keeping previous output")
        sys.exit(0)

    store.save(merged)

    from renderer import render_html, write_output
    html = render_html(merged)
    output_path = write_output(html)

    open_in_browser(output_path)
    logger.info(f"=== Done — {len(merged)} articles in store ===")


if __name__ == "__main__":
    main()
