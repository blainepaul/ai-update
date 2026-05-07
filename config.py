import os

# --- Telegram ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
SITE_URL           = os.environ.get("SITE_URL", "https://blainepaul.github.io/ai-update/")

# --- Categories ---
CATEGORIES = [
    "models_research",
    "tools_products",
    "policy_regulation",
    "business_investment",
    "ethics_safety",
    "healthcare",
    "creativity",
    "other",
]

CATEGORY_LABELS = {
    "models_research":     "Modelli & Ricerca",
    "tools_products":      "Strumenti & Prodotti",
    "policy_regulation":   "Policy & Regolamentazione",
    "business_investment": "Business & Investimenti",
    "ethics_safety":       "Etica & Sicurezza",
    "healthcare":          "Healthcare & Medicina",
    "creativity":          "Creatività & Arte",
    "other":               "Altro",
}

CATEGORY_ICONS = {
    "models_research":     "🧠",
    "tools_products":      "🛠️",
    "policy_regulation":   "⚖️",
    "business_investment": "💼",
    "ethics_safety":       "🛡️",
    "healthcare":          "🏥",
    "creativity":          "🎨",
    "other":               "📌",
}

# --- RSS Feeds ---
FEEDS = [
    {"name": "TechCrunch AI",    "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
    {"name": "The Verge AI",     "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"},
    {"name": "VentureBeat AI",   "url": "https://venturebeat.com/category/ai/feed/"},
    {"name": "MIT Tech Review",  "url": "https://www.technologyreview.com/feed/"},
    {"name": "Wired",            "url": "https://www.wired.com/feed/rss"},
    {"name": "OpenAI Blog",      "url": "https://openai.com/blog/rss.xml"},
    {"name": "Google AI Blog",   "url": "https://blog.google/technology/ai/rss/"},
    {"name": "HuggingFace Blog", "url": "https://huggingface.co/blog/feed.xml"},
    {"name": "The Register AI",  "url": "https://www.theregister.com/software/ai_ml/headlines.atom"},
    {"name": "AI News",          "url": "https://www.artificialintelligence-news.com/feed/"},
    {"name": "ANSA Tech",        "url": "https://www.ansa.it/sito/ansait_rss.xml"},
    {"name": "Bloomberg Tech",   "url": "https://feeds.bloomberg.com/technology/news.rss"},
    {"name": "Ars Technica",     "url": "https://feeds.arstechnica.com/arstechnica/technology-lab"},
]

# Feeds that are NOT AI-specific and need keyword filtering
GENERIC_FEEDS = {"ANSA Tech", "Bloomberg Tech", "MIT Tech Review", "Wired", "Ars Technica"}

# --- Reddit sources (curated, moderated AI subreddits) ---
# Only link posts with score >= min_score are included
REDDIT_SOURCES = [
    {"sub": "MachineLearning", "min_score": 50},   # very strict — academic/pro
    {"sub": "artificial",      "min_score": 30},
    {"sub": "AINews",          "min_score": 20},
    {"sub": "singularity",     "min_score": 30},
    {"sub": "LocalLLaMA",      "min_score": 40},
]

AI_KEYWORDS = [
    "artificial intelligence", "machine learning", "deep learning",
    "neural network", "large language model", "llm", "gpt", "gemini",
    "claude", "chatgpt", "openai", "anthropic", "deepmind", "mistral",
    "generative ai", "diffusion model", "transformer", "ai model", "ai chip",
    "nvidia", "ai regulation", "ai safety", "ai ethics", "ai tool",
    "intelligenza artificiale", "apprendimento automatico",
]

# --- Fetcher settings ---
MAX_ARTICLES_PER_FEED = 15
FETCH_TIMEOUT_SECONDS = 10
MAX_AGE_HOURS = 26

# --- Claude settings ---
CLAUDE_MODEL = "claude-haiku-4-5-20251001"
CATEGORIZATION_BATCH_SIZE = 10
