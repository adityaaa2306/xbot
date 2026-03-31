"""
fetcher.py — Metric Collection from X API (Priority 3: Metric Optimization)

Fetches public engagement metrics for tweets with batch processing and smart scheduling.
Handles rate limiting, backoff, incremental updates, and metric archival.

Priority 3 Enhancements:
- Batch fetching: Fetch up to 100 tweet IDs per API call (not one-by-one)
- Incremental updates: Only fetch new tweets and refresh stale ones
- Metric archival: Skip tweets 365+ days old (archived)
- Smart scheduling: Respect rate limits with exponential backoff
"""

import os
import time
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

import tweepy

import config
from logger import logger
from memory import TweetMetrics


class MetricsFetcher:
    """Fetch public metrics for tweets using X API v2 with batch processing."""

    def __init__(self):
        self.bearer_token = config.X_BEARER_TOKEN
        if not self.bearer_token:
            raise ValueError("X_BEARER_TOKEN not set in environment")
        
        self.client = tweepy.Client(bearer_token=self.bearer_token)
        self.backoff_multiplier = config.BACKOFF_MULTIPLIER
        self.backoff_current = config.BACKOFF_INITIAL
        self.batch_size = config.BATCH_FETCH_SIZE  # Default 100

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
                    error=str(e)
                )
                return None

        except Exception as e:
            logger.error(
                "Unexpected error during metric fetch",
                phase="FETCHER",
                data={"tweet_id": tweet_id},
                error=str(e)
            )
            return None

    def fetch_batch(self, tweet_ids: List[str]) -> Dict[str, Optional[TweetMetrics]]:
        """
        PRIORITY 3: Fetch metrics for multiple tweets efficiently.
        X API allows lookups of multiple tweet IDs in one call.
        
        Args:
            tweet_ids: List of tweet IDs (up to 100)
            
        Returns:
            Dict mapping tweet_id -> TweetMetrics
        """
        results = {}
        
        if not tweet_ids:
            return results
        
        # Limit to batch size
        tweet_ids = tweet_ids[:self.batch_size]
        
        try:
            # Fetch all tweets in one request
            response = self.client.get_tweets(
                ids=tweet_ids,
                tweet_fields=["public_metrics", "created_at"]
            )
            
            if not response.data:
                logger.warn(
                    "No tweets found in batch fetch",
                    phase="FETCHER",
                    data={"batch_size": len(tweet_ids)}
                )
                return results
            
            # Process each tweet
            for tweet in response.data:
                tweet_id = tweet.id
                metrics_dict = tweet.public_metrics
                
                metrics = TweetMetrics(
                    impressions=metrics_dict.get("impression_count", 0),
                    likes=metrics_dict.get("like_count", 0),
                    retweets=metrics_dict.get("retweet_count", 0),
                    replies=metrics_dict.get("reply_count", 0),
                    quote_tweets=metrics_dict.get("quote_tweet_count", 0),
                )
                
                results[tweet_id] = metrics
            
            # Reset backoff on success
            self.backoff_current = config.BACKOFF_INITIAL
            
            logger.info(
                f"Batch fetched metrics",
                phase="FETCHER",
                data={"batch_size": len(tweet_ids), "successful": len(results)}
            )
            
            return results
            
        except tweepy.TweepyException as e:
            if e.response.status_code == 429:  # Rate limited
                logger.warn(
                    "Rate limited during batch fetch",
                    phase="FETCHER",
                    data={"batch_size": len(tweet_ids), "backoff_seconds": self.backoff_current}
                )
                time.sleep(self.backoff_current)
                self.backoff_current = min(
                    self.backoff_current * self.backoff_multiplier,
                    config.BACKOFF_MAX
                )
                # Retry with smaller batch
                half = len(tweet_ids) // 2
                if half > 0:
                    results.update(self.fetch_batch(tweet_ids[:half]))
                    time.sleep(0.5)
                    results.update(self.fetch_batch(tweet_ids[half:]))
                return results
            else:
                logger.error(
                    "Failed batch fetch",
                    phase="FETCHER",
                    data={"batch_size": len(tweet_ids)},
                    error=str(e)
                )
                return results
        
        except Exception as e:
            logger.error(
                "Unexpected error during batch fetch",
                phase="FETCHER",
                data={"batch_size": len(tweet_ids)},
                error=str(e)
            )
            return results

    def fetch_all_pending(self, memory) -> int:
        """
        PRIORITY 3: Fetch metrics for tweets that need updating (incremental + batch).
        
        Priority:
        1. Tweets with NO metrics yet (age >= 2 hours, skip if > 365 days)
        2. Tweets in "fresh" state (refresh at 24h)
        3. Tweets in "settling" state (refresh at 72h)
        
        Optimized with:
        - Batch processing (group up to 100 fetches into 1 API call)
        - Metric archival (skip tweets 365+ days old)
        - Incremental updates (only process changed tweets)
        
        Args:
            memory: MemoryManager instance
            
        Returns:
            Number of tweets updated
        """
        tweets = memory.load_all_tweets()
        fetch_queue = []
        archived_count = 0
        
        now = datetime.utcnow()
        metric_archive_days = config.METRIC_ARCHIVE_DAYS
        
        for tweet in tweets:
            try:
                posted_at = datetime.fromisoformat(tweet.posted_at.replace("Z", "+00:00"))
                hours_old = (now - posted_at.replace(tzinfo=None)).total_seconds() / 3600
                days_old = hours_old / 24
                
                # PRIORITY 3: Skip archived tweets (365+ days)
                if days_old > metric_archive_days:
                    archived_count += 1
                    continue
                
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
                    fetch_queue.append((tweet.tweet_id, hours_old))
            
            except Exception as e:
                logger.warn(
                    f"Error parsing tweet for fetch scheduling",
                    phase="FETCHER",
                    error=str(e)
                )
                continue
        
        if archived_count > 0:
            logger.info(
                f"Skipped {archived_count} archived tweets",
                phase="FETCHER",
                data={"archive_days": metric_archive_days}
            )
        
        if not fetch_queue:
            logger.info(
                "No tweets to fetch",
                phase="FETCHER",
                data={"total_tweets": len(tweets), "archived": archived_count}
            )
            return 0
        
        # PRIORITY 3: Process in batches
        updated_count = 0
        batch_count = (len(fetch_queue) + self.batch_size - 1) // self.batch_size
        
        for batch_idx in range(batch_count):
            start_idx = batch_idx * self.batch_size
            end_idx = min(start_idx + self.batch_size, len(fetch_queue))
            batch = fetch_queue[start_idx:end_idx]
            
            tweet_ids = [t[0] for t in batch]
            logger.debug(
                f"Fetching batch {batch_idx + 1}/{batch_count}",
                phase="FETCHER",
                data={"batch_size": len(tweet_ids)}
            )
            
            # Batch fetch
            results = self.fetch_batch(tweet_ids)
            
            # Update memory with results
            for tweet_id, hours_old in batch:
                if tweet_id in results and results[tweet_id]:
                    metrics = results[tweet_id]
                    
                    # Determine maturity tier
                    if hours_old < 6:
                        maturity = "fresh"
                    elif hours_old < 48:
                        maturity = "settling"
                    else:
                        maturity = "mature"
                    
                    memory.update_tweet_metrics(tweet_id, metrics, maturity)
                    updated_count += 1
            
            # Small delay between batches to avoid rate limiting
            if batch_idx < batch_count - 1:
                time.sleep(0.5)
        
        logger.info(
            f"Fetched metrics for {updated_count} tweets",
            phase="FETCHER",
            data={
                "total_fetched": updated_count,
                "batches": batch_count,
                "archived_skipped": archived_count
            }
        )
        
        return updated_count


# Global fetcher instance
fetcher = MetricsFetcher()
