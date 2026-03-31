"""
config.py — Global Configuration & Constants

All system parameters, thresholds, and configuration in one place.
Load from environment variables where necessary.
"""

import os
from datetime import timedelta

# ============================================================================
# API & CREDENTIALS
# ============================================================================

X_API_KEY = os.getenv("X_API_KEY")
X_API_SECRET = os.getenv("X_API_SECRET")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
X_ACCESS_TOKEN_SECRET = os.getenv("X_ACCESS_TOKEN_SECRET")
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = "claude-sonnet-4-20250514"

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NVIDIA_ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"

# ============================================================================
# POSTING
# ============================================================================

DAILY_POST_TIME = os.getenv("POST_TIME_UTC", "09:00")  # HH:MM in UTC
MAX_POSTS_PER_DAY = int(os.getenv("MAX_POSTS_PER_DAY", "1"))
MAX_TWEET_LENGTH = 280
OPTIMAL_TWEET_LENGTH = 220  # Leave buffer

# ============================================================================
# LEARNING & STRATEGY
# ============================================================================

MIN_MATURE_TWEETS_TO_LEARN = 10
MIN_TWEETS_PER_COMBINATION = 3
STRATEGY_WINDOW_DAYS = 30
PATTERN_DECAY_DAYS = 30

# Confidence levels gate how aggressively the system optimizes
CONFIDENCE_THRESHOLDS = {
    "low": (0, 20),        # < 20 mature tweets  → conservative
    "medium": (20, 60),    # 20–60 mature tweets → moderate
    "high": (60, None)     # 60+ mature tweets   → full optimization
}

# ============================================================================
# EXPLORATION & DIVERSITY
# ============================================================================

EXPLORATION_FRACTION = 0.30  # 30% of posts are always exploratory
EXPLOITATION_FRACTION = 0.70  # 70% use best-known strategy

FORMAT_COOLDOWN_DAYS = 3       # Format can't repeat for N days
FORMAT_RETIREMENT_DAYS = 14    # Retired format eligible for re-experimentation
DIVERSITY_SCORE_THRESHOLD = 0.5  # If < this, force exploration

EXPLORATION_TYPES = [
    "new_format",
    "new_topic",
    "new_tone",
    "structure_variant"
]

# Weekly experiment schedule
WEEKLY_EXPERIMENT_SCHEDULE = {
    0: "new_format",          # Monday
    1: "exploitation",         # Tuesday
    2: "new_topic",           # Wednesday
    3: "exploitation",         # Thursday
    4: "structure_variant",   # Friday
    5: "exploitation",         # Saturday
    6: "new_tone",            # Sunday
}

# ============================================================================
# METRIC MATURITY
# ============================================================================

# Engagement is not instant. Tiers:
# fresh: 0–6 hours   → trust 0.2 (don't learn yet)
# settling: 6–48 hrs → trust 0.7 (partial signal)
# mature: 48h+       → trust 1.0 (full signal, use for strategy)

MATURITY_TIERS = {
    "fresh": {
        "min_hours": 0,
        "max_hours": 6,
        "trust": 0.2,
        "use_for_strategy": False
    },
    "settling": {
        "min_hours": 6,
        "max_hours": 48,
        "trust": 0.7,
        "use_for_strategy": False
    },
    "mature": {
        "min_hours": 48,
        "max_hours": None,
        "trust": 1.0,
        "use_for_strategy": True
    }
}

# Fetch schedule
FETCH_SCHEDULE = {
    "fresh_check": {"after_hours": 2, "fields": ["impressions", "likes", "retweets", "replies"]},
    "settling_check": {"after_hours": 24, "fields": ["impressions", "likes", "retweets", "replies", "quote_tweets"]},
    "mature_check": {"after_hours": 72, "fields": ["impressions", "likes", "retweets", "replies", "quote_tweets"]},
}

# ============================================================================
# SCORING & ENGAGEMENT WEIGHTS
# ============================================================================

# Weights favor replies/quotes over likes (real engagement > passive approval)
ENGAGEMENT_WEIGHTS = {
    "impression": 0.05,
    "like": 2.0,
    "retweet": 6.0,
    "reply": 7.0,
    "quote_tweet": 8.0,
}

# ============================================================================
# CONTENT FORMATS, TOPICS, TONES
# ============================================================================

VALID_FORMATS = [
    "reversal",
    "prediction",
    "observation",
    "unpopular_truth",
    "compressed_lesson",
    "list",
    "thread_opener",
]

VALID_TOPICS = [
    "ai_ml",
    "founder_reality",
    "big_tech",
    "startup_frameworks",
    "emerging_tech",
    "dev_culture",
]

VALID_TONES = [
    "contrarian",
    "analytical",
    "educational",
    "observational",
    "provocative",
]

# ============================================================================
# VALIDATION
# ============================================================================

BANNED_WORDS = [
    "game-changing",
    "disruptive",
    "synergy",
    "democratizing",
    "innovative",
    "exciting",
    "inspiring",
]

DUPLICATE_SIMILARITY_THRESHOLD = 0.75  # Cosine similarity for duplicate detection

# ============================================================================
# GENERATION
# ============================================================================

MAX_GENERATION_ATTEMPTS = 3
GENERATION_TEMPERATURE = 0.8
GENERATION_TOP_P = 0.95

# ============================================================================
# LOGGING
# ============================================================================

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR = "logs"
LOG_FORMAT = "json"  # json or text

# ============================================================================
# STORAGE
# ============================================================================

MEMORY_DIR = "memory"
MEMORY_TYPE = "json"  # json or sqlite (currently json)

TWEET_LOG_FILE = f"{MEMORY_DIR}/tweet_log.jsonl"
STRATEGY_LOG_FILE = f"{MEMORY_DIR}/strategy_log.jsonl"
PATTERN_LIBRARY_FILE = f"{MEMORY_DIR}/pattern_library.jsonl"

# ============================================================================
# NICHE CONFIG
# ============================================================================

NICHE_CONFIG_PATH = "config/niche.md"

# ============================================================================
# RATE LIMITING
# ============================================================================

X_API_RATE_LIMIT = 50  # Posts per 24 hours on Basic tier
FETCH_RATE_LIMIT = 300  # Requests per 15 mins for reads

# Backoff strategy for rate limits
BACKOFF_INITIAL = 1  # seconds
BACKOFF_MAX = 300  # seconds (5 minutes)
BACKOFF_MULTIPLIER = 2

# ============================================================================
# STARTUP CHECKS
# ============================================================================

REQUIRED_ENV_VARS = [
    "X_API_KEY",
    "X_API_SECRET",
    "X_ACCESS_TOKEN",
    "X_ACCESS_TOKEN_SECRET",
    "X_BEARER_TOKEN",
    "ANTHROPIC_API_KEY",
    "NVIDIA_API_KEY",
]

# ============================================================================
# PATHS & DIRECTORIES
# ============================================================================

MEMORY_DIR = "memory"
LOG_DIR = "logs"
DATA_DIR = "data"

# Ensure all directories exist
for dir_path in [MEMORY_DIR, LOG_DIR, DATA_DIR]:
    os.makedirs(dir_path, exist_ok=True)
