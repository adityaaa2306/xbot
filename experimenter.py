"""
experimenter.py — Controlled Experimentation & Diversity Enforcement

Manages exploration vs exploitation tradeoff.
Ensures the system never converges to a single format.
Enforces novelty and diversity quotas.
"""

import random
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from zoneinfo import ZoneInfo

import config
from logger import logger
from memory import memory


class ExperimentManager:
    """Manages exploration/exploitation and experiment scheduling."""

    def __init__(self):
        pass

    def get_todays_plan(self) -> Dict[str, Any]:
        """
        Determine what to post today.
        
        Returns:
            {
                "format_type": str,
                "topic_bucket": str,
                "tone": str,
                "is_experiment": bool,
                "experiment_type": str  # "new_format" | "new_topic" | "new_tone" | "structure_variant"
            }
        """
        # Check current day of week in the bot's configured timezone.
        today_weekday = self._get_local_weekday()  # 0=Monday, 6=Sunday
        preferred_topic = config.TOPIC_WEEKDAY_ROTATION.get(today_weekday)
        prefer_thread = today_weekday == config.THREAD_PREFERRED_WEEKDAY
        
        # Get scheduled experiment type for today
        scheduled_experiment = config.WEEKLY_EXPERIMENT_SCHEDULE.get(today_weekday, "exploitation")
        
        # Check if we violate diversity quota
        recent_tweets = self._load_supported_recent_tweets(days=14)
        diversity_score = self._compute_diversity_score(recent_tweets)
        
        logger.debug(
            f"Diversity score: {diversity_score:.2f}",
            phase="EXPERIMENTER",
            data={"diversity_threshold": config.DIVERSITY_SCORE_THRESHOLD}
        )
        
        # If diversity is low, force exploration
        if diversity_score < config.DIVERSITY_SCORE_THRESHOLD:
            logger.warn(
                "Diversity below threshold, forcing exploration",
                phase="EXPERIMENTER",
                data={"diversity_score": diversity_score}
            )
            scheduled_experiment = "forced_exploration"
        
        # Decide based on schedule
        if scheduled_experiment == "exploitation":
            return self._plan_exploitation(preferred_topic=preferred_topic, prefer_thread=prefer_thread)
        else:
            return self._plan_exploration(
                scheduled_experiment,
                preferred_topic=preferred_topic,
                prefer_thread=prefer_thread,
            )

    def _plan_exploitation(self, preferred_topic: Optional[str] = None, prefer_thread: bool = False) -> Dict[str, Any]:
        """
        Pick the best-known strategy.
        
        Returns top-performing (format, topic, tone) combination.
        """
        tweets = [
            tweet for tweet in memory.load_mature_tweets()
            if self._is_supported_tweet(tweet)
        ]
        
        if not tweets:
            # Fallback: random
            return self._plan_exploration("random", preferred_topic=preferred_topic, prefer_thread=prefer_thread)

        candidate_tweets = tweets
        if preferred_topic:
            preferred = [tweet for tweet in tweets if tweet.topic_bucket == preferred_topic]
            if preferred:
                candidate_tweets = preferred
        
        # Find highest-scoring (format, topic, tone) combo
        combos = {}
        for tweet in candidate_tweets:
            key = (tweet.format_type, tweet.topic_bucket, tweet.tone)
            if key not in combos:
                combos[key] = []
            combos[key].append(tweet.engagement_score)
        
        best_combo = None
        best_avg = 0
        
        for combo, scores in combos.items():
            avg = sum(scores) / len(scores) if scores else 0
            if avg > best_avg:
                best_avg = avg
                best_combo = combo
        
        if best_combo:
            logger.info(
                "Planning exploitation",
                phase="EXPERIMENTER",
                data={
                    "format": best_combo[0],
                    "topic": best_combo[1],
                    "tone": best_combo[2],
                    "avg_score": round(best_avg, 2),
                    "preferred_topic": preferred_topic,
                }
            )
            
            planned_format = best_combo[0]
            planned_topic = best_combo[1]
            planned_tone = best_combo[2]

            if prefer_thread and planned_format not in config.THREAD_ONLY_FORMATS:
                return self._plan_exploration(
                    "thread_preferred",
                    preferred_topic=preferred_topic or planned_topic,
                    prefer_thread=True,
                )

            return self._build_plan(
                format_type=planned_format,
                topic_bucket=self._choose_topic_with_streak_guard(planned_topic),
                tone=planned_tone,
                is_experiment=False,
                experiment_type=None,
                prefer_thread=prefer_thread,
            )
        else:
            # Fallback
            return self._plan_exploration("random", preferred_topic=preferred_topic, prefer_thread=prefer_thread)

    def _plan_exploration(
        self,
        experiment_type: str,
        preferred_topic: Optional[str] = None,
        prefer_thread: bool = False,
    ) -> Dict[str, Any]:
        """
        Pick an exploratory format/topic/tone.
        
        experiment_type: "new_format" | "new_topic" | "new_tone" | "structure_variant" | "random"
        """
        recent_tweets = self._load_supported_recent_tweets(days=14)
        
        # Gather what's been used recently
        recent_formats = set(t.format_type for t in recent_tweets)
        recent_topics = set(t.topic_bucket for t in recent_tweets)
        recent_tones = set(t.tone for t in recent_tweets)
        
        format_type = None
        topic_bucket = None
        tone = None
        
        if experiment_type == "new_format":
            # Pick a format not used in last 14 days
            unused_formats = set(config.VALID_FORMATS) - recent_formats
            if unused_formats:
                format_type = random.choice(list(unused_formats))
            else:
                format_type = random.choice(config.VALID_FORMATS)
            topic_bucket = preferred_topic or random.choice(config.VALID_TOPICS)
            tone = random.choice(config.VALID_TONES)
            
        elif experiment_type == "new_topic":
            format_type = random.choice(config.VALID_FORMATS)
            unused_topics = set(config.VALID_TOPICS) - recent_topics
            if unused_topics:
                topic_bucket = random.choice(list(unused_topics))
            else:
                topic_bucket = preferred_topic or random.choice(config.VALID_TOPICS)
            tone = random.choice(config.VALID_TONES)
            
        elif experiment_type == "new_tone":
            format_type = random.choice(config.VALID_FORMATS)
            topic_bucket = preferred_topic or random.choice(config.VALID_TOPICS)
            unused_tones = set(config.VALID_TONES) - recent_tones
            if unused_tones:
                tone = random.choice(list(unused_tones))
            else:
                tone = random.choice(config.VALID_TONES)
            
        elif experiment_type == "structure_variant":
            # Same topic/tone, different format
            if recent_tweets:
                base = random.choice(recent_tweets)
                format_type = random.choice(config.VALID_FORMATS)
                topic_bucket = preferred_topic or base.topic_bucket
                tone = base.tone
            else:
                format_type = random.choice(config.VALID_FORMATS)
                topic_bucket = preferred_topic or random.choice(config.VALID_TOPICS)
                tone = random.choice(config.VALID_TONES)
        
        else:  # random or unknown
            format_type = random.choice(config.VALID_FORMATS)
            topic_bucket = preferred_topic or random.choice(config.VALID_TOPICS)
            tone = random.choice(config.VALID_TONES)
            experiment_type = "random"

        if prefer_thread:
            format_type = "thread_opener"

        if format_type in config.THREAD_ONLY_FORMATS and not prefer_thread:
            non_thread_formats = [
                value for value in config.VALID_FORMATS
                if value not in config.THREAD_ONLY_FORMATS
            ]
            format_type = random.choice(non_thread_formats)

        logger.info(
            f"Planning exploration ({experiment_type})",
            phase="EXPERIMENTER",
            data={
                "format": format_type,
                "topic": topic_bucket,
                "tone": tone
            }
        )
        
        return self._build_plan(
            format_type=format_type,
            topic_bucket=self._choose_topic_with_streak_guard(topic_bucket),
            tone=tone,
            is_experiment=True,
            experiment_type=experiment_type,
            prefer_thread=prefer_thread,
        )

    def _compute_diversity_score(self, recent_tweets) -> float:
        """
        Compute diversity score across recent tweets.
        
        0.0 = all same format/topic/tone
        1.0 = perfectly diverse
        """
        if not recent_tweets:
            return 0.5  # Neutral if no data
        
        formats = set(t.format_type for t in recent_tweets)
        topics = set(t.topic_bucket for t in recent_tweets)
        tones = set(t.tone for t in recent_tweets)
        
        # Normalize: max 5 formats, 6 topics, 4 tones
        format_score = len(formats) / len(config.VALID_FORMATS)
        topic_score = len(topics) / len(config.VALID_TOPICS)
        tone_score = len(tones) / len(config.VALID_TONES)
        
        avg_diversity = (format_score + topic_score + tone_score) / 3
        
        return round(min(avg_diversity, 1.0), 2)

    def _build_plan(
        self,
        format_type: str,
        topic_bucket: str,
        tone: str,
        is_experiment: bool,
        experiment_type: Optional[str],
        prefer_thread: bool,
    ) -> Dict[str, Any]:
        thread_length = 1
        if prefer_thread or format_type in config.THREAD_ONLY_FORMATS:
            thread_length = random.randint(config.THREAD_LENGTH_MIN, config.THREAD_LENGTH_MAX)

        return {
            "format_type": format_type,
            "topic_bucket": topic_bucket,
            "tone": tone,
            "thread_length": thread_length,
            "is_experiment": is_experiment,
            "experiment_type": experiment_type,
        }

    def _get_local_weekday(self) -> int:
        try:
            return datetime.now(ZoneInfo(config.BOT_TIMEZONE)).weekday()
        except Exception:
            return datetime.utcnow().weekday()

    def _load_supported_recent_tweets(self, days: int):
        recent_tweets = memory.get_recent_tweets(days=days)
        return [tweet for tweet in recent_tweets if self._is_supported_tweet(tweet)]

    def _is_supported_tweet(self, tweet) -> bool:
        return (
            tweet.format_type in config.VALID_FORMATS
            and tweet.topic_bucket in config.VALID_TOPICS
            and tweet.tone in config.VALID_TONES
        )

    def _choose_topic_with_streak_guard(self, preferred_topic: str) -> str:
        recent_tweets = self._load_supported_recent_tweets(days=3)
        recent_topics = [tweet.topic_bucket for tweet in recent_tweets[:2]]

        if (
            preferred_topic
            and len(recent_topics) >= 2
            and recent_topics[0] == preferred_topic
            and recent_topics[1] == preferred_topic
        ):
            alternatives = [
                topic for topic in config.VALID_TOPICS
                if topic != preferred_topic
            ]
            if alternatives:
                return random.choice(alternatives)

        return preferred_topic


# Global experiment manager instance
experimenter = ExperimentManager()
