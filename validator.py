"""
validator.py — Quality Gate for Tweet Validation

Pre-post checklist: ensure tweets are good enough to post.
Validates length, format, banned words, structure, and similarity.
"""

import json
from typing import Dict, Any, List, Tuple
from datetime import datetime

import config
from logger import logger


class TweetValidator:
    """Validates tweets before posting."""

    def __init__(self):
        self.banned_words = config.BANNED_WORDS

    def validate_all(self, tweet_obj: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Run all validation checks on a tweet.
        
        Args:
            tweet_obj: Generated tweet object with keys: tweet, format_type, topic_bucket, tone, hook, reasoning
            
        Returns:
            (is_valid, list_of_error_messages)
        """
        errors = []
        
        # Required fields
        required_keys = ["tweet", "format_type", "topic_bucket", "tone", "hook", "reasoning"]
        missing = [k for k in required_keys if k not in tweet_obj]
        if missing:
            errors.append(f"Missing required keys: {missing}")
            return False, errors
        
        tweet = tweet_obj["tweet"]
        
        # Length check
        if len(tweet) > config.MAX_TWEET_LENGTH:
            errors.append(f"Tweet too long ({len(tweet)} > {config.MAX_TWEET_LENGTH} chars)")
        
        if len(tweet.strip()) < 20:
            errors.append("Tweet too short (< 20 chars)")
        
        # Empty check
        if not tweet.strip():
            errors.append("Tweet is empty")
        
        # Format validation
        if tweet_obj["format_type"] not in config.VALID_FORMATS:
            errors.append(f"Invalid format: {tweet_obj['format_type']}")
        
        # Topic validation
        if tweet_obj["topic_bucket"] not in config.VALID_TOPICS:
            errors.append(f"Invalid topic: {tweet_obj['topic_bucket']}")
        
        # Tone validation
        if tweet_obj["tone"] not in config.VALID_TONES:
            errors.append(f"Invalid tone: {tweet_obj['tone']}")
        
        # Banned words check
        tweet_lower = tweet.lower()
        found_banned = [w for w in self.banned_words if w.lower() in tweet_lower]
        if found_banned:
            logger.warn(
                "Tweet contains banned words",
                phase="VALIDATOR",
                data={"banned_words_found": found_banned}
            )
        
        # Hook validation
        if len(tweet_obj["hook"]) > 100:
            logger.warn(
                "Hook is long",
                phase="VALIDATOR",
                data={"hook_length": len(tweet_obj["hook"])}
            )
        
        # Structure check (should have blank line if multi-line)
        if "\n\n" not in tweet and "\n" in tweet:
            logger.warn(
                "Multi-line tweet missing blank line for rhythm",
                phase="VALIDATOR"
            )
        
        # Return result
        if errors:
            return False, errors
        else:
            return True, []

    def is_duplicate(self, tweet_text: str, memory) -> bool:
        """
        Check if tweet is too similar to recent posts.
        
        Uses simple string similarity (TF-IDF).
        
        Args:
            tweet_text: The new tweet text
            memory: MemoryManager instance
            
        Returns:
            True if duplicate detected
        """
        from datetime import datetime, timedelta
        
        recent_tweets = memory.load_recent_tweets(days=7)
        
        if not recent_tweets:
            return False
        
        for recent in recent_tweets:
            similarity = self._compute_similarity(tweet_text, recent.content)
            if similarity > config.DUPLICATE_SIMILARITY_THRESHOLD:
                logger.warn(
                    "Potential duplicate detected",
                    phase="VALIDATOR",
                    data={
                        "similarity": similarity,
                        "recent_tweet_id": recent.tweet_id
                    }
                )
                return True
        
        return False

    def _compute_similarity(self, text1: str, text2: str) -> float:
        """
        Simple cosine similarity between two texts.
        Uses word overlap (Jaccard-style) for simplicity.
        """
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        return intersection / union if union > 0 else 0.0


# Global validator instance
validator = TweetValidator()
