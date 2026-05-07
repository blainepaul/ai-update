"""
Reddit OAuth2 client-credentials helper.
Returns authenticated headers for oauth.reddit.com, or None if credentials are missing.
"""
import os
import logging
import requests

logger = logging.getLogger(__name__)

_UA = "script:ai-update:v1.0 (personal aggregator)"
_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"


def get_reddit_headers() -> dict | None:
    """
    Exchange client credentials for a bearer token and return ready-to-use headers.
    Returns None if REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET are not set.
    """
    client_id = os.environ.get("REDDIT_CLIENT_ID", "").strip()
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        logger.info("Reddit OAuth: credentials not configured — skipping")
        return None
    try:
        resp = requests.post(
            _TOKEN_URL,
            auth=(client_id, client_secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": _UA},
            timeout=10,
        )
        resp.raise_for_status()
        token = resp.json().get("access_token")
        if not token:
            logger.warning("Reddit OAuth: empty token in response")
            return None
        logger.info("Reddit OAuth: token acquired")
        return {"Authorization": f"Bearer {token}", "User-Agent": _UA}
    except Exception as exc:
        logger.warning(f"Reddit OAuth failed: {exc}")
        return None
