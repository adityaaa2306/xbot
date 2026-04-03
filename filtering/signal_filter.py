"""Hard filters, deduplication, and scoring for scraped signals."""

import math
import re
from datetime import datetime, timezone
from typing import Iterable, List, Sequence

import config
from ingestion.models import SignalTweet


class SignalFilter:
    """Transform noisy scraped tweets into a ranked signal set."""

    PROMOTIONAL_PATTERNS = (
        "link in bio",
        "subscribe",
        "dm me",
        "join my",
        "course",
        "buy now",
        "limited offer",
    )

    def filter_and_rank(self, signals: Sequence[SignalTweet]) -> List[SignalTweet]:
        candidates: List[SignalTweet] = []

        for signal in signals:
            kept, reason = self._passes_hard_filters(signal)
            signal.kept = kept
            signal.rejection_reason = None if kept else reason
            if kept:
                candidates.append(signal)

        deduped = self._dedupe(candidates)
        ranked = []
        for signal in deduped:
            signal.recency_decay = self._recency_decay(signal.timestamp)
            signal.rank_score = round(self._raw_score(signal) / signal.recency_decay, 2)
            ranked.append(signal)

        ranked.sort(key=lambda signal: signal.rank_score or 0.0, reverse=True)
        return ranked[: config.SIGNAL_TOP_TWEETS_PER_RUN]

    def _passes_hard_filters(self, signal: SignalTweet) -> tuple[bool, str]:
        text = signal.text.strip()
        lower = text.lower()

        if len(text) < config.SIGNAL_MIN_TEXT_LENGTH:
            return False, "too_short"

        if "http://" in lower or "https://" in lower:
            return False, "contains_link"

        if any(pattern in lower for pattern in self.PROMOTIONAL_PATTERNS):
            return False, "promotional"

        # For public embed scraping, engagement metrics may be 0
        # So we use a relaxed check: if all metrics are 0, we allow it (proxy scoring will rank it)
        # But if metrics exist, they must meet threshold
        has_any_metric = signal.likes > 0 or signal.replies > 0 or signal.retweets > 0
        if has_any_metric and not (
            signal.likes >= config.SIGNAL_MIN_LIKES
            or signal.replies >= config.SIGNAL_MIN_REPLIES
        ):
            return False, "below_engagement_threshold"

        return True, ""

    def _dedupe(self, signals: Iterable[SignalTweet]) -> List[SignalTweet]:
        kept: List[SignalTweet] = []
        for signal in signals:
            if any(self._similarity(signal.text, existing.text) >= config.SIGNAL_DEDUPLICATION_THRESHOLD for existing in kept):
                signal.kept = False
                signal.rejection_reason = "duplicate_idea"
                continue
            kept.append(signal)
        return kept

    def _similarity(self, first: str, second: str) -> float:
        tokens_a = self._tokenize(first)
        tokens_b = self._tokenize(second)
        if not tokens_a or not tokens_b:
            return 0.0
        intersection = len(tokens_a & tokens_b)
        union = len(tokens_a | tokens_b)
        return intersection / union if union else 0.0

    def _tokenize(self, value: str) -> set[str]:
        cleaned = re.sub(r"[^a-z0-9\s]", " ", value.lower())
        return {token for token in cleaned.split() if token}

    def _raw_score(self, signal: SignalTweet) -> float:
        """Score tweets using real engagement metrics when available, proxy scoring as fallback."""
        # If we have real engagement metrics, use them
        has_any_metric = signal.likes > 0 or signal.retweets > 0 or signal.replies > 0
        if has_any_metric:
            return float(signal.likes + (2 * signal.retweets) + (3 * signal.replies))
        
        # Fallback: proxy scoring based on text quality and creator tier
        return self._proxy_score(signal)

    def _proxy_score(self, signal: SignalTweet) -> float:
        """Proxy scoring when engagement metrics are unavailable (e.g., public embed scraping)."""
        base_tier_weight = getattr(config, "SIGNAL_PROXY_SCORE_TIER_WEIGHT", 150)
        tier = (signal.creator_tier or "").lower()
        if tier == "core":
            tier_score = float(base_tier_weight)
        elif tier == "rotating":
            tier_score = float(round(base_tier_weight * 0.8))
        else:
            tier_score = float(round(base_tier_weight * 0.65))

        # Boost from text quality heuristics
        text_score = self._text_quality_score(signal.text)

        # Combined proxy score
        return float(tier_score + text_score)
    
    def _text_quality_score(self, text: str) -> float:
        """Estimate quality from text characteristics."""
        score = 0.0
        
        # Length bonus (longer well-written tweets)
        cleaned = text.strip()
        word_count = len(cleaned.split())
        if 20 <= word_count <= 100:
            score += 50
        elif word_count > 100:
            score += 30
        else:
            score += 20  # short tweets still valid
        
        # Question marks (engagement driver)
        if "?" in text:
            score += 30
        
        # Bold/contrarian patterns
        contrarian_words = ["actually", "despite", "contrary", "wrong", "myth", "trap", "never", "always"]
        if any(word in text.lower() for word in contrarian_words):
            score += 25
        
        # Specific/concrete language
        numbers_in_text = bool(re.search(r"\d+", text))
        if numbers_in_text:
            score += 15
        
        # Avoid all caps (usually low quality)
        if text.isupper():
            score -= 20
        
        return score

    def _recency_decay(self, timestamp: str) -> float:
        posted_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        hours_old = max((now - posted_at).total_seconds() / 3600, 1)

        if hours_old <= 24:
            return 1.0
        if hours_old <= 72:
            return 1.5
        if hours_old <= 24 * 7:
            return 2.0
        return min(4.0, 2.0 + math.log(hours_old / 24, 2))
