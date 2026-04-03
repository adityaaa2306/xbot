"""
validator.py — Quality Gate for Tweet Validation (Priority 2: Content Quality)

Pre-post checklist: ensure tweets are good enough to post.
Validates length, format, toxicity, semantic similarity, hook strength, and diversity.

Priority 2 Enhancements:
- Toxicity filter: Blocks tweets with offensive language
- Semantic similarity: Improved duplicate detection
- Hook validation: Ensures opening lines are compelling
- Format diversity: Prevents posting same format too often
"""

import json
import re
from typing import Dict, Any, List, Tuple
from datetime import datetime, timedelta
from collections import Counter

import config
from logger import logger
from memory import memory


BANNED_OPENING_PHRASES = [
    "the real problem isn't",
    "the real problem is not",
    "nobody tells you this",
    "the default path",
    "most people",
]


def _is_numbering_only(text: str) -> bool:
    return bool(re.fullmatch(r"\s*\d+\s*/\s*\d+\s*", str(text)))


def check_opening_phrase_freshness(tweet_text: str, recent_tweets: list) -> dict:
    """
    Fails if the tweet opens with a phrase used in the last 5 tweets.
    """
    text_lower = tweet_text.strip().lower()

    # Get opening phrases from last 5 tweets
    recent_openers = []
    for t in recent_tweets[-5:]:
        if hasattr(t, "content"):
            content = t.content
        elif isinstance(t, dict):
            content = t.get("content") or t.get("tweet", "")
        else:
            content = getattr(t, "tweet", "")
        if content:
            words = content.strip().lower().split()
            recent_openers.append(" ".join(words[:4]))

    # Check current tweet's opener
    current_opener = " ".join(text_lower.split()[:4])

    if current_opener and current_opener in recent_openers:
        return {
            "valid": False,
            "rule": "opening_phrase_freshness",
            "reason": f"Opening phrase '{current_opener}' was used in the last 5 tweets. Regenerate with a different opener.",
        }

    # Also hard-ban specific phrases regardless of recency
    for banned in BANNED_OPENING_PHRASES:
        count = sum(
            1
            for t in recent_tweets[-10:]
            if (
                (t.content if hasattr(t, "content") else t.get("tweet", ""))
                if isinstance(t, dict)
                else (t.content if hasattr(t, "content") else getattr(t, "tweet", ""))
            ).lower().startswith(banned)
        )
        if count >= 2 and text_lower.startswith(banned):
            return {
                "valid": False,
                "rule": "banned_opener_overuse",
                "reason": f"'{banned}' has been used {count} times recently. Banned for next 10 posts.",
            }

    return {"valid": True}


class TweetValidator:
    """Validates tweets before posting with production-grade quality gates."""

    def __init__(self):
        self.banned_words = config.BANNED_WORDS
        self.toxicity_words = self._load_toxicity_list()
        self.min_hook_length = config.MIN_HOOK_LENGTH
        self.max_hook_length = config.MAX_HOOK_LENGTH

    def _load_toxicity_list(self) -> set:
        """Load toxicity keywords (basic filter without external dependencies)."""
        # Basic list of known offensive terms - this is non-comprehensive
        # but catches obvious cases
        toxic_patterns = {
            # Slurs and extremely offensive terms
            "n-word", "nword", "fag", "faggot", "dyke", "tr*nny",
            # Sexual harassment
            "rape", "raped", "raping", "rapist",
            # Violent threats
            "kill yourself", "kys", "die", "death threat",
            # Extreme profanity
            "fuck you", "f*ck you", "piece of shit", "asshole",
            # Hateful ideologies
            "nazi", "hitler", "white supremacy", "white power",
        }
        return toxic_patterns

    def validate_all(self, tweet_obj: Dict[str, Any], recent_tweets: list = None) -> Tuple[bool, List[str]]:
        """
        Run all validation checks on a tweet.
        
        Args:
            tweet_obj: Generated tweet object with required keys
            
        Returns:
            (is_valid, list_of_error_messages_or_warnings)
        """
        errors = []
        warnings = []
        
        # Required fields
        required_keys = ["tweet", "format_type", "topic_bucket", "tone", "hook", "reasoning"]
        missing = [k for k in required_keys if k not in tweet_obj]
        if missing:
            errors.append(f"Missing required keys: {missing}")
            return False, errors
        
        tweet = tweet_obj["tweet"]
        thread_length = int(tweet_obj.get("thread_length", 1) or 1)
        text_parts = tweet_obj.get("text_parts")

        if recent_tweets is None:
            recent_tweets = memory.get_recent_tweets(days=30, limit=10)

        # ===== CRITICAL CHECKS (FATAL) =====

        opening_phrase_result = check_opening_phrase_freshness(tweet, recent_tweets)
        if not opening_phrase_result["valid"]:
            errors.append(opening_phrase_result["reason"])
        
        # 1. Length check
        if len(tweet) > config.MAX_TWEET_LENGTH:
            errors.append(f"Tweet too long ({len(tweet)} > {config.MAX_TWEET_LENGTH} chars)")
        
        if len(tweet.strip()) < 10:
            errors.append("Tweet too short (< 10 chars)")
        
        # 2. Empty check
        if not tweet.strip():
            errors.append("Tweet is empty")
        
        # 3. Format validation
        if tweet_obj["format_type"] not in config.VALID_FORMATS:
            errors.append(f"Invalid format: {tweet_obj['format_type']}")
        
        # 4. Topic validation
        if tweet_obj["topic_bucket"] not in config.VALID_TOPICS:
            errors.append(f"Invalid topic: {tweet_obj['topic_bucket']}")
        
        # 5. Tone validation
        if tweet_obj["tone"] not in config.VALID_TONES:
            errors.append(f"Invalid tone: {tweet_obj['tone']}")

        # 6. Thread structure validation
        if thread_length > 1:
            if not isinstance(text_parts, list) or not text_parts:
                errors.append("Thread is missing text_parts list")
            else:
                if len(text_parts) != thread_length:
                    errors.append(f"Thread has {len(text_parts)} parts but expected {thread_length}")
                for idx, part in enumerate(text_parts, start=1):
                    part_text = str(part).strip()
                    if not part_text:
                        errors.append(f"Thread part {idx} is empty")
                    elif _is_numbering_only(part_text):
                        errors.append(f"Thread part {idx} is only a numbering marker")

        # ===== PRIORITY 2: TOXICITY CHECK (FATAL) =====
        toxicity_score = self._check_toxicity(tweet)
        if toxicity_score > config.TOXICITY_THRESHOLD:
            errors.append(f"Tweet contains toxic language (score: {toxicity_score:.2f} > {config.TOXICITY_THRESHOLD})")
        
        # ===== PRIORITY 2: HOOK VALIDATION (WARNING/FATAL) =====
        hook_error = self._validate_hook(tweet_obj.get("hook", ""))
        if hook_error:
            errors.append(hook_error)
        
        # ===== WARNINGS (NON-FATAL) =====
        
        # Banned words check
        tweet_lower = tweet.lower()
        found_banned = [w for w in self.banned_words if w.lower() in tweet_lower]
        if found_banned:
            warnings.append(f"Contains banned words: {found_banned}")
        
        # Structure check (should have blank line if multi-line)
        if "\n\n" not in tweet and "\n" in tweet:
            warnings.append("Multi-line tweet missing blank line for rhythm")
        
        # Excessive punctuation
        if re.search(r'[!?]{2,}', tweet):
            warnings.append("Tweet has excessive punctuation")
        
        # ALL CAPS warning
        words_in_tweet = tweet.split()
        caps_words = [w for w in words_in_tweet if w.isupper() and len(w) > 2]
        if len(caps_words) > len(words_in_tweet) * 0.3:
            warnings.append(f"Tweet is {len(caps_words)/len(words_in_tweet)*100:.0f}% ALL CAPS")
        
        # Return result
        if errors:
            return False, errors
        else:
            return True, warnings

    def validate_tweet(self, tweet_obj: Dict[str, Any], recent_tweets: list = None) -> Dict[str, Any]:
        """Structured validation result used by the pipeline."""
        valid, messages = self.validate_all(tweet_obj, recent_tweets=recent_tweets)
        if valid:
            return {"valid": True, "warnings": messages}
        return {"valid": False, "failures": messages}

    def _check_toxicity(self, text: str) -> float:
        """
        Score toxicity (0.0 = clean, 1.0 = extremely toxic).
        Uses basic pattern matching without external APIs.
        
        Returns: toxicity score 0-1
        """
        text_lower = text.lower()
        text_lower = re.sub(r'[^a-z0-9\s]', '', text_lower)  # Normalize
        
        toxic_matches = 0
        total_dangerous_patterns = 0
        
        # Check each toxic pattern
        for pattern in self.toxicity_words:
            pattern_norm = re.sub(r'[^a-z0-9\s]', '', pattern.lower())
            # Look for exact match or partial obfuscation (like n-word)
            if pattern_norm in text_lower or pattern in text.lower():
                toxic_matches += 1
            total_dangerous_patterns += 1
        
        # Score: proportion of toxic patterns found
        score = min(1.0, toxic_matches / max(total_dangerous_patterns, 1) * 2)
        
        if toxic_matches > 0:
            logger.warn(
                "Toxicity check flagged",
                phase="VALIDATOR",
                data={"score": score, "toxic_patterns_found": toxic_matches}
            )
        
        return score

    def _validate_hook(self, hook: str) -> str:
        """
        Validate hook (opening line) quality.
        Returns error message if invalid, None if valid.
        """
        if not hook or len(hook.strip()) == 0:
            return "Hook is empty"
        
        if len(hook) < self.min_hook_length:
            return f"Hook too short ({len(hook)} < {self.min_hook_length} chars)"
        
        if len(hook) > self.max_hook_length:
            return f"Hook too long ({len(hook)} > {self.max_hook_length} chars)"
        
        # Check if hook is just emoji or numbers
        alphanumeric = sum(1 for c in hook if c.isalnum())
        if alphanumeric < len(hook) * 0.3:
            return f"Hook lacks substance (only {alphanumeric/len(hook)*100:.0f}% alphanumeric)"
        
        return None

    def is_duplicate(self, tweet_text: str, memory) -> bool:
        """
        Check if tweet is too similar to recent posts.
        Uses semantic similarity (improved from Jaccard).
        """
        recent_tweets = memory.load_recent_tweets(days=7)
        
        if not recent_tweets:
            return False
        
        for recent in recent_tweets:
            similarity = self._compute_semantic_similarity(tweet_text, recent.content)
            if similarity > config.DUPLICATE_SIMILARITY_THRESHOLD:
                logger.warn(
                    "Potential duplicate detected",
                    phase="VALIDATOR",
                    data={
                        "similarity": f"{similarity:.2f}",
                        "recent_tweet_id": recent.tweet_id
                    }
                )
                return True
        
        return False

    def _compute_semantic_similarity(self, text1: str, text2: str) -> float:
        """
        Improved semantic similarity using multiple methods:
        1. Jaccard similarity (word overlap)
        2. Word frequency comparison (TF-IDF lite)
        3. Bigram overlap (sequence similarity)
        
        Returns: 0.0 (completely different) to 1.0 (identical)
        """
        # Method 1: Jaccard similarity (40% weight)
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        jaccard = len(words1 & words2) / len(words1 | words2) if words1 | words2 else 0
        
        # Method 2: Word frequency correlation (30% weight)
        freq1 = Counter(text1.lower().split())
        freq2 = Counter(text2.lower().split())
        common_words = set(freq1.keys()) & set(freq2.keys())
        
        if common_words:
            freq_correlation = sum(min(freq1[w], freq2[w]) for w in common_words) / max(len(text1.split()), len(text2.split()))
        else:
            freq_correlation = 0
        
        # Method 3: Bigram overlap (30% weight)
        bigrams1 = set(zip(text1.lower().split()[:-1], text1.lower().split()[1:]))
        bigrams2 = set(zip(text2.lower().split()[:-1], text2.lower().split()[1:]))
        
        if bigrams1 or bigrams2:
            bigram_overlap = len(bigrams1 & bigrams2) / len(bigrams1 | bigrams2) if (bigrams1 | bigrams2) else 0
        else:
            bigram_overlap = 0
        
        # Weighted combination
        final_similarity = (jaccard * 0.4) + (freq_correlation * 0.3) + (bigram_overlap * 0.3)
        
        return final_similarity

    def check_format_diversity(self, new_format: str, memory, days: int = 7, max_posts_same_format: int = 2) -> Tuple[bool, str]:
        """
        Check if posting same format too often (prevents convergence).
        
        Returns: (is_diverse_enough, warning_message)
        """
        recent_tweets = memory.load_recent_tweets(days=days)
        
        same_format_count = sum(1 for t in recent_tweets if t.format_type == new_format)
        
        if same_format_count >= max_posts_same_format:
            msg = f"Format '{new_format}' posted {same_format_count}x in {days}d (limit: {max_posts_same_format})"
            return False, msg
        
        return True, f"Format diversity OK ({same_format_count} of {max_posts_same_format} limit)"


# Global validator instance
validator = TweetValidator()
