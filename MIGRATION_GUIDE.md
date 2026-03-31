# XBOT Migration Guide: Old System → Production System

## Overview

The old system (v1) was a simple daily tweet scheduler. The new system (v2) is a sophisticated multi-variable optimization engine with maturity-gated learning and anti-convergence mechanisms.

**Key Insight**: The old system suffered from **convergence** - it would optimize toward one format and repeat it forever. The new system enforces diversity and continuous learning.

---

## Major Architectural Changes

### OLD SYSTEM (v1)

```
researcher.py (main loop)
  ├── decide_thread_length()     → Random or learned
  ├── decide_topic()              → Random or learned
  ├── decide_archetype()          → Random or learned
  ├── generate_tweet()            → Call Mistral
  ├── post_tweet()                → Post to X
  └── log to experiments.jsonl

Data Storage:
  └── experiments.jsonl (flat JSON lines, no structure)
```

**Problems**:
- ❌ No maturity gating - learns from 1-day-old incomplete metrics
- ❌ Continuous re-scoring not implemented properly
- ❌ Local maxima - once format X scores highest, always use X (convergence)
- ❌ No diversity enforcement
- ❌ No confidence levels - learns too aggressively
- ❌ Hard to replay/debug - unstructured logging

---

### NEW SYSTEM (v2)

```
main.py (daily orchestrator)
  ├─ Phase 1: FETCH     → fetcher.py (collect metrics with priority scheduling)
  ├─ Phase 2: SCORE     → scorer.py (score only mature tweets, apply time decay)
  ├─ Phase 3: STRATEGIST → strategist.py (reflect using Mistral LLM)
  ├─ Phase 4: PLAN     → experimenter.py (65% exploit / 35% explore)
  ├─ Phase 5: GENERATE  → generator.py (create tweet with context)
  ├─ Phase 6: VALIDATE  → validator.py (11-rule pre-post gate)
  └─ Phase 7: POST      → poster.py (upload + memory storage)

Data Storage (Persistence Layer):
  ├── memory/
  │   ├── tweet_log.jsonl       (TweetRecord dataclass)
  │   ├── strategy_log.jsonl    (StrategySnapshot with confidence)
  │   └── pattern_library.jsonl (PatternRecord - abstracted learnings)
  ├── logs/
  │   └── xbot_YYYY-MM-DD.jsonl (Structured audit trail)
  └── data/
      └── todays_plan.json      (Inter-module communication)
```

**Improvements**:
- ✅ Maturity gating (48h+ only for strategy)
- ✅ Time decay scoring (60-day window)
- ✅ Forced diversity quotas (max 2x per combo per 7 days)
- ✅ Mandatory exploration (30% exploration budget, cannot optimize away)
- ✅ Confidence levels (low/medium/high gate optimization aggressiveness)
- ✅ Structured logging (JSON lines enable full system replay)
- ✅ Error handling (no silent failures)
- ✅ Rate limiting (exponential backoff, priority scheduling)

---

## Module Mapping

| OLD SYSTEM | NEW SYSTEM | Purpose |
|-----------|-----------|---------|
| researcher.py | main.py | Daily orchestrator |
| generator.py | generator.py | Mistral LLM integration (refactored) |
| poster.py | poster.py | X API posting (refactored) |
| scorer.py | scorer.py | Engagement scoring (completely rewritten) |
| (none) | config.py | Centralized configuration |
| (none) | logger.py | Structured JSON logging |
| (none) | memory.py | Typed data structures + persistence |
| (none) | fetcher.py | Metric collection with backoff |
| (none) | validator.py | Pre-post quality gate (11 rules) |
| (none) | experimenter.py | Exploration/exploitation balance |
| (none) | strategist.py | Learning engine (Mistral reflection) |
| strategy.md | strategy_log.jsonl | Strategy snapshots (now auto-generated) |
| (none) | PRODUCTION_STATUS.md | This documentation |

---

## Data Model Changes

### OLD: experiments.jsonl

```json
{
  "tweet_id": "1234567890",
  "text": "Tweet content",
  "posted_at": "2024-01-01T12:00:00Z",
  "archetype": "Reversal",
  "topic": "AI",
  "thread_length": 1,
  "posted_hour": 12,
  "tone": "contrarian",
  "score": null,        # Set after 24 hours
  "score_history": [],  # Re-scores tracked here
  "impressions": 0
}
```

**Problems**: Flat structure, no typing, score could be None, no maturity tracking

### NEW: tweet_log.jsonl + memory.py

```json
{
  "tweet_id": "1234567890",
  "content": "Tweet content",
  "posted_at": "2024-01-15T08:32:00Z",
  "format_type": "reversal",
  "topic_bucket": "ai_ml",
  "tone": "contrarian",
  "metrics": {
    "impressions": 1250,
    "likes": 45,
    "retweets": 12,
    "replies": 8,
    "quote_tweets": 3
  },
  "engagement_score": 127.5,
  "metrics_maturity": "mature",
  "is_experiment": false
}
```

**Improvements**: 
- ✅ Typed (TweetRecord dataclass)
- ✅ Metrics structured (TweetMetrics)
- ✅ Maturity tracking
- ✅ Historical queries optimized
- ✅ Persistence layer abstraction

---

## Config File Changes

### OLD: strategy.md (manual updates)

User had to manually edit strategy.md with:
- Current Best Formats
- Active Hypothesis
- Experiment History
- (rarely updated, often out of sync)

### NEW: strategy_log.jsonl (auto-generated daily)

```json
{
  "date": "2024-01-15T00:00:00Z",
  "version": 1,
  "confidence_level": "medium",
  "top_formats": ["reversal", "prediction"],
  "top_topics": ["ai_ml", "founder_reality"],
  "patterns_observed": [
    "Contrarian takes outperform balanced takes",
    "Threads > Single tweets"
  ],
  "hypothesis_to_test": "Test video content",
  "why_this_hypothesis": "Based on quote_tweet analysis",
  "next_experiment": "new_tone",
  "reasoning": "50 mature tweets analyzed, identifying patterns"
}
```

**Improvements**:
- ✅ Auto-generated by strategist.py
- ✅ Versioned for history
- ✅ Confidence levels
- ✅ Analysis reasoning included
- ✅ Always in sync with actual data

---

## Scoring Algorithm Changes

### OLD: compute_score()

```python
def compute_score(metrics):
    score = (
        metrics["like_count"] * 3 +
        metrics["retweet_count"] * 5 +
        metrics["reply_count"] * 4 +
        metrics["impression_count"] * 0.1
    )
    # No time decay
    # No maturity gating
    return score
```

**Problems**:
- ❌ Learns from 1-day-old incomplete data
- ❌ Old patterns weighted same as new patterns
- ❌ Could learn from partially-loaded tweets

### NEW: EngagementScorer

```python
class EngagementScorer:
    def score_tweet(self, tweet: TweetRecord) -> float:
        # STEP 1: Only score mature tweets (48h+)
        if tweet.metrics_maturity != "mature":
            return 0.0
        
        # STEP 2: Compute raw weighted score
        raw_score = self._compute_raw_score(tweet.metrics)
        # Weights: reply:7, quote:8, retweet:6, like:2, impression:0.05
        
        # STEP 3: Apply time decay (60-day window)
        decayed_score = self._apply_time_decay(raw_score, tweet.posted_at)
        
        # STEP 4: Store in memory
        memory.update_tweet_score(tweet.tweet_id, decayed_score)
        
        return decayed_score
```

**Improvements**:
- ✅ Maturity gating (48h+)
- ✅ Time decay (recent patterns weighted higher)
- ✅ Percentile ranking within cohorts
- ✅ Declining strategy detection
- ✅ Cohort statistics computation

---

## Diversity Enforcement (NEW)

### OLD SYSTEM: No diversity enforcement
- Once 3-piece threads scored highest, system posts only 3-piece threads
- **Result**: Convergence, audience gets bored

### NEW SYSTEM: Multiple diversity mechanisms

```python
class ExperimentManager:
    def get_todays_plan(self):
        # 1. Check diversity score of recent 14 tweets
        diversity = self._compute_diversity_score(recent_tweets)
        
        # 2. If diversity < 50%, force exploration
        if diversity < 0.5:
            return self._plan_exploration("forced_exploration")
        
        # 3. Check weekly schedule
        #    Mon=new_format, Wed=new_topic, Fri=structure_variant
        today = datetime.utcnow().weekday()
        scheduled_experiment = WEEKLY_EXPERIMENT_SCHEDULE[today]
        
        # 4. Choose exploit (65%) or explore (35%)
        if scheduled_experiment == "exploitation":
            return self._plan_exploitation()  # Use best combo
        else:
            return self._plan_exploration(scheduled_experiment)
```

**Guarantees**:
- ✅ Max 2 posts per (format, topic, tone) per 7 days
- ✅ 30% mandatory exploration
- ✅ Weekly schedule ensures format/topic/tone rotation
- ✅ Forced exploration if diversity drops

---

## Learning Engine Changes

### OLD: Manual pattern tracking

User would manually note findings:
- "Reversals score 350 on average"
- "Threads are better than single tweets"
- (Subjective, error-prone)

### NEW: Automated reflection

```python
class Strategist:
    async def reflect_and_update_strategy(self):
        # 1. Load mature tweets from last 14 days
        mature_tweets = memory.load_mature_tweets()
        
        # 2. Group by (format, topic, tone) cohorts
        cohort_stats = self._compute_cohort_stats(mature_tweets)
        
        # 3. Identify top 3 and bottom 3 performers
        top = self._identify_top_combinations(cohort_stats, k=3)
        bottom = self._identify_bottom_combinations(cohort_stats, k=3)
        
        # 4. Build context and call Mistral LLM
        prompt = self._build_reflection_prompt(cohort_stats, top, bottom, mature_tweets)
        
        # 5. Mistral generates strategic analysis
        response = await self._call_mistral(prompt)
        
        # 6. Determine confidence level based on data maturity
        confidence = self._compute_confidence_level(len(mature_tweets), cohorts)
        
        # 7. Save StrategySnapshot to strategy_log.jsonl
        memory.save_strategy(strategy_snapshot)
```

**Improvements**:
- ✅ Automated analysis (no manual work)
- ✅ Mistral-powered hypothesis generation
- ✅ Confidence gating (prevents over-optimization)
- ✅ Versioned strategy history

---

## Running the Old System

```bash
# Old system (researcher.py v1)
python researcher.py

# Posts manually, logs to experiments.jsonl
# No structured logging, no validation, simple daily loop
```

---

## Running the New System

```bash
# Step 1: Set environment variables
export NVIDIA_API_KEY="..."
export X_API_KEY="..."
export X_API_SECRET="..."
export X_ACCESS_TOKEN="..."
export X_ACCESS_TOKEN_SECRET="..."
export X_BEARER_TOKEN="..."

# Step 2: Test the full pipeline
python main.py

# Output:
# - Fetches metrics for 3-day-old tweets
# - Scores all mature (48h+) tweets
# - Updates strategy if 10+ mature tweets exist
# - Plans today's post (exploit vs explore)
# - Generates tweet using Mistral
# - Validates with 11 rules
# - Posts to X (or fails gracefully)
# - Logs everything to logs/xbot_YYYY-MM-DD.jsonl

# Step 3: Schedule with GitHub Actions
# Deploy .github/workflows/daily_post.yml
# Runs 8x daily (every 3 hours)
```

---

## Data Migration (if needed)

### Migrating experiments.jsonl to new system

```python
import json
from datetime import datetime
from memory import TweetRecord, TweetMetrics, memory

# Read old experiments.jsonl
with open("data/experiments.jsonl", "r") as f:
    for line in f:
        old_record = json.loads(line)
        
        # Map old format to new
        metrics = TweetMetrics(
            impressions=old_record.get("impressions", 0),
            likes=old_record.get("likes", 0),
            retweets=old_record.get("retweets", 0),
            replies=old_record.get("replies", 0),
            quote_tweets=old_record.get("quote_tweets", 0)
        )
        
        tweet = TweetRecord(
            tweet_id=old_record["tweet_id"],
            content=old_record.get("text", ""),
            posted_at=old_record["posted_at"],
            format_type=old_record.get("archetype", "unknown"),
            topic_bucket=old_record.get("topic", "unknown"),
            tone=old_record.get("tone", "unknown"),
            metrics=metrics,
            engagement_score=old_record.get("score"),
            metrics_maturity="mature" if old_record.get("score") else "fresh",
            is_experiment=old_record.get("is_experiment", False)
        )
        
        # Save to new system
        memory.save_tweet(tweet)

print("Migration complete!")
```

---

## Troubleshooting Migration

| Issue | Old System | New System |
|-------|-----------|-----------|
| No data loading | experiments.jsonl empty | Verify memory/tweet_log.jsonl exists |
| Scoring breaks | Score is None | Maturity check - need 48h+ data |
| Strategy not updating | Manual edit of strategy.md | Wait 10 mature tweets, strategist runs daily |
| Too many posts | No rate limiting | Check fetcher.py backoff settings |
| Convergence happening | Designed into system | Check experimenter.py - should enforce diversity |

---

## Performance Comparison

| Metric | Old System | New System |
|--------|-----------|-----------|
| Posts/Day | 5-10 | 8-10 |
| Learning Latency | 24h | 48h (maturity gated) |
| Convergence Risk | HIGH | LOW (diversity enforced) |
| Error Recovery | Manual | Automatic (try/except per phase) |
| Strategy Updates | Manual | Automatic (daily) |
| Logging | Minimal | Comprehensive (JSON structured) |
| Rate Limiting | None | Exponential backoff + priority scheduling |
| Quality Checking | None | 11-rule validator |
| Confidence Gating | None | low/medium/high levels |

---

## Timeline for Migration

**Week 1**: Set up new modules, verify config  
**Week 2**: Run main.py in test mode, monitor logs  
**Week 3**: Migrate historical data (optional)  
**Week 4**: Deploy GitHub Actions workflow  
**Week 5+**: Monitor compounding improvement over 90 days  

---

## Rollback Strategy

If new system has issues:
1. Keep researcher.py v1 as backup branch
2. Test new system thoroughly before removing old
3. GitHub Actions can quickly switch workflows
4. Data is all in JSON - easy to inspect/reprocess

---

## Questions?

See `PRODUCTION_STATUS.md`, `README_PRODUCTION.md`, or module docstrings for detailed info on any component.

