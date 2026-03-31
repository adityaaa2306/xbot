"""
experimenter.py — Controlled Experimentation & Diversity Enforcement

Manages exploration vs exploitation tradeoff.
Ensures the system never converges to a single format.
Enforces novelty and diversity quotas.
"""

import random
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

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
        # Check current day of week
        today_weekday = datetime.utcnow().weekday()  # 0=Monday, 6=Sunday
        
        # Get scheduled experiment type for today
        scheduled_experiment = config.WEEKLY_EXPERIMENT_SCHEDULE.get(today_weekday, "exploitation")
        
        # Check if we violate diversity quota
        recent_tweets = memory.load_recent_tweets(days=14)
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
            return self._plan_exploitation()
        else:
            return self._plan_exploration(scheduled_experiment)

    def _plan_exploitation(self) -> Dict[str, Any]:
        """
        Pick the best-known strategy.
        
        Returns top-performing (format, topic, tone) combination.
        """
        tweets = memory.load_mature_tweets()
        
        if not tweets:
            # Fallback: random
            return self._plan_exploration("random")
        
        # Find highest-scoring (format, topic, tone) combo
        combos = {}
        for tweet in tweets:
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
                    "avg_score": round(best_avg, 2)
                }
            )
            
            return {
                "format_type": best_combo[0],
                "topic_bucket": best_combo[1],
                "tone": best_combo[2],
                "is_experiment": False,
                "experiment_type": None
            }
        else:
            # Fallback
            return self._plan_exploration("random")

    def _plan_exploration(self, experiment_type: str) -> Dict[str, Any]:
        """
        Pick an exploratory format/topic/tone.
        
        experiment_type: "new_format" | "new_topic" | "new_tone" | "structure_variant" | "random"
        """
        recent_tweets = memory.load_recent_tweets(days=14)
        
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
            topic_bucket = random.choice(config.VALID_TOPICS)
            tone = random.choice(config.VALID_TONES)
            
        elif experiment_type == "new_topic":
            format_type = random.choice(config.VALID_FORMATS)
            unused_topics = set(config.VALID_TOPICS) - recent_topics
            if unused_topics:
                topic_bucket = random.choice(list(unused_topics))
            else:
                topic_bucket = random.choice(config.VALID_TOPICS)
            tone = random.choice(config.VALID_TONES)
            
        elif experiment_type == "new_tone":
            format_type = random.choice(config.VALID_FORMATS)
            topic_bucket = random.choice(config.VALID_TOPICS)
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
                topic_bucket = base.topic_bucket
                tone = base.tone
            else:
                format_type = random.choice(config.VALID_FORMATS)
                topic_bucket = random.choice(config.VALID_TOPICS)
                tone = random.choice(config.VALID_TONES)
        
        else:  # random or unknown
            format_type = random.choice(config.VALID_FORMATS)
            topic_bucket = random.choice(config.VALID_TOPICS)
            tone = random.choice(config.VALID_TONES)
            experiment_type = "random"
        
        logger.info(
            f"Planning exploration ({experiment_type})",
            phase="EXPERIMENTER",
            data={
                "format": format_type,
                "topic": topic_bucket,
                "tone": tone
            }
        )
        
        return {
            "format_type": format_type,
            "topic_bucket": topic_bucket,
            "tone": tone,
            "is_experiment": True,
            "experiment_type": experiment_type
        }

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


# Global experiment manager instance
experimenter = ExperimentManager()
