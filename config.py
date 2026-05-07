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
    # Major tech media
    {"name": "TechCrunch AI",    "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
    {"name": "The Verge AI",     "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"},
    {"name": "VentureBeat AI",   "url": "https://venturebeat.com/category/ai/feed/"},
    {"name": "MIT Tech Review",  "url": "https://www.technologyreview.com/feed/"},
    {"name": "Wired",            "url": "https://www.wired.com/feed/rss"},
    {"name": "The Register AI",  "url": "https://www.theregister.com/software/ai_ml/headlines.atom"},
    {"name": "Ars Technica",     "url": "https://feeds.arstechnica.com/arstechnica/technology-lab"},
    {"name": "AI News (AIN)",    "url": "https://www.artificialintelligence-news.com/feed/"},
    {"name": "Bloomberg Tech",   "url": "https://feeds.bloomberg.com/technology/news.rss"},
    {"name": "ANSA Tech",        "url": "https://www.ansa.it/sito/ansait_rss.xml"},
    # Official AI company blogs
    {"name": "OpenAI Blog",      "url": "https://openai.com/blog/rss.xml"},
    {"name": "Anthropic Blog",   "url": "https://www.anthropic.com/rss.xml"},
    {"name": "Google AI Blog",   "url": "https://blog.google/technology/ai/rss/"},
    {"name": "DeepMind Blog",    "url": "https://deepmind.google/blog/rss/"},
    {"name": "Meta AI Blog",     "url": "https://ai.meta.com/blog/rss/"},
    {"name": "Microsoft AI Blog","url": "https://blogs.microsoft.com/ai/feed/"},
    {"name": "NVIDIA Blog",      "url": "https://blogs.nvidia.com/feed/"},
    {"name": "Mistral AI Blog",  "url": "https://mistral.ai/news/rss/"},
    {"name": "HuggingFace Blog", "url": "https://huggingface.co/blog/feed.xml"},
    {"name": "AWS ML Blog",      "url": "https://aws.amazon.com/blogs/machine-learning/feed/"},
    # Research
    {"name": "Papers With Code", "url": "https://paperswithcode.com/latest.rss"},
    {"name": "IEEE Spectrum AI", "url": "https://spectrum.ieee.org/feeds/topic/artificial-intelligence.rss"},
    {"name": "AI Alignment Forum","url": "https://www.alignmentforum.org/feed.xml"},
    # Newsletters
    {"name": "The Batch",        "url": "https://www.deeplearning.ai/the-batch/rss/"},
    {"name": "Import AI",        "url": "https://importai.substack.com/feed"},
    {"name": "Ben's Bites",      "url": "https://bensbites.beehiiv.com/feed"},
    {"name": "Interconnects",    "url": "https://www.interconnects.ai/feed"},
    {"name": "One Useful Thing", "url": "https://www.oneusefulthing.org/feed"},
    # Business / finance
    {"name": "Fortune AI",       "url": "https://fortune.com/tag/artificial-intelligence/feed/"},
    # Italian / European
    {"name": "Wired Italia",     "url": "https://www.wired.it/rss"},
    {"name": "Agenda Digitale",  "url": "https://www.agendadigitale.eu/feed/"},
]

# Feeds that are NOT AI-specific and need keyword filtering
GENERIC_FEEDS = {
    "ANSA Tech", "Bloomberg Tech", "MIT Tech Review", "Wired", "Ars Technica",
    "IEEE Spectrum AI", "Fortune AI", "Wired Italia", "Agenda Digitale",
    "NVIDIA Blog",  # covers GPU/hardware broadly, filter to AI topics
}

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
    # Core concepts
    "artificial intelligence", "machine learning", "deep learning",
    "neural network", "large language model", "foundation model",
    "generative ai", "diffusion model", "transformer", "multimodal",
    "reasoning model", "agentic", "ai agent", "llm",
    # Specific models
    "gpt", "gemini", "claude", "chatgpt", "copilot",
    "llama", "deepseek", "grok", "mistral", "mixtral", "gemma",
    "stable diffusion", "midjourney", "sora", "dall-e",
    # Companies / platforms
    "openai", "anthropic", "deepmind", "nvidia",
    "hugging face", "huggingface", "perplexity", "cohere", "xai",
    "stability ai", "mistral ai",
    # Products & use cases
    "ai model", "ai chip", "ai hardware", "ai datacenter", "ai infrastructure",
    "ai regulation", "ai safety", "ai ethics", "ai tool", "ai assistant",
    "ai coding", "vibe coding", "computer use",
    "text-to-video", "text-to-image", "voice ai", "speech recognition",
    "retrieval augmented", "fine-tuning", "fine-tune",
    "open source ai", "model weights", "open weights",
    # Policy / milestones
    "ai act", "eu ai", "agi", "superintelligence", "ai startup",
    "ai investment", "ai compute", "ai governance",
    # Italian
    "intelligenza artificiale", "apprendimento automatico",
    "modello linguistico", "rete neurale",
]

# --- Fetcher settings ---
MAX_ARTICLES_PER_FEED = 15
FETCH_TIMEOUT_SECONDS = 10
MAX_AGE_HOURS = 26

# --- Claude settings ---
CLAUDE_MODEL = "claude-haiku-4-5-20251001"
CATEGORIZATION_BATCH_SIZE = 10
