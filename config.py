"""
config.py — Global Configuration & Constants

All system parameters, thresholds, and configuration in one place.
Load from environment variables where necessary.
"""

import os
from datetime import timedelta

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ============================================================================
# API & CREDENTIALS
# ============================================================================

GETXAPI_API_KEY = os.getenv("GETXAPI_API_KEY")
GETXAPI_AUTH_TOKEN = os.getenv("GETXAPI_AUTH_TOKEN")
GETXAPI_USERNAME = os.getenv("GETXAPI_USERNAME")
GETXAPI_PASSWORD = os.getenv("GETXAPI_PASSWORD")
GETXAPI_EMAIL = os.getenv("GETXAPI_EMAIL")
GETXAPI_TOTP_SECRET = os.getenv("GETXAPI_TOTP_SECRET")
GETXAPI_PROXY = os.getenv("GETXAPI_PROXY")
GETXAPI_BASE_URL = os.getenv("GETXAPI_BASE_URL", "https://api.getxapi.com")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = "claude-sonnet-4-20250514"

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NVIDIA_ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "qwen/qwen3.5-122b-a10b")

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
MAX_GEN_ATTEMPTS = MAX_GENERATION_ATTEMPTS  # Backward compatibility alias
GENERATION_TEMPERATURE = 0.8
GENERATION_TOP_P = 0.95
GENERATION_MAX_TOKENS_SINGLE = int(os.getenv("GENERATION_MAX_TOKENS_SINGLE", "320"))
GENERATION_MAX_TOKENS_THREAD = int(os.getenv("GENERATION_MAX_TOKENS_THREAD", "640"))

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

# ============================================================================
# PRIORITY 1: ERROR RECOVERY & ROBUSTNESS
# ============================================================================

LLM_TIMEOUT_SECS = 30  # Timeout for Mistral/Anthropic API calls
GENERATION_PHASE_TIMEOUT_SECS = int(
    os.getenv(
        "GENERATION_PHASE_TIMEOUT_SECS",
        str((LLM_TIMEOUT_SECS * MAX_GENERATION_ATTEMPTS) + 10),
    )
)
POSTER_TIMEOUT_SECS = 15  # Timeout for posting calls
CIRCUIT_BREAKER_THRESHOLD = 3  # Pause if N consecutive posts fail
JSON_BACKUP_DIR = "memory/_backups"  # Backup directory for JSON rollback

# ============================================================================
# PRIORITY 2: CONTENT QUALITY GATES
# ============================================================================

TOXICITY_THRESHOLD = 0.6  # 0-1 scale, reject if > threshold
SEMANTIC_SIMILARITY_THRESHOLD = 0.75  # Same as duplicate check
MIN_HOOK_LENGTH = 10  # Reject hooks shorter than this
MAX_HOOK_LENGTH = 100  # Reject hooks longer than this
DIVERSITY_PENALTY = 0.5  # Reduce score if format used 2+ times in 7 days

# ============================================================================
# PRIORITY 3: METRIC COLLECTION OPTIMIZATION
# ============================================================================

BATCH_FETCH_SIZE = 100  # Fetch metrics 100 tweet IDs at a time
METRIC_ARCHIVE_DAYS = 365  # Archive tweets older than 1 year
INCREMENTAL_STRATEGY_UPDATE = True  # Only update strategy on new mature tweets

# ============================================================================
# PRIORITY 4: PLATFORM COMPLIANCE
# ============================================================================

USER_AGENT = "XBot/1.0 (Autonomous AI Twitter agent; +https://github.com/adityaaa2306/xbot)"
RATE_LIMIT_BUFFER = 0.8  # Stay at 80% of platform limits
HUMAN_REVIEW_MODE = False  # If True, show 5 best tweets weekly for human approval

# ============================================================================
# PRIORITY 5: ADVANCED EXPERIMENTS & TRACKING
# ============================================================================

TRACK_URL_CLICKS = True  # Log URL click tracking data
TRACK_FOLLOWER_GROWTH = True  # Log daily follower count changes
ANALYZE_REPLY_SENTIMENT = True  # Classify replies as positive/negative/neutral
GENERATE_WEEKLY_DASHBOARD = True  # Generate text-based weekly report

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
    "GETXAPI_API_KEY",
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
