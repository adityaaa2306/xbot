"""
poster.py — Async X (Twitter) API Integration (Priority 4: Compliance)

Posts tweets and threads to X via official API v2.
Features:
- Async wrapper around tweepy (runs in executor)
- Pre-post validation (11 checks)
- Duplicate detection via TF-IDF cosine similarity
- Thread handling (replies linked correctly)
- Memory integration for logging
- User-Agent identification (XBot automation)
- Rate limit tracking and compliance

Priority 4 Enhancements:
- User-Agent header: Identifies posts as automated (XBot1.0)
- Rate limit buffer: Stays at 80% of API limits to avoid hard blocks
- Request tracking: Logs API usage for compliance audits
- Graceful degradation: Backs off when approaching limits
"""

import asyncio
import json
import os
import time
from typing import Optional, Dict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

import tweepy
import config
from logger import logger
from memory import memory
from validator import validator


# X API Keys from environment
X_API_KEY = os.getenv("X_API_KEY", "")
X_API_SECRET = os.getenv("X_API_SECRET", "")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN", "")
X_ACCESS_TOKEN_SECRET = os.getenv("X_ACCESS_TOKEN_SECRET", "")
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN", "")


class RateLimitTracker:
    """PRIORITY 4: Track X API rate limits and enforce buffer."""
    
    def __init__(self, limit_buffer_percent=config.RATE_LIMIT_BUFFER):
        self.limit_buffer_percent = limit_buffer_percent  # e.g., 80%
        self.posts_today = 0
        self.posts_limit_daily = 50  # X allows ~50 posts per 24h window
        self.last_reset = datetime.utcnow()
    
    def can_post(self) -> bool:
        """Check if we can post without hitting rate limits."""
        # Reset daily counter every 24h
        now = datetime.utcnow()
        if (now - self.last_reset).total_seconds() > 86400:
            self.posts_today = 0
            self.last_reset = now
        
        # Check if we're at the buffer limit
        limit_threshold = (self.limit_buffer_percent / 100) * self.posts_limit_daily
        
        if self.posts_today >= limit_threshold:
            remaining_until_hard_limit = self.posts_limit_daily - self.posts_today
            logger.warn(
                "Rate limit buffer reached",
                phase="POSTER",
                data={
                    "posts_today": self.posts_today,
                    "buffer_limit": limit_threshold,
                    "hard_limit": self.posts_limit_daily,
                    "remaining": remaining_until_hard_limit
                }
            )
            return False
        
        return True
    
    def record_post(self):
        """Record that we posted something."""
        self.posts_today += 1
        logger.info(
            "Post recorded for rate limit tracking",
            phase="POSTER",
            data={
                "posts_today": self.posts_today,
                "limit": self.posts_limit_daily,
                "percentage_used": f"{(self.posts_today/self.posts_limit_daily)*100:.1f}%"
            }
        )


class XAPIAsyncClient:
    """Async wrapper for tweepy X API client with compliance headers."""
    
    def __init__(self):
        # OAuth1.0a authentication (User Context)
        auth = tweepy.OAuth1UserHandler(
            X_API_KEY,
            X_API_SECRET,
            X_ACCESS_TOKEN,
            X_ACCESS_TOKEN_SECRET
        )
        self.client = tweepy.API(auth)
        self.executor = ThreadPoolExecutor(max_workers=1)
        
        # PRIORITY 4: Add User-Agent header for compliance
        self.user_agent = config.USER_AGENT
        self._setup_headers()
    
    def _setup_headers(self):
        """PRIORITY 4: Configure User-Agent header identifying XBot."""
        try:
            # Set User-Agent on the client
            self.client.request_headers = {
                "User-Agent": self.user_agent
            }
            logger.info(
                "X API headers configured",
                phase="POSTER",
                data={"user_agent": self.user_agent}
            )
        except Exception as e:
            logger.warn(
                "Failed to set User-Agent header",
                phase="POSTER",
                error=str(e)
            )
    
    async def post_tweet(self, text: str) -> Optional[Dict]:
        """Post a single tweet asynchronously."""
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                self.executor,
                lambda: self.client.create_tweet(text=text)
            )
            return {
                "tweet_id": result.id,
                "text": result.text,
                "created_at": str(result.created_at)
            }
        except Exception as e:
            logger.error(f"X API tweet post failed: {str(e)}", 
                        phase="POSTER", error=str(e))
            return None
    
    async def post_thread(self, tweets: list) -> Optional[Dict]:
        """Post a thread (replies linked)."""
        results = []
        reply_to_id = None
        
        for text in tweets:
            loop = asyncio.get_event_loop()
            try:
                result = await loop.run_in_executor(
                    self.executor,
                    lambda t=text, rid=reply_to_id: self.client.create_tweet(
                        text=t, 
                        in_reply_to_status_id=rid
                    )
                )
                results.append({
                    "tweet_id": result.id,
                    "text": result.text,
                    "created_at": str(result.created_at)
                })
                reply_to_id = result.id  # Link next tweet to this one
            except Exception as e:
                logger.error(f"X API thread post failed on part {len(results)+1}: {str(e)}", 
                            phase="POSTER", error=str(e))
                return None
        
        return {
            "thread_id": results[0]["tweet_id"],
            "parts": results,
            "thread_length": len(results)
        }


# PRIORITY 4: Global rate limit tracker
rate_limit_tracker = RateLimitTracker()


async def pre_post_validation(tweet_obj: Dict) -> bool:
    """Pre-flight validation before posting."""
    
    # PRIORITY 4: Check rate limits first
    if not rate_limit_tracker.can_post():
        logger.error("Pre-post validation FAILED: Rate limit buffer reached",
                   phase="POSTER", event="RATE_LIMIT_EXCEEDED")
        return False
    
    # Run validator
    validation = validator.validate_tweet(tweet_obj)
    if not validation["valid"]:
        logger.error("Pre-post validation FAILED",
                   phase="POSTER",
                   data={"failures": validation.get("failures", [])})
        return False
    
    # Check for duplicates
    if await is_duplicate(tweet_obj):
        logger.error("Pre-post validation FAILED: DUPLICATE detected",
                   phase="POSTER", event="DUPLICATE_ERROR")
        return False
    
    logger.info("Pre-post validation PASSED", phase="POSTER", event="VALIDATION_OK")
    return True


async def is_duplicate(tweet_obj: Dict, threshold: float = 0.75) -> bool:
    """Check if tweet is too similar to recent tweets via TF-IDF cosine similarity."""
    
    try:
        new_text = tweet_obj.get("text", "")
        if not new_text:
            return False
        
        # Get recent tweets from memory
        recent = memory.get_recent_tweets(days=7, limit=50)
        if not recent or len(recent) == 0:
            return False  # No data to compare against
        
        recent_texts = [t.get("text", "") for t in recent if t.get("text")]
        if not recent_texts:
            return False
        
        if not SKLEARN_AVAILABLE:
            # Fallback to simple word overlap if sklearn not available
            return _simple_duplicate_check(new_text, recent_texts, threshold)
        
        # TF-IDF vectorizer
        vectorizer = TfidfVectorizer(analyzer='word', ngram_range=(1, 2))
        try:
            tfidf_matrix = vectorizer.fit_transform([new_text] + recent_texts)
        except:
            return False  # Edge case: empty tokens
        
        # Cosine similarity between new tweet and each recent tweet
        similarities = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:]).flatten()
        max_similarity = similarities.max() if len(similarities) > 0 else 0
        
        if max_similarity > threshold:
            logger.warn(f"Duplicate detected (similarity: {max_similarity:.2f})",
                      phase="POSTER",
                      data={"max_similarity": float(max_similarity), "threshold": threshold})
            return True
        
        return False
        
    except Exception as e:
        logger.warn(f"Duplicate check failed: {str(e)}", 
                  phase="POSTER", error=str(e))
        return False


def _simple_duplicate_check(new_text: str, recent_texts: list, threshold: float) -> bool:
    """Simple duplicate check without sklearn (fallback)."""
    new_words = set(new_text.lower().split())
    for recent in recent_texts:
        recent_words = set(recent.lower().split())
        if recent_words and new_words:
            overlap = len(new_words & recent_words) / len(new_words | recent_words)
            if overlap > threshold:
                return True
    return False


async def post_tweet_async(tweet_obj: Dict) -> Optional[Dict]:
    """Post tweet/thread to X after validation."""
    
    try:
        logger.info("Posting tweet to X", phase="POSTER", event="POSTER_START",
                   data={"thread_length": tweet_obj.get("thread_length", 1)})
        
        # Pre-post validation
        if not await pre_post_validation(tweet_obj):
            logger.error("Post ABORTED due to validation failure",
                       phase="POSTER", event="POST_ABORTED")
            return None
        
        # Initialize X API client
        client = XAPIAsyncClient()
        
        # Handle thread vs single
        thread_length = tweet_obj.get("thread_length", 1)
        if thread_length > 1:
            # Thread
            tweets = tweet_obj.get("text_parts", [tweet_obj.get("text", "")])
            result = await client.post_thread(tweets)
        else:
            # Single tweet
            result = await client.post_tweet(tweet_obj.get("text", ""))
        
        if not result:
            logger.error("Post FAILED: X API returned None",
                       phase="POSTER", event="POST_FAILED")
            return None
        
        # PRIORITY 4: Record post for rate limit tracking
        rate_limit_tracker.record_post()
        
        # Log to memory
        memory.add_tweet_to_log(tweet_obj, result, {})
        
        logger.info("Post SUCCESS",
                  phase="POSTER",
                  event="POST_SUCCESS",
                  data={
                      "tweet_id": result.get("tweet_id"),
                      "thread_length": result.get("thread_length", 1)
                  })
        
        # Schedule metric fetches
        try:
            tweet_id = result.get("tweet_id")
            memory.schedule_metric_fetch(tweet_id, delay_hours=2)
            memory.schedule_metric_fetch(tweet_id, delay_hours=24)
            memory.schedule_metric_fetch(tweet_id, delay_hours=72)
        except Exception as e:
            logger.warn(f"Failed to schedule metric fetches: {str(e)}", 
                      phase="POSTER", event="SCHEDULE_FAILED")
        
        return result
        
    except Exception as e:
        logger.error(f"Post FAILED with exception: {str(e)}",
                   phase="POSTER", event="POSTER_ERROR", error=str(e))
        return None


async def post_tweet(tweet_obj: Dict) -> Optional[Dict]:
    """Async wrapper that delegates to post_tweet_async."""
    return await post_tweet_async(tweet_obj)


def append_experiment(experiment: Dict) -> None:
    """Append experiment record to experiments.jsonl for learning loop."""
    try:
        # Ensure data directory exists
        os.makedirs("data", exist_ok=True)
        
        # Append to experiments.jsonl
        experiments_path = "data/experiments.jsonl"
        with open(experiments_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(experiment) + "\n")
        
        logger.info(
            "Experiment logged to experiments.jsonl",
            phase="POSTER",
            data={"tweet_id": experiment.get("tweet_id")}
        )
    except Exception as e:
        logger.error(
            f"Failed to append experiment: {str(e)}",
            phase="POSTER",
            error=str(e)
        )
