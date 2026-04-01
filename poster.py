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
from typing import Optional, Dict, List
from datetime import datetime

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

import httpx
import config
from getxapi import GetXAPIError, api_headers, get_auth_token_async
from logger import logger
from memory import memory
from validator import validator


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
    """Async wrapper for GetXAPI create tweet endpoint."""
    
    def __init__(self):
        self.base_url = config.GETXAPI_BASE_URL.rstrip("/")

    async def _create_tweet(self, text: str, reply_to_tweet_id: Optional[str] = None) -> Dict:
        auth_token = await get_auth_token_async()
        payload: Dict[str, str] = {
            "auth_token": auth_token,
            "text": text,
        }
        if reply_to_tweet_id:
            payload["reply_to_tweet_id"] = str(reply_to_tweet_id)

        async with httpx.AsyncClient(timeout=config.POSTER_TIMEOUT_SECS) as client:
            response = await client.post(
                f"{self.base_url}/twitter/tweet/create",
                headers=api_headers(),
                json=payload,
            )

        if response.status_code >= 400:
            raise GetXAPIError(response.text.strip() or f"HTTP {response.status_code}")

        result = response.json()
        data = result.get("data", {}) if isinstance(result, dict) else {}
        tweet_id = data.get("id")
        if not tweet_id:
            raise GetXAPIError("GetXAPI did not return a tweet ID.")

        return {
            "tweet_id": str(tweet_id),
            "text": data.get("text", text),
            "posted_at": datetime.utcnow().isoformat() + "Z",
        }
    
    async def post_tweet(self, text: str) -> Optional[Dict]:
        """Post a single tweet asynchronously."""
        try:
            result = await self._create_tweet(text=text)
            return {
                "tweet_id": result["tweet_id"],
                "text": result["text"],
                "posted_at": result["posted_at"],
                "thread_length": 1,
            }
        except Exception as e:
            error_text = str(e)
            data = {}
            lowered = error_text.lower()
            if "402" in lowered or "credits" in lowered or "payment required" in lowered:
                data["remediation"] = "Add GetXAPI credits or upgrade the GetXAPI account plan."
            elif "401" in lowered or "invalid auth_token" in lowered:
                data["remediation"] = "Refresh GETXAPI_AUTH_TOKEN and update the repository secret."
            logger.error(f"GetXAPI tweet post failed: {error_text}", phase="POSTER", data=data, error=error_text)
            return None
    
    async def post_thread(self, tweets: List[str]) -> Optional[Dict]:
        """Post a thread (replies linked)."""
        results = []
        reply_to_id = None
        
        for text in tweets:
            try:
                result = await self._create_tweet(text=text, reply_to_tweet_id=reply_to_id)
                results.append({
                    "tweet_id": result["tweet_id"],
                    "text": result["text"],
                    "posted_at": result["posted_at"],
                })
                reply_to_id = result["tweet_id"]
            except Exception as e:
                error_text = str(e)
                data = {}
                lowered = error_text.lower()
                if "402" in lowered or "credits" in lowered or "payment required" in lowered:
                    data["remediation"] = "Add GetXAPI credits or upgrade the GetXAPI account plan."
                elif "401" in lowered or "invalid auth_token" in lowered:
                    data["remediation"] = "Refresh GETXAPI_AUTH_TOKEN and update the repository secret."
                logger.error(
                    f"GetXAPI thread post failed on part {len(results)+1}: {error_text}",
                    phase="POSTER",
                    data=data,
                    error=error_text,
                )
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
        logger.error("RATE_LIMIT_EXCEEDED", phase="POSTER")
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
        logger.error("DUPLICATE_ERROR", phase="POSTER")
        return False
    
    logger.info("VALIDATION_OK", phase="POSTER")
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
        
        recent_texts = [t.content for t in recent if t.content]
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
        logger.info("POSTER_START", phase="POSTER", data={"thread_length": tweet_obj.get("thread_length", 1)})
        
        # Pre-post validation
        if not await pre_post_validation(tweet_obj):
            logger.error("POST_ABORTED", phase="POSTER")
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
            logger.error("POST_FAILED", phase="POSTER")
            return None
        
        # PRIORITY 4: Record post for rate limit tracking
        rate_limit_tracker.record_post()
        
        logger.info(
            "POST_SUCCESS",
            phase="POSTER",
            data={
                "tweet_id": result.get("tweet_id"),
                "thread_length": result.get("thread_length", 1),
            },
        )
        
        # Schedule metric fetches
        try:
            tweet_id = result.get("tweet_id")
            memory.schedule_metric_fetch(tweet_id, delay_hours=2)
            memory.schedule_metric_fetch(tweet_id, delay_hours=24)
            memory.schedule_metric_fetch(tweet_id, delay_hours=72)
        except Exception as e:
            logger.warn("SCHEDULE_FAILED", phase="POSTER", data={"error": str(e)})
        
        return result
        
    except Exception as e:
        logger.error("POSTER_ERROR", phase="POSTER", data={"error": str(e)})
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
