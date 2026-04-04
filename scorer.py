"""
scorer.py — Engagement Scoring with Maturity System

Computes weighted scores only from mature metrics (48h+).
Uses percentile ranking within cohorts to prevent local maxima.
Applies time decay to give more weight to recent patterns.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple

import config
from logger import logger
from memory import TweetRecord, TweetMetrics, memory



class EngagementScorer:
    """Computes engagement scores with maturity gating and percentile ranking."""

    def __init__(self):
        self.engagement_weights = config.ENGAGEMENT_WEIGHTS

    def score_tweet(self, tweet: TweetRecord) -> float:
        """
        Score a single mature tweet using weighted engagement metrics.
        
        Only scores tweets with maturity = "mature" (48h+ engagement data).
        
        Args:
            tweet: TweetRecord with populated metrics
            
        Returns:
            float: Weighted engagement score
        """
        if not tweet.metrics:
            logger.warn(
                f"Tweet {tweet.tweet_id} has no metrics",
                phase="SCORER"
            )
            return 0.0

        # Only score mature tweets
        if tweet.metrics_maturity != "mature":
            logger.debug(
                f"Tweet {tweet.tweet_id} not mature, skipping score",
                phase="SCORER",
                data={"maturity": tweet.metrics_maturity}
            )
            return 0.0

        # Compute raw weighted score
        raw_score = self._compute_raw_score(tweet.metrics)

        # Apply time decay (recent tweets weighted higher)
        decayed_score = self._apply_time_decay(raw_score, tweet.posted_at)

        # Update tweet record
        memory.update_tweet_score(tweet.tweet_id, decayed_score)

        logger.debug(
            f"Scored tweet {tweet.tweet_id}",
            phase="SCORER",
            data={"raw_score": round(raw_score, 1), "decayed_score": round(decayed_score, 1)}
        )

        return decayed_score

    def _compute_raw_score(self, metrics: TweetMetrics) -> float:
        """
        Compute raw weighted score from engagement metrics.
        
        Formula: (impressions × 0.05) + (likes × 2.0) + (retweets × 6.0) + 
                 (replies × 7.0) + (quote_tweets × 8.0)
                 
        Weights favor conversation (replies/quotes) over passive metrics.
        """
        score = 0.0

        if metrics.impressions:
            score += metrics.impressions * self.engagement_weights.get("impression", 0.05)

        if metrics.likes:
            score += metrics.likes * self.engagement_weights.get("like", 2.0)

        if metrics.retweets:
            score += metrics.retweets * self.engagement_weights.get("retweet", 6.0)

        if metrics.replies:
            score += metrics.replies * self.engagement_weights.get("reply", 7.0)

        if metrics.quote_tweets:
            score += metrics.quote_tweets * self.engagement_weights.get("quote_tweet", 8.0)

        return round(score, 2)

    def _apply_time_decay(self, score: float, posted_at_str: str) -> float:
        """
        Apply exponential time decay to emphasize recent patterns.
        
        Decay schedule (60-day window):
        - 0-3 days:   100% weight
        - 7 days:    90% weight
        - 14 days:   70% weight
        - 30 days:   40% weight
        - 60 days:   0% weight (dropped)
        
        Args:
            score: Raw engagement score
            posted_at_str: ISO 8601 timestamp when posted
            
        Returns:
            float: Score with decay applied
        """
        try:
            posted_at = datetime.fromisoformat(posted_at_str.replace("Z", "+00:00"))
            if posted_at.tzinfo is None:
                posted_at = posted_at.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            days_old = (now - posted_at).days

            # Linear decay over 60 days
            max_age = 60
            if days_old >= max_age:
                return 0.0

            decay_factor = max(0, 1.0 - (days_old / max_age))
            return round(score * decay_factor, 2)

        except Exception as e:
            logger.warn(
                f"Failed to compute time decay: {str(e)}",
                phase="SCORER",
                error=str(e)
            )
            return score

    def score_all_mature(self) -> int:
        """
        Score all mature tweets in memory.
        
        Returns:
            int: Count of tweets scored
        """
        mature_tweets = memory.load_mature_tweets()

        if not mature_tweets:
            logger.debug("No mature tweets to score", phase="SCORER")
            return 0

        scored_count = 0
        for tweet in mature_tweets:
            try:
                self.score_tweet(tweet)
                scored_count += 1
            except Exception as e:
                logger.warn(
                    f"Failed to score tweet {tweet.tweet_id}: {str(e)}",
                    phase="SCORER",
                    tweet_id=tweet.tweet_id,
                    error=str(e)
                )

        logger.info(
            f"Scored {scored_count} mature tweets",
            phase="SCORER",
            data={"count": scored_count}
        )

        return scored_count

    def percentile_rank(self, score: float, cohort_scores: List[float]) -> float:
        """
        Rank a score relative to others in its cohort.
        
        Percentile ranking prevents the system from optimizing locally.
        A score of 100 is better than 99 of 100 scores only if it's truly top 1%.
        
        Args:
            score: The score to rank
            cohort_scores: List of scores from same (format, topic, tone) cohort
            
        Returns:
            float: Percentile (0.0 to 1.0) where 1.0 is best in cohort
        """
        if not cohort_scores:
            return 0.5

        sorted_scores = sorted(cohort_scores)
        rank = sum(1 for s in sorted_scores if s <= score) / len(sorted_scores)

        return round(rank, 2)

    def get_cohort(
        self,
        format_type: str,
        topic_bucket: str,
        tone: str
    ) -> Dict[str, any]:
        """
        Get all mature tweets in a specific (format, topic, tone) cohort.
        
        Args:
            format_type: Tweet format (e.g., "reversal")
            topic_bucket: Topic (e.g., "ai_ml")
            tone: Tone (e.g., "contrarian")
            
        Returns:
            dict: {
                "tweets": [TweetRecord, ...],
                "scores": [float, ...],
                "avg_score": float,
                "median_score": float,
                "min_score": float,
                "max_score": float,
                "n": int
            }
        """
        mature_tweets = memory.load_mature_tweets()

        cohort_tweets = [
            t for t in mature_tweets
            if t.format_type == format_type
            and t.topic_bucket == topic_bucket
            and t.tone == tone
        ]

        scores = [t.engagement_score for t in cohort_tweets if t.engagement_score is not None]

        if not scores:
            return {
                "tweets": [],
                "scores": [],
                "avg_score": 0.0,
                "median_score": 0.0,
                "min_score": 0.0,
                "max_score": 0.0,
                "n": 0,
            }

        sorted_scores = sorted(scores)
        median = sorted_scores[len(sorted_scores) // 2] if sorted_scores else 0.0

        return {
            "tweets": cohort_tweets,
            "scores": scores,
            "avg_score": round(sum(scores) / len(scores), 1),
            "median_score": round(median, 1),
            "min_score": round(min(scores), 1),
            "max_score": round(max(scores), 1),
            "n": len(cohort_tweets),
        }

    def get_cohort_stats(self) -> Dict[tuple, Dict]:
        """
        Compute stats for all (format, topic, tone) cohorts.
        
        Returns:
            dict: {
                (format, topic, tone): {
                    "avg_score": float,
                    "n": int,
                    "percentile": float
                },
                ...
            }
        """
        mature_tweets = memory.load_mature_tweets()

        if not mature_tweets:
            return {}

        # Group by cohort
        cohorts = {}
        for tweet in mature_tweets:
            key = (tweet.format_type, tweet.topic_bucket, tweet.tone)
            if key not in cohorts:
                cohorts[key] = []
            if tweet.engagement_score is not None:
                cohorts[key].append(tweet.engagement_score)

        # Compute stats
        stats = {}
        for key, scores in cohorts.items():
            if scores:
                stats[key] = {
                    "avg_score": round(sum(scores) / len(scores), 1),
                    "n": len(scores),
                }

        return stats

    def detect_declining_strategies(self) -> List[tuple]:
        """
        Detect (format, topic, tone) combinations that are declining.
        
        Compares performance:
        - Last 7 days vs last 30 days
        
        Returns:
            list: List of declining cohorts as (format, topic, tone) tuples
        """
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        recent_tweets = [
            t for t in memory.load_mature_tweets()
            if self._parse_posted_at(t.posted_at) > week_ago
        ]

        older_tweets = [
            t for t in memory.load_mature_tweets()
            if month_ago
            < self._parse_posted_at(t.posted_at)
            < now
        ]

        # Group by cohort
        recent_cohorts = {}
        older_cohorts = {}

        for tweet in recent_tweets:
            key = (tweet.format_type, tweet.topic_bucket, tweet.tone)
            if key not in recent_cohorts:
                recent_cohorts[key] = []
            if tweet.engagement_score is not None:
                recent_cohorts[key].append(tweet.engagement_score)

        for tweet in older_tweets:
            key = (tweet.format_type, tweet.topic_bucket, tweet.tone)
            if key not in older_cohorts:
                older_cohorts[key] = []
            if tweet.engagement_score is not None:
                older_cohorts[key].append(tweet.engagement_score)

        # Compare
        declining = []
        decline_threshold = 0.8  # 20% drop

        for cohort, recent_scores in recent_cohorts.items():
            if cohort not in older_cohorts:
                continue

            older_scores = older_cohorts[cohort]
            if not older_scores or not recent_scores:
                continue

            older_avg = sum(older_scores) / len(older_scores)
            recent_avg = sum(recent_scores) / len(recent_scores)

            if recent_avg < (older_avg * decline_threshold):
                declining.append(cohort)
                logger.warn(
                    f"Declining strategy: {cohort}",
                    phase="SCORER",
                    data={
                        "old_avg": round(older_avg, 1),
                        "recent_avg": round(recent_avg, 1),
                        "decline": round((1 - recent_avg / older_avg) * 100, 1),
                    }
                )

        return declining

    def _parse_posted_at(self, posted_at_str: str) -> datetime:
        """Parse timestamps into timezone-aware UTC datetimes."""
        posted_at = datetime.fromisoformat(posted_at_str.replace("Z", "+00:00"))
        if posted_at.tzinfo is None:
            posted_at = posted_at.replace(tzinfo=timezone.utc)
        return posted_at.astimezone(timezone.utc)


# Global scorer instance
scorer = EngagementScorer()

