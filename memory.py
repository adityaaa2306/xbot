"""
memory.py — Persistent Memory & Data Structures

Core data types and persistence for:
- tweet_log (all posted tweets with metrics)
- strategy_log (daily strategy snapshots)
- pattern_library (abstracted learnings)
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict

import config
from logger import logger


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class TweetMetrics:
    """Engagement metrics for a single tweet."""
    impressions: int = 0
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    quote_tweets: int = 0

    def to_dict(self) -> Dict[str, int]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, int]) -> "TweetMetrics":
        return cls(**d)


@dataclass
class TweetRecord:
    """Complete record for a posted tweet."""
    tweet_id: str
    content: str
    posted_at: str  # ISO8601
    format_type: str  # "reversal", "prediction", etc.
    topic_bucket: str  # "ai_ml", "founder_reality", etc.
    tone: str  # "contrarian", "analytical", etc.
    
    hook: str = ""
    reasoning: str = ""
    
    metrics: Optional[TweetMetrics] = None
    engagement_score: Optional[float] = None
    metrics_fetched_at: Optional[str] = None
    metrics_maturity: str = "fresh"  # "fresh" | "settling" | "mature"
    
    hook_score: float = 0.0  # 0–10 pre-post validation score
    
    # Experiment tracking
    is_experiment: bool = False
    experiment_type: str = ""

    @property
    def text(self) -> str:
        return self.content

    @property
    def like_count(self) -> int:
        return self.metrics.likes if self.metrics else 0

    @property
    def reply_count(self) -> int:
        return self.metrics.replies if self.metrics else 0
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.metrics:
            d["metrics"] = self.metrics.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TweetRecord":
        metrics = d.pop("metrics", None)
        if metrics:
            metrics = TweetMetrics.from_dict(metrics)
        return cls(metrics=metrics, **d)


@dataclass
class StrategySnapshot:
    """Daily strategy configuration."""
    date: str  # ISO8601
    version: int
    
    top_formats: List[str]
    top_topics: List[str]
    top_tones: List[str]
    
    avoid_formats: List[str]
    avoid_topics: List[str]
    
    experiment_slot: Dict[str, Any]  # {"type": "new_format", ...}
    
    confidence_level: str  # "low" | "medium" | "high"
    confidence_data_count: int  # How many mature tweets informed this
    
    reasoning: str  # LLM-generated explanation
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "StrategySnapshot":
        return cls(**d)


@dataclass
class PatternRecord:
    """Abstracted learning from raw tweets."""
    pattern_id: str
    description: str  # e.g., "Questions about founder hiring score well"
    
    evidence_count: int  # How many tweets support this
    avg_score: float
    
    last_seen: str  # ISO8601 of last confirmation
    created_at: str  # ISO8601 when pattern discovered
    
    status: str  # "active" | "decaying" | "retired"
    
    supporting_tweet_ids: List[str] = None
    
    def __post_init__(self):
        if self.supporting_tweet_ids is None:
            self.supporting_tweet_ids = []

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PatternRecord":
        return cls(**d)


# ============================================================================
# MEMORY MANAGER
# ============================================================================

class MemoryManager:
    """Manages persistence of all system memory."""

    def __init__(self):
        self.tweet_log_path = Path(config.TWEET_LOG_FILE)
        self.strategy_log_path = Path(config.STRATEGY_LOG_FILE)
        self.pattern_library_path = Path(config.PATTERN_LIBRARY_FILE)
        
        # Ensure files exist
        for path in [self.tweet_log_path, self.strategy_log_path, self.pattern_library_path]:
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.touch()

    # ========================================================================
    # TWEET LOG
    # ========================================================================

    def save_tweet(self, tweet: TweetRecord) -> None:
        """Append tweet to log."""
        try:
            with open(self.tweet_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(tweet.to_dict()) + "\n")
            logger.debug("Saved tweet", phase="MEMORY", data={"tweet_id": tweet.tweet_id})
        except IOError as e:
            logger.error("Failed to save tweet", phase="MEMORY", error=e)

    def update_tweet_metrics(self, tweet_id: str, metrics: TweetMetrics, maturity: str) -> None:
        """Update metrics for existing tweet."""
        try:
            records = self.load_all_tweets()
            found = False
            
            for record in records:
                if record.tweet_id == tweet_id:
                    record.metrics = metrics
                    record.metrics_fetched_at = datetime.utcnow().isoformat() + "Z"
                    record.metrics_maturity = maturity
                    found = True
                    break
            
            if found:
                self._write_tweet_log(records)
                logger.debug("Updated tweet metrics", phase="MEMORY", data={"tweet_id": tweet_id})
            else:
                logger.warn("Tweet not found for update", phase="MEMORY", data={"tweet_id": tweet_id})
        except Exception as e:
            logger.error("Failed to update tweet metrics", phase="MEMORY", error=e)

    def update_tweet_score(self, tweet_id: str, score: float) -> None:
        """Update engagement score for existing tweet."""
        try:
            records = self.load_all_tweets()
            
            for record in records:
                if record.tweet_id == tweet_id:
                    record.engagement_score = score
                    break
            
            self._write_tweet_log(records)
            logger.debug("Updated tweet score", phase="MEMORY", data={"tweet_id": tweet_id, "score": score})
        except Exception as e:
            logger.error("Failed to update tweet score", phase="MEMORY", error=e)

    def load_all_tweets(self) -> List[TweetRecord]:
        """Load all tweets from log."""
        tweets = []
        try:
            with open(self.tweet_log_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        tweet = TweetRecord.from_dict(json.loads(line))
                        tweets.append(tweet)
        except Exception as e:
            logger.error("Failed to load tweets", phase="MEMORY", error=e)
        return tweets

    def load_recent_tweets(self, days: int = 30) -> List[TweetRecord]:
        """Load tweets from last N days."""
        all_tweets = self.load_all_tweets()
        cutoff = datetime.utcnow().timestamp() - (days * 86400)
        
        return [
            t for t in all_tweets
            if datetime.fromisoformat(t.posted_at.replace("Z", "+00:00")).timestamp() > cutoff
        ]

    def get_recent_tweets(self, days: int = 30, limit: Optional[int] = None) -> List[TweetRecord]:
        """Compatibility wrapper for the production pipeline."""
        tweets = sorted(self.load_recent_tweets(days=days), key=lambda tweet: tweet.posted_at, reverse=True)
        return tweets[:limit] if limit else tweets

    def load_mature_tweets(self) -> List[TweetRecord]:
        """Load only tweets with mature metrics (48h+)."""
        return [t for t in self.load_all_tweets() if t.metrics_maturity == "mature"]

    def get_mature_tweets(self) -> List[TweetRecord]:
        """Compatibility wrapper for the production pipeline."""
        return self.load_mature_tweets()

    def update_score(self, tweet_id: str, score: float) -> None:
        """Compatibility wrapper for the production pipeline."""
        self.update_tweet_score(tweet_id, score)

    def _write_tweet_log(self, tweets: List[TweetRecord]) -> None:
        """Rewrite entire tweet log (for updates)."""
        with open(self.tweet_log_path, "w", encoding="utf-8") as f:
            for tweet in tweets:
                f.write(json.dumps(tweet.to_dict()) + "\n")

    # ========================================================================
    # STRATEGY LOG
    # ========================================================================

    def save_strategy(self, strategy: StrategySnapshot) -> None:
        """Append strategy snapshot to log."""
        try:
            if isinstance(strategy, dict):
                strategy = StrategySnapshot(
                    date=strategy.get("date", datetime.utcnow().isoformat() + "Z"),
                    version=int(strategy.get("version", len(self.load_all_strategies()) + 1)),
                    top_formats=list(strategy.get("top_formats", [])),
                    top_topics=list(strategy.get("top_topics", [])),
                    top_tones=list(strategy.get("top_tones", [])),
                    avoid_formats=list(strategy.get("avoid_formats", [])),
                    avoid_topics=list(strategy.get("avoid_topics", [])),
                    experiment_slot=strategy.get("experiment_slot", {"type": strategy.get("next_experiment", "continue_exploration")}),
                    confidence_level=strategy.get("confidence_level", "low"),
                    confidence_data_count=int(strategy.get("confidence_data_count", 0)),
                    reasoning=strategy.get("reasoning", ""),
                )
            with open(self.strategy_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(strategy.to_dict()) + "\n")
            self._write_strategy_markdown(strategy)
            logger.info("Saved strategy snapshot", phase="MEMORY", data={"version": strategy.version})
        except IOError as e:
            logger.error("Failed to save strategy", phase="MEMORY", error=e)

    def load_latest_strategy(self) -> Optional[StrategySnapshot]:
        """Load most recent strategy snapshot."""
        try:
            with open(self.strategy_log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            if lines:
                latest = StrategySnapshot.from_dict(json.loads(lines[-1]))
                return latest
        except Exception as e:
            logger.warn("Failed to load latest strategy", phase="MEMORY", error=e)
        return None

    def load_all_strategies(self) -> List[StrategySnapshot]:
        """Load all strategy snapshots."""
        strategies = []
        try:
            with open(self.strategy_log_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        strategy = StrategySnapshot.from_dict(json.loads(line))
                        strategies.append(strategy)
        except Exception as e:
            logger.error("Failed to load strategies", phase="MEMORY", error=e)
        return strategies

    def get_strategy_logs(self, days: int = 30) -> List[Dict[str, Any]]:
        """Return recent strategies as dictionaries for prompt context."""
        cutoff = datetime.utcnow().timestamp() - (days * 86400)
        recent = []
        for strategy in self.load_all_strategies():
            try:
                ts = datetime.fromisoformat(strategy.date.replace("Z", "+00:00")).timestamp()
                if ts > cutoff:
                    recent.append(strategy.to_dict())
            except ValueError:
                recent.append(strategy.to_dict())
        recent.sort(key=lambda item: item.get("date", ""), reverse=True)
        return recent

    # ========================================================================
    # PATTERN LIBRARY
    # ========================================================================

    def save_pattern(self, pattern: PatternRecord) -> None:
        """Add or update pattern in library."""
        try:
            patterns = self.load_all_patterns()
            # Remove old version if exists
            patterns = [p for p in patterns if p.pattern_id != pattern.pattern_id]
            # Add new version
            patterns.append(pattern)
            
            with open(self.pattern_library_path, "w", encoding="utf-8") as f:
                for p in patterns:
                    f.write(json.dumps(p.to_dict()) + "\n")
            
            logger.debug("Saved pattern", phase="MEMORY", data={"pattern_id": pattern.pattern_id})
        except Exception as e:
            logger.error("Failed to save pattern", phase="MEMORY", error=e)

    def load_all_patterns(self) -> List[PatternRecord]:
        """Load all patterns from library."""
        patterns = []
        try:
            with open(self.pattern_library_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        pattern = PatternRecord.from_dict(json.loads(line))
                        patterns.append(pattern)
        except Exception as e:
            logger.error("Failed to load patterns", phase="MEMORY", error=e)
        return patterns

    def load_active_patterns(self) -> List[PatternRecord]:
        """Load only active (non-decaying) patterns."""
        return [p for p in self.load_all_patterns() if p.status == "active"]

    def _write_strategy_markdown(self, strategy: StrategySnapshot) -> None:
        """Keep the repo-level strategy.md aligned with the latest snapshot."""
        lines = [
            "# Content Strategy - Autonomous Learning Log",
            "",
            f"Last Updated: {strategy.date}",
            "",
            "## Current Best Formats",
        ]
        if strategy.top_formats:
            for fmt, topic, tone in zip(strategy.top_formats, strategy.top_topics, strategy.top_tones):
                lines.append(f"- `{fmt}` on `{topic}` with `{tone}` tone.")
        else:
            lines.append("- Not enough mature tweets yet.")

        lines.extend(["", "## Avoid For Now"])
        if strategy.avoid_formats:
            for fmt, topic in zip(strategy.avoid_formats, strategy.avoid_topics):
                lines.append(f"- Reduce `{fmt}` on `{topic}`.")
        else:
            lines.append("- No weak cohorts identified yet.")

        lines.extend(
            [
                "",
                "## Active Hypothesis",
                f"- {strategy.experiment_slot.get('type', 'continue_exploration')}",
                "",
                "## Confidence",
                f"- Level: `{strategy.confidence_level}` from {strategy.confidence_data_count} mature tweets.",
                "",
                "## Reasoning",
                strategy.reasoning or "No reasoning recorded.",
                "",
            ]
        )

        with open("strategy.md", "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines))

    def add_tweet_to_log(self, tweet_obj: Dict[str, Any], result: Dict[str, Any], plan: Dict[str, Any]) -> TweetRecord:
        """Persist a posted tweet using the canonical memory schema."""
        raw_text = tweet_obj.get("text") or tweet_obj.get("tweet") or ""
        if isinstance(raw_text, list):
            content = "\n".join(raw_text)
        else:
            content = str(raw_text)

        posted_at = result.get("posted_at") or result.get("created_at") or datetime.utcnow().isoformat() + "Z"
        tweet_record = TweetRecord(
            tweet_id=str(result.get("tweet_id") or result.get("thread_id")),
            content=content,
            posted_at=posted_at,
            format_type=tweet_obj.get("format_type") or plan.get("format_type") or "observation",
            topic_bucket=tweet_obj.get("topic_bucket") or plan.get("topic_bucket") or "ai_ml",
            tone=tweet_obj.get("tone") or plan.get("tone") or "analytical",
            hook=tweet_obj.get("hook", ""),
            reasoning=tweet_obj.get("reasoning", ""),
            metrics=None,
            engagement_score=None,
            metrics_fetched_at=None,
            metrics_maturity="fresh",
            hook_score=float(tweet_obj.get("hook_score", 0.0)),
            is_experiment=bool(plan.get("is_experiment", False)),
            experiment_type=plan.get("experiment_type") or "",
        )
        self.save_tweet(tweet_record)
        return tweet_record

    def schedule_metric_fetch(self, tweet_id: str, delay_hours: int) -> None:
        """Compatibility hook for poster scheduling."""
        logger.debug(
            "Metric fetch scheduled",
            phase="MEMORY",
            data={"tweet_id": tweet_id, "delay_hours": delay_hours},
        )


# Global memory manager instance
memory = MemoryManager()
