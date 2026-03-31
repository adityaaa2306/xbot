# XBOT Module API Reference

Complete function signatures and usage for all 11 production modules.

---

## 1. config.py

**Purpose:** Centralized configuration constants

### Key Constants

```python
# Learning config
MIN_MATURE_TWEETS_TO_LEARN = 10
MATURE_AGE_HOURS = 48
CONFIDENCE_THRESHOLDS = {"low": 20, "medium": 60, "high": 999}

# Generation config
MAX_GEN_ATTEMPTS = 3

# Scoring config
MATURITY_LEVELS = {"fresh": 6, "settling": 48, "mature": 72}
WEIGHTS = {
    "impression": 0.05,
    "like": 2.0,
    "retweet": 6.0,
    "reply": 7.0,
    "quote_tweet": 8.0
}
WINDOW_MONTHS = 2
MAX_AGE_DAYS = 60

# Anti-convergence
EXPLORATION_FRACTION = 0.30
MAX_PER_FORMAT_PER_WEEK = 2
NOVELTY_BONUS_MIN = 1.15
NOVELTY_BONUS_MAX = 1.50
```

---

## 2. logger.py

**Purpose:** Structured JSON logging to stdout + JSONL files

### Functions

```python
def info(message: str, event: str, data: Dict = None) -> None
def warn(message: str, event: str, data: Dict = None, error: str = None) -> None
def error(message: str, event: str, data: Dict = None, error: str = None) -> None
```

### Usage

```python
from logger import logger

logger.info("Tweet generated", event="GENERATE_SUCCESS", 
           data={"archetype": "Tactical", "score": 387})

logger.error("API failed", event="MISTRAL_ERROR", 
            error="Connection timeout")
```

### Output

```json
{"timestamp": "2026-03-31T09:15:23Z", "level": "INFO", "event": "GENERATE_SUCCESS", "message": "Tweet generated", "data": {"archetype": "Tactical", "score": 387}}
```

---

## 3. memory.py

**Purpose:** Typed persistent state via JSONL files

### Data Classes

```python
@dataclass
class TweetLog:
    tweet_id: str
    content: str
    archetype: str
    topic: str
    thread_length: int
    posted_at: str
    engagement_score: float
    score_history: list  # [{"timestamp": "2h", "score": 45, "maturity": "fresh"}, ...]

@dataclass
class StrategyLog:
    date: str
    confidence_level: str
    top_formats: list
    recommendations: str

@dataclass
class PatternLibrary:
    pattern_id: str
    archetype: str
    topic: str
    avg_engagement_score: float
    status: str  # "active", "decaying", "retired"
```

### Functions

```python
def add_tweet_to_log(tweet_obj: Dict, result: Dict, plan: Dict) -> None
def get_recent_tweets(days: int = 7, limit: int = 50) -> List[Dict]
def get_mature_tweets() -> List[Dict]
def get_strategy_logs(days: int = 1) -> List[Dict]
def update_score(tweet_id: str, score: float) -> None
def schedule_metric_fetch(tweet_id: str, delay_hours: int) -> None
def get_pattern_library() -> List[Dict]
```

### Usage

```python
from memory import memory

tweets = memory.get_recent_tweets(days=7, limit=100)
mature = memory.get_mature_tweets()
memory.add_tweet_to_log(tweet_obj, result, plan)
```

---

## 4. fetcher.py

**Purpose:** Async metric collection with exponential backoff

### Functions (Async)

```python
async def fetch_all_pending(tweets: List[Dict], batch_size: int = 10) -> int
async def fetch_tweet_metrics(tweet_id: str, window_hours: int) -> Dict
async def batch_fetch_with_backoff(tweet_ids: List[str]) -> List[Dict]
```

### Usage

```python
from fetcher import fetcher

pending = memory.get_recent_tweets(days=3)
updated = await fetcher.fetch_all_pending(pending)
print(f"Updated {updated} tweets")
```

---

## 5. scorer.py

**Purpose:** Maturity-gated engagement scoring with time decay

### Functions

```python
def score_tweet(tweet: Dict) -> float
def compute_score(metrics: Dict, weights: Dict) -> float
def percentile_rank(tweet_id: str, cohort: str) -> float
def get_maturity_level(hours_old: int) -> str  # "fresh", "settling", "mature"
def detect_strategy_decline() -> Optional[str]  # warning message if decline >20%
```

### Scoring Algorithm

```
maturity_trust = {
    "fresh": 0.2,      # 0-6 hours
    "settling": 0.7,   # 6-48 hours
    "mature": 1.0      # 48h+
}

time_decay_multiplier = exp(-age_days / 30)
score = sum(metric_value * weight) * maturity_trust * time_decay_multiplier
percentile = rank_score_within_cohort(format+topic+tone)
```

### Usage

```python
from scorer import scorer

score = scorer.score_tweet(tweet)
percentile = scorer.percentile_rank(tweet_id, "tactical_advice")
```

---

## 6. validator.py

**Purpose:** 11-rule pre-post quality gate

### Functions

```python
def validate_tweet(tweet_obj: Dict) -> Dict  # {"valid": bool, "failures": [...], "warnings": [...]}
```

### Rules

**Fatal (post blocked):**
1. Length 1-280 chars
2. No banned words
3. Valid archetype
4. Required fields present

**Warnings (logged but post proceeds):**
5. Engagement prediction not too low
6. Format not too repetitive
7. Topic on-strategy
8. Thread linked correctly
9. Post not at unusual hour
10. LLM confidence not too low
11. Not a duplicate

### Usage

```python
from validator import validator

result = validator.validate_tweet(tweet_obj)
if not result["valid"]:
    for failure in result["failures"]:
        print(f"FATAL: {failure}")
if result["warnings"]:
    for warn in result["warnings"]:
        print(f"WARN: {warn}")
```

---

## 7. experimenter.py

**Purpose:** Exploit/explore decision logic with diversity enforcement

### Functions

```python
def get_todays_plan() -> Dict
def compute_format_scores() -> Dict
def should_explore() -> bool
def get_novelty_bonus(archetype: str, topic: str) -> float  # 1.0-1.5
def check_diversity_quota(archetype: str, topic: str) -> bool
```

### Usage

```python
from experimenter import experimenter

plan = experimenter.get_todays_plan()
# Returns: {
#     "format_type": "Tactical Advice",
#     "topic_bucket": "time-management", 
#     "thread_length": 2,
#     "is_experiment": False
# }
```

---

## 8. strategist.py

**Purpose:** LLM-based daily strategy reflection

### Functions (Async)

```python
async def reflect_and_update_strategy() -> Optional[Dict]
async def analyze_patterns() -> Dict
async def generate_hypothesis() -> str
```

### Returns

```python
{
    "date": "2026-03-31",
    "confidence_level": "HIGH",
    "data_points": 87,
    "top_formats": [
        {"format": "Tactical Advice", "avg_score": 412, "confidence": "HIGH"}
    ],
    "recommendations": "EXPLOIT: Tactical Advice at 8 AM",
    "emerging_patterns": ["Thread length positively correlated with likes"],
    "retiring_patterns": ["Industry News is decaying"]
}
```

---

## 9. generator.py

**Purpose:** Async Mistral LLM tweet generation

### Classes

```python
class MistralAsyncClient:
    async def chat(system_message: str, user_message: str, temperature: float = 0.7) -> Optional[str]
```

### Functions (Async)

```python
async def generate_tweet_async(
    archetype: str,
    topic: str,
    thread_length: int = 1,
    is_experiment: bool = False,
    retry_count: int = 0
) -> Optional[Dict]

def generate_tweet(archetype: str, topic: str, thread_length: int = 1, is_experiment: bool = False) -> Optional[Dict]
```

### Returns

```python
{
    "text": "Today I learned that...",  # or text_parts[] for threads
    "archetype": "Tactical Advice",
    "topic": "time-management",
    "thread_length": 2,
    "confidence": 0.85,
    "reasoning": "Testing new time-of-day insight"
}
```

### Retry Logic

- Max 3 attempts
- 1s backoff between attempts
- Validation failure triggers retry
- Returns None after all attempts fail

---

## 10. poster.py

**Purpose:** Async X API posting + duplicate detection

### Classes

```python
class XAPIAsyncClient:
    async def post_tweet(text: str) -> Optional[Dict]
    async def post_thread(tweets: List[str]) -> Optional[Dict]
```

### Functions (Async)

```python
async def pre_post_validation(tweet_obj: Dict) -> bool
async def is_duplicate(tweet_obj: Dict, threshold: float = 0.75) -> bool
async def post_tweet_async(tweet_obj: Dict) -> Optional[Dict]

def post_tweet(tweet_obj: Dict) -> Optional[Dict]  # Sync wrapper
```

### Returns

```python
{
    "tweet_id": "1743123456789",
    "text": "Posted tweet text",
    "created_at": "2026-03-31T09:15:23Z",
    "thread_id": "1743123456789",  # if thread
    "parts": [],  # if thread
    "thread_length": 1
}
```

### Duplicate Detection

- TF-IDF vectorizer on 1-2 grams
- Cosine similarity against recent 7 days
- Threshold 0.75 (customizable)
- Returns True if match found

---

## 11. main.py

**Purpose:** 7-phase daily orchestrator

### Functions (Async)

```python
async def verify_environment() -> bool
async def phase_1_fetch_metrics() -> bool
async def phase_2_score_mature() -> bool
async def phase_3_update_strategy() -> bool
async def phase_4_plan_post() -> bool
async def phase_5_generate() -> bool
async def phase_6_validate() -> bool
async def phase_7_post() -> bool
async def run_daily_pipeline() -> bool
```

### Entry Point

```python
def main() -> None:
    # Executes full pipeline, exits with code 0 (success) or 1 (failure)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
```

### Usage

```bash
python main.py                    # Run full pipeline
python main.py --dry-run         # Simulate (no posting)
```

### Exit Codes

- `0` = All 7 phases passed
- `1` = Any fatal phase failed (4, 5, 6, 7)

---

## Complete Call Order (Daily)

```
main.py:main()
  └─ verify_environment()
  └─ phase_1_fetch_metrics()
      └─ fetcher.fetch_all_pending()
  └─ phase_2_score_mature()
      └─ memory.get_mature_tweets()
      └─ FOR EACH: scorer.score_tweet()
  └─ phase_3_update_strategy()
      └─ strategist.reflect_and_update_strategy()
  └─ phase_4_plan_post()
      └─ experimenter.get_todays_plan()
      └─ memory.add_strategy_log()
  └─ phase_5_generate()
      └─ generator.generate_tweet_async()
          └─ load_context()
          └─ build_generation_prompt()
          └─ MistralAsyncClient.chat()
          └─ validator.validate_tweet()
  └─ phase_6_validate()
      └─ validator.validate_tweet()
  └─ phase_7_post()
      └─ poster.post_tweet_async()
          └─ pre_post_validation()
          └─ is_duplicate()
          └─ XAPIAsyncClient.post_tweet()
          └─ memory.add_tweet_to_log()
          └─ memory.schedule_metric_fetch()
```

---

## Error Handling Quick Reference

| Error Type | Module | Handling | Log Level |
|------------|--------|----------|-----------|
| Missing env var | main | Halt with exit(1) | ERROR |
| API timeout | fetcher | Exponential backoff | WARN |
| JSON parse error | generator | Retry (max 3) | WARN |
| Validation fail | validator | Block post | ERROR |
| Duplicate detected | poster | Block post | ERROR |
| X API error | poster | Return None → log → halt | ERROR |

---

## Performance Tips

1. **Batch requests:** fetcher.py automatically batches metric fetches
2. **Minimize LLM calls:** strategist.py runs only if 10+ mature tweets
3. **Cache context:** generator.py loads context once per day
4. **Parallel scoring:** scorer.py can be parallelized (not currently)
5. **Async I/O:** All network calls use async/await

---

## Testing Checklist

```python
# 1. All imports work
python -c "import config, logger, memory, fetcher, scorer, validator, experimenter, strategist, generator, poster, main; print('OK')"

# 2. Logger writes JSON
logger.info("Test", event="TEST", data={"val": 1})  # Check logs/app.jsonl

# 3. Memory persistence
memory.add_tweet_to_log({"tweet_id": "1"}, {"id": "1"}, {})
tweets = memory.get_recent_tweets()
assert len(tweets) > 0

# 4. Validation passes
result = validator.validate_tweet({"text": "Hello world", "archetype": "Tactical Advice", "topic": "x", "thread_length": 1})
assert result["valid"] == True

# 5. Full pipeline (dry run)
XBOT_DRY_RUN=1 python main.py
```

---

## References

- **System Evolution:** See `SYSTEM_EVOLUTION.md` for old vs new comparison
- **Deployment:** See `PRODUCTION_READY.md` for deployment checklist
- **Niche Config:** Fill `config/niche.md` with bot identity
- **Strategy:** Auto-generated daily in `memory/strategy_log.jsonl`
