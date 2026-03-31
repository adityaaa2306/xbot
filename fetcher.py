"""
fetcher.py — Metric Collection from X API

Fetches public engagement metrics for tweets.
Handles rate limiting, backoff, and error recovery.
"""

import os
import time
from typing import Optional, Dict, Any

import tweepy

import config
from logger import logger
from memory import TweetMetrics


class MetricsFetcher:
    """Fetch public metrics for tweets using X API v2."""

    def __init__(self):
        self.bearer_token = config.X_BEARER_TOKEN
        if not self.bearer_token:
            raise ValueError("X_BEARER_TOKEN not set in environment")
        
        self.client = tweepy.Client(bearer_token=self.bearer_token)
        self.backoff_multiplier = config.BACKOFF_MULTIPLIER
        self.backoff_current = config.BACKOFF_INITIAL

    def fetch_metrics(self, tweet_id: str) -> Optional[TweetMetrics]:
        """
        Fetch public metrics for a single tweet.
        
        Args:
            tweet_id: X tweet ID
            
        Returns:
            TweetMetrics object or None if fetch failed
        """
        try:
            response = self.client.get_tweet(
                id=tweet_id,
                tweet_fields=["public_metrics", "created_at"]
            )

            if not response.data:
                logger.warn(
                    "Tweet not found or not public",
                    phase="FETCHER",
                    data={"tweet_id": tweet_id}
                )
                return None

            metrics_dict = response.data.public_metrics
            
            metrics = TweetMetrics(
                impressions=metrics_dict.get("impression_count", 0),
                likes=metrics_dict.get("like_count", 0),
                retweets=metrics_dict.get("retweet_count", 0),
                replies=metrics_dict.get("reply_count", 0),
                quote_tweets=metrics_dict.get("quote_tweet_count", 0),
            )

            # Reset backoff on success
            self.backoff_current = config.BACKOFF_INITIAL
            
            logger.debug(
                "Fetched metrics",
                phase="FETCHER",
                data={"tweet_id": tweet_id, "metrics": metrics.to_dict()}
            )
            
            return metrics

        except tweepy.TweepyException as e:
            if e.response.status_code == 429:  # Rate limited
                logger.warn(
                    "Rate limited during fetch",
                    phase="FETCHER",
                    data={"backoff_seconds": self.backoff_current}
                )
                time.sleep(self.backoff_current)
                self.backoff_current = min(
                    self.backoff_current * self.backoff_multiplier,
                    config.BACKOFF_MAX
                )
                # Retry once after backoff
                return self.fetch_metrics(tweet_id)
            else:
                logger.error(
                    "Failed to fetch metrics",
                    phase="FETCHER",
                    data={"tweet_id": tweet_id},
                    error=e
                )
                return None

        except Exception as e:
            logger.error(
                "Unexpected error during metric fetch",
                phase="FETCHER",
                data={"tweet_id": tweet_id},
                error=e
            )
            return None

    def fetch_batch(self, tweet_ids: list[str]) -> Dict[str, Optional[TweetMetrics]]:
        """
        Fetch metrics for multiple tweets.
        
        Args:
            tweet_ids: List of tweet IDs
            
        Returns:
            Dict mapping tweet_id -> TweetMetrics
        """
        results = {}
        for tweet_id in tweet_ids:
            results[tweet_id] = self.fetch_metrics(tweet_id)
            # Small delay between requests to avoid rate limiting
            time.sleep(0.1)
        
        return results

    def fetch_all_pending(self, memory) -> int:
        """
        Fetch metrics for tweets that haven't been fetched yet or need refreshing.
        
        Priority:
        1. Tweets with NO metrics yet (age >= 2 hours)
        2. Tweets in "fresh" state (refresh at 24h)
        3. Tweets in "settling" state (refresh at 72h)
        
        Args:
            memory: MemoryManager instance
            
        Returns:
            Number of tweets fetched
        """
        tweets = memory.load_all_tweets()
        fetched_count = 0
        
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        
        for tweet in tweets:
            posted_at = datetime.fromisoformat(tweet.posted_at.replace("Z", "+00:00"))
            hours_old = (now - posted_at.replace(tzinfo=None)).total_seconds() / 3600
            
            should_fetch = False
            
            # Priority 1: No metrics yet, 2+ hours old
            if not tweet.metrics and hours_old >= 2:
                should_fetch = True
            
            # Priority 2: Fresh metrics (refresh at 24h)
            elif tweet.metrics_maturity == "fresh" and hours_old >= 24:
                should_fetch = True
            
            # Priority 3: Settling metrics (refresh at 72h)
            elif tweet.metrics_maturity == "settling" and hours_old >= 72:
                should_fetch = True
            
            if should_fetch:
                metrics = self.fetch_metrics(tweet.tweet_id)
                if metrics:
                    # Determine maturity tier
                    if hours_old < 6:
                        maturity = "fresh"
                    elif hours_old < 48:
                        maturity = "settling"
                    else:
                        maturity = "mature"
                    
                    memory.update_tweet_metrics(tweet.tweet_id, metrics, maturity)
                    fetched_count += 1
        
        logger.info(
            "Fetched metrics for pending tweets",
            phase="FETCHER",
            data={"fetched_count": fetched_count}
        )
        
        return fetched_count


# Global fetcher instance
fetcher = MetricsFetcher()
