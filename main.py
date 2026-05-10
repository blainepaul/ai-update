import json
import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_RUN_FLAG = os.path.join(BASE_DIR, "cache", "last_run.txt")
_PREV_HIGHLIGHTS_FILE = os.path.join(BASE_DIR, "cache", "last_highlights.json")
_WEEKLY_TOOLS_FILE = os.path.join(BASE_DIR, "cache", "weekly_tools.json")


def _load_prev_highlight_urls() -> set[str]:
    try:
        with open(_PREV_HIGHLIGHTS_FILE) as f:
            return set(json.load(f))
    except (FileNotFoundError, ValueError):
        return set()


def _save_highlight_urls(highlights: list[dict]):
    os.makedirs(os.path.dirname(_PREV_HIGHLIGHTS_FILE), exist_ok=True)
    with open(_PREV_HIGHLIGHTS_FILE, "w") as f:
        json.dump([a["url"] for a in highlights], f)


def _current_slot() -> str:
    """morning = UTC 0-11, afternoon = UTC 12-23."""
    return "morning" if datetime.now(timezone.utc).hour < 12 else "afternoon"


def _read_flags() -> dict:
    try:
        with open(_RUN_FLAG) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def _already_ran_today() -> bool:
    flags = _read_flags()
    ts = flags.get(_current_slot())
    if not ts:
        return False
    try:
        # Support both old format ("2025-05-07") and new ISO format
        if "T" in ts:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        else:
            dt = datetime.strptime(ts, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return dt.date() == datetime.now(timezone.utc).date()
    except ValueError:
        return False


def _mark_ran_today():
    os.makedirs(os.path.dirname(_RUN_FLAG), exist_ok=True)
    flags = _read_flags()
    flags[_current_slot()] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(_RUN_FLAG, "w") as f:
        json.dump(flags, f)


def _fetch_window_hours() -> float:
    """
    Returns how many hours back the fetcher should look.
    = elapsed time since the most recent run across all slots + 2h buffer.
    Clamped to [6, 48] hours.
    """
    flags = _read_flags()
    now = datetime.now(timezone.utc)
    latest: datetime | None = None
    for ts in flags.values():
        try:
            if "T" in ts:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            else:
                dt = datetime.strptime(ts, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if latest is None or dt > latest:
                latest = dt
        except ValueError:
            pass
    if latest is None:
        return 26.0  # first ever run: default lookback
    elapsed_hours = (now - latest).total_seconds() / 3600
    return max(6.0, min(48.0, elapsed_hours + 2.0))


def _load_weekly_tools() -> list:
    try:
        with open(_WEEKLY_TOOLS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return []


def _save_weekly_tools(tools: list):
    os.makedirs(os.path.dirname(_WEEKLY_TOOLS_FILE), exist_ok=True)
    with open(_WEEKLY_TOOLS_FILE, "w") as f:
        json.dump(tools, f, ensure_ascii=False, indent=2)


def _is_monday_morning() -> bool:
    now = datetime.now(timezone.utc)
    return now.weekday() == 0 and now.hour < 12


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

    # Fetch new articles (RSS + Reddit) — window = elapsed since last run + 2h buffer
    from fetcher import fetch_all_articles
    fetch_hours = _fetch_window_hours()
    logger.info(f"Fetch window: {fetch_hours:.1f}h")
    fetched = fetch_all_articles(max_age_hours=fetch_hours)

    new_articles = [a for a in fetched if a["url"] not in existing_urls]
    new_urls = {a["url"] for a in new_articles}
    run_slot = _current_slot()
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for a in new_articles:
        a["_slot"] = run_slot
        a["_slot_date"] = run_date
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

    # Pre-compute scores so renderer can sort by relevance
    from renderer import _score as compute_score
    _now = datetime.now(timezone.utc)

    # Pre-filter: score new articles with rule-based scorer (no LLM yet), pick top 60
    # These are the candidates for Gemini evaluation
    new_display = [a for a in display if a.get("_is_new")]
    llm_candidates = sorted(
        new_display,
        key=lambda a: compute_score(a, _now, traction_map, {}),
        reverse=True,
    )[:60]
    logger.info(f"LLM candidates (pre-filtered): {len(llm_candidates)} of {len(new_display)} new articles")

    # LLM strategic importance scoring via Gemini Flash (free tier)
    llm_map = build_llm_score_map(llm_candidates)

    for a in display:
        a["_computed_score"] = compute_score(a, _now, traction_map, llm_map)

    # Top 20 of this run (new articles only), sorted by score
    run_top20 = sorted(
        [a for a in display if a.get("_is_new")],
        key=lambda a: a["_computed_score"],
        reverse=True,
    )[:20]

    # Top 7 = best 7 of the current run's top 20
    # Fallback to full display if run brought < 7 new articles
    highlight_pool = run_top20 if len(run_top20) >= 7 else display
    highlights = pick_highlights(highlight_pool, traction_map, llm_map)

    # 140-char Italian descriptions for Top 7 (1 Gemini call)
    from llm_scorer import build_top7_descriptions, build_weekly_tools_section
    build_top7_descriptions(highlights)

    # Weekly tools section — rebuilt every Monday morning (or if cache is empty)
    cached_tools = _load_weekly_tools()
    if _is_monday_morning() or not cached_tools:
        weekly_tools = build_weekly_tools_section(display, traction_map, llm_map)
        _save_weekly_tools(weekly_tools)
        logger.info(f"Weekly tools section updated: {len(weekly_tools)} items")
    else:
        weekly_tools = cached_tools

    html = render_html(display, highlights, traction_history, weekly_tools)
    output_path = write_output(html)

    from notifier import send_highlights
    send_highlights(highlights)

    _mark_ran_today()
    open_in_browser(output_path)
    logger.info(f"=== Done — {len(merged)} articles in store ===")


if __name__ == "__main__":
    main()
