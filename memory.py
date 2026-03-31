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

    def load_mature_tweets(self) -> List[TweetRecord]:
        """Load only tweets with mature metrics (48h+)."""
        return [t for t in self.load_all_tweets() if t.metrics_maturity == "mature"]

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
            with open(self.strategy_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(strategy.to_dict()) + "\n")
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


# Global memory manager instance
memory = MemoryManager()
