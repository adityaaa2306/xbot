"""
poster.py — Async X (Twitter) API Integration

Posts tweets and threads to X via official API v2.
Features:
- Async wrapper around tweepy (runs in executor)
- Pre-post validation (11 checks)
- Duplicate detection via TF-IDF cosine similarity
- Thread handling (replies linked correctly)
- Memory integration for logging
"""

import asyncio
import json
import os
from typing import Optional, Dict
from concurrent.futures import ThreadPoolExecutor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

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


class XAPIAsyncClient:
    """Async wrapper for tweepy X API client."""
    
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
                        event="X_API_ERROR", error=str(e))
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
                            event="X_API_ERROR", error=str(e))
                return None
        
        return {
            "thread_id": results[0]["tweet_id"],
            "parts": results,
            "thread_length": len(results)
        }


async def pre_post_validation(tweet_obj: Dict) -> bool:
    """Pre-flight validation before posting."""
    
    # Run validator
    validation = validator.validate_tweet(tweet_obj)
    if not validation["valid"]:
        logger.error("Pre-post validation FAILED",
                   event="VALIDATION_ERROR",
                   data={"failures": validation.get("failures", [])})
        return False
    
    # Check for duplicates
    if await is_duplicate(tweet_obj):
        logger.error("Pre-post validation FAILED: DUPLICATE detected",
                   event="DUPLICATE_ERROR")
        return False
    
    logger.info("Pre-post validation PASSED", event="VALIDATION_OK")
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
                      event="DUPLICATE_WARNING",
                      data={"max_similarity": float(max_similarity), "threshold": threshold})
            return True
        
        return False
        
    except Exception as e:
        logger.warn(f"Duplicate check failed: {str(e)}", 
                  event="DUPLICATE_CHECK_FAILED", error=str(e))
        return False


async def post_tweet_async(tweet_obj: Dict) -> Optional[Dict]:
    """Post tweet/thread to X after validation."""
    
    try:
        logger.info("Posting tweet to X", event="POSTER_START", 
                   data={"thread_length": tweet_obj.get("thread_length", 1)})
        
        # Pre-post validation
        if not await pre_post_validation(tweet_obj):
            logger.error("Post ABORTED due to validation failure",
                       event="POST_ABORTED")
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
                       event="POST_FAILED")
            return None
        
        # Log to memory
        memory.add_tweet_to_log(tweet_obj, result, {})
        
        logger.info("Post SUCCESS",
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
                      event="SCHEDULE_FAILED")
        
        return result
        
    except Exception as e:
        logger.error(f"Post FAILED with exception: {str(e)}",
                   event="POSTER_ERROR", error=str(e))
        return None


def post_tweet(tweet_obj: Dict) -> Optional[Dict]:
    """Synchronous wrapper for async posting (compatibility)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(post_tweet_async(tweet_obj))
    finally:
        loop.close()
