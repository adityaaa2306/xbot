"""
experimenter.py — Controlled Experimentation & Diversity Enforcement

Manages exploration vs exploitation tradeoff.
Ensures the system never converges to a single format.
Enforces novelty and diversity quotas.
"""

import random
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, Optional
from zoneinfo import ZoneInfo

import config
from content_policy import load_content_policy
from logger import logger
from memory import memory


def get_archetype_with_cooldown(
    candidate_archetype: str,
    recent_tweets: list,
    cooldown_days: int = 3
) -> str:
    """
    If the candidate archetype was used in the last cooldown_days days,
    pick the next archetype in rotation instead.
    """
    ARCHETYPE_ROTATION = [
        "brutal_truth",
        "most_people_vs_smart_people",
        "if_you_understand_this",
        "kill_a_belief",
        "equation",
        "stacked_insight",
        "identity_shift",
        "contrarian_insight",
        "reframe",
        "thread_opener",
    ]

    cutoff = datetime.now(timezone.utc) - timedelta(days=cooldown_days)

    # Find archetypes used recently
    recently_used = set()
    for tweet in recent_tweets:
        posted_at = getattr(tweet, "posted_at", None) or (tweet.get("posted_at", "") if isinstance(tweet, dict) else "")
        if posted_at:
            try:
                tweet_time = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
                if tweet_time.tzinfo is None:
                    tweet_time = tweet_time.replace(tzinfo=timezone.utc)
                else:
                    tweet_time = tweet_time.astimezone(timezone.utc)
                if tweet_time > cutoff:
                    recently_used.add(
                        tweet.format_type if hasattr(tweet, "format_type")
                        else tweet.get("format_type", "")
                    )
            except Exception:
                pass

    # If candidate is on cooldown, find next available archetype
    if candidate_archetype in recently_used:
        for archetype in ARCHETYPE_ROTATION:
            if archetype not in recently_used:
                return archetype

    return candidate_archetype


class ExperimentManager:
    """Manages exploration/exploitation and experiment scheduling."""

    def __init__(self):
        self.content_policy = load_content_policy()

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
        self.content_policy = load_content_policy()
        cadence_policy = self.content_policy.get("cadence", {})
        local_now = self._get_local_now()
        slot = self._get_current_slot(local_now, cadence_policy)
        if not slot:
            slot = self._build_unscheduled_slot(local_now, cadence_policy)

        cadence_decision = self._evaluate_cadence(local_now, cadence_policy, slot)
        if cadence_decision.get("skip_post"):
            return cadence_decision

        desired_post_type = cadence_decision.get("post_type", "standalone")

        # Check current day of week in the bot's configured timezone.
        today_weekday = local_now.weekday()  # 0=Monday, 6=Sunday
        preferred_topic = config.TOPIC_WEEKDAY_ROTATION.get(today_weekday)
        
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
            return self._plan_exploitation(preferred_topic=preferred_topic, desired_post_type=desired_post_type)
        else:
            return self._plan_exploration(
                scheduled_experiment,
                preferred_topic=preferred_topic,
                desired_post_type=desired_post_type,
            )

    def _plan_exploitation(self, preferred_topic: Optional[str] = None, desired_post_type: str = "standalone") -> Dict[str, Any]:
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
            return self._plan_exploration("random", preferred_topic=preferred_topic, desired_post_type=desired_post_type)

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

            if desired_post_type == "thread" and planned_format not in config.THREAD_ONLY_FORMATS:
                return self._plan_exploration(
                    "thread_preferred",
                    preferred_topic=preferred_topic or planned_topic,
                    desired_post_type="thread",
                )

            return self._build_plan(
                format_type=planned_format,
                topic_bucket=self._choose_topic_with_streak_guard(planned_topic),
                tone=planned_tone,
                is_experiment=False,
                experiment_type=None,
                desired_post_type=desired_post_type,
            )
        else:
            # Fallback
            return self._plan_exploration("random", preferred_topic=preferred_topic, desired_post_type=desired_post_type)

    def _plan_exploration(
        self,
        experiment_type: str,
        preferred_topic: Optional[str] = None,
        desired_post_type: str = "standalone",
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

        if desired_post_type == "thread":
            format_type = "thread_opener"

        if format_type in config.THREAD_ONLY_FORMATS and desired_post_type != "thread":
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
            desired_post_type=desired_post_type,
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
        desired_post_type: str,
    ) -> Dict[str, Any]:
        recent_tweets = self._load_supported_recent_tweets(days=3)
        cooled_format = format_type
        if desired_post_type != "thread":
            cooled_format = get_archetype_with_cooldown(format_type, recent_tweets)
        if cooled_format != format_type and desired_post_type != "thread":
            logger.info(
                "Archetype cooldown applied",
                phase="EXPERIMENTER",
                data={"requested": format_type, "selected": cooled_format},
            )

        if desired_post_type == "thread":
            cooled_format = "thread_opener"
        elif cooled_format in config.THREAD_ONLY_FORMATS:
            non_thread_formats = [
                value for value in config.VALID_FORMATS
                if value not in config.THREAD_ONLY_FORMATS
            ]
            cooled_format = random.choice(non_thread_formats)

        thread_length = 1
        if cooled_format in config.THREAD_ONLY_FORMATS:
            thread_length = random.randint(config.THREAD_LENGTH_MIN, config.THREAD_LENGTH_MAX)

        return {
            "format_type": cooled_format,
            "topic_bucket": topic_bucket,
            "tone": tone,
            "thread_length": thread_length,
            "is_experiment": is_experiment,
            "experiment_type": experiment_type,
            "scheduled_post_type": desired_post_type,
        }

    def _get_local_now(self) -> datetime:
        try:
            return datetime.now(ZoneInfo(config.BOT_TIMEZONE))
        except Exception:
            return datetime.utcnow().replace(tzinfo=timezone.utc)

    def _get_current_slot(self, local_now: datetime, cadence_policy: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        slots = cadence_policy.get("slots", [])
        window_minutes = int(cadence_policy.get("schedule_window_minutes", 120))
        best_slot = None
        best_delta = None

        for index, slot in enumerate(slots):
            slot_weekday = slot.get("weekday")
            if slot_weekday is not None and int(slot_weekday) != local_now.weekday():
                continue
            try:
                slot_hour, slot_minute = [int(part) for part in str(slot.get("time", "00:00")).split(":", 1)]
            except Exception:
                continue

            slot_dt = local_now.replace(hour=slot_hour, minute=slot_minute, second=0, microsecond=0)
            delta_minutes = abs((local_now - slot_dt).total_seconds()) / 60
            if delta_minutes <= window_minutes and (best_delta is None or delta_minutes < best_delta):
                best_slot = {
                    **slot,
                    "slot_index": index,
                }
                best_delta = delta_minutes

        return best_slot

    def _build_unscheduled_slot(self, local_now: datetime, cadence_policy: Dict[str, Any]) -> Dict[str, Any]:
        slots = cadence_policy.get("slots", [])
        local_today = self._load_supported_recent_tweets(days=2)
        today_posts = [tweet for tweet in local_today if self._tweet_local_date(tweet.posted_at) == local_now.date()]
        fallback_index = min(len(today_posts), max(len(slots) - 1, 0))
        label = slots[fallback_index].get("label", f"Slot {fallback_index + 1}") if slots else "Manual slot"
        return {"slot_index": fallback_index, "label": label, "time": local_now.strftime("%H:%M"), "manual": True}

    def _evaluate_cadence(
        self,
        local_now: datetime,
        cadence_policy: Dict[str, Any],
        slot: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        recent_supported = self._load_supported_recent_tweets(days=2)
        local_today = [tweet for tweet in recent_supported if self._tweet_local_date(tweet.posted_at) == local_now.date()]

        daily_cap = min(config.MAX_POSTS_PER_DAY, int(cadence_policy.get("max_posts_per_day", config.MAX_POSTS_PER_DAY)))
        min_hours_between_posts = float(cadence_policy.get("min_hours_between_posts", 6))
        daily_mix = self._build_daily_mix_plan(local_now, cadence_policy)
        slot_index = int(slot.get("slot_index", len(local_today))) if slot else len(local_today)

        if len(local_today) >= daily_cap:
            return {"skip_post": True, "skip_reason": "daily_post_cap", "scheduled_post_type": slot.get("post_type") if slot else None}

        if len(local_today) >= daily_mix["target_posts"]:
            return {"skip_post": True, "skip_reason": "daily_target_reached", "scheduled_post_type": None}

        latest_post_time = self._latest_post_time(local_today)
        if latest_post_time and (local_now - latest_post_time).total_seconds() < (min_hours_between_posts * 3600):
            return {"skip_post": True, "skip_reason": "post_spacing_guard", "scheduled_post_type": slot.get("post_type") if slot else None}

        if slot.get("manual") and slot_index not in daily_mix["active_slot_indexes"]:
            upcoming_slots = [
                index for index in daily_mix["active_slot_indexes"]
                if index >= len(local_today)
            ]
            if upcoming_slots:
                slot_index = upcoming_slots[0]
            elif daily_mix["active_slot_indexes"]:
                slot_index = daily_mix["active_slot_indexes"][-1]

        if slot_index not in daily_mix["active_slot_indexes"]:
            return {
                "skip_post": True,
                "skip_reason": "inactive_daily_slot",
                "scheduled_post_type": None,
            }

        desired_post_type = daily_mix["slot_post_types"].get(slot_index, "standalone")
        if desired_post_type == "thread":
            thread_ok, thread_reason = self._thread_slot_allowed(local_now, local_today, cadence_policy, daily_mix)
            if not thread_ok:
                logger.info(
                    "Thread slot downgraded to standalone",
                    phase="EXPERIMENTER",
                    data={"reason": thread_reason, "slot": slot.get("label") if slot else "manual"},
                )
                desired_post_type = "standalone"

        return {
            "skip_post": False,
            "post_type": desired_post_type,
            "scheduled_post_type": desired_post_type,
            "slot_label": slot.get("label") if slot else "manual",
            "daily_target_posts": daily_mix["target_posts"],
            "daily_target_threads": daily_mix["target_threads"],
        }

    def _thread_slot_allowed(
        self,
        local_now: datetime,
        local_today: list,
        cadence_policy: Dict[str, Any],
        daily_mix: Dict[str, Any],
    ) -> tuple[bool, str]:
        today_threads = [tweet for tweet in local_today if tweet.format_type in config.THREAD_ONLY_FORMATS]

        if len(today_threads) >= daily_mix["target_threads"]:
            return False, "thread_daily_target_reached"
        if len(today_threads) >= int(cadence_policy.get("max_threads_per_day", daily_mix["target_threads"])):
            return False, "thread_daily_cap"

        latest_thread_time = self._latest_post_time(today_threads)
        min_hours_between_threads = float(cadence_policy.get("min_hours_between_threads", 4))
        if latest_thread_time and (local_now - latest_thread_time).total_seconds() < (min_hours_between_threads * 3600):
            return False, "thread_spacing_guard"

        if not self._research_supports_thread():
            return False, "insufficient_thread_depth"

        return True, "thread_allowed"

    def _build_daily_mix_plan(self, local_now: datetime, cadence_policy: Dict[str, Any]) -> Dict[str, Any]:
        slots = cadence_policy.get("slots", [])
        opportunities = len(slots)
        if opportunities == 0:
            return {
                "target_posts": 0,
                "target_threads": 0,
                "active_slot_indexes": [],
                "slot_post_types": {},
            }

        seed = int(local_now.strftime("%Y%m%d"))
        rng = random.Random(seed)

        min_posts = int(cadence_policy.get("min_posts_per_day", 5))
        max_posts = min(int(cadence_policy.get("max_posts_per_day", opportunities)), opportunities)
        target_posts = rng.randint(min_posts, max_posts)

        min_threads = int(cadence_policy.get("min_threads_per_day", 1))
        max_threads = min(int(cadence_policy.get("max_threads_per_day", 3)), max(1, target_posts - 1))
        target_threads = rng.randint(min_threads, max_threads)

        active_slot_indexes = sorted(rng.sample(range(opportunities), target_posts))
        thread_slot_indexes = self._choose_thread_slots(active_slot_indexes, target_threads, rng)
        slot_post_types = {
            slot_index: ("thread" if slot_index in thread_slot_indexes else "standalone")
            for slot_index in active_slot_indexes
        }

        return {
            "target_posts": target_posts,
            "target_threads": target_threads,
            "active_slot_indexes": active_slot_indexes,
            "slot_post_types": slot_post_types,
        }

    def _choose_thread_slots(self, active_slot_indexes: list[int], target_threads: int, rng: random.Random) -> set[int]:
        if target_threads <= 0:
            return set()

        shuffled = active_slot_indexes[:]
        rng.shuffle(shuffled)
        chosen: list[int] = []

        for slot_index in shuffled:
            if all(abs(slot_index - existing) > 1 for existing in chosen):
                chosen.append(slot_index)
            if len(chosen) >= target_threads:
                break

        if len(chosen) < target_threads:
            for slot_index in shuffled:
                if slot_index not in chosen:
                    chosen.append(slot_index)
                if len(chosen) >= target_threads:
                    break

        return set(chosen)

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

    def _tweet_local_date(self, posted_at: str):
        try:
            parsed = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(ZoneInfo(config.BOT_TIMEZONE)).date()
        except Exception:
            return self._get_local_now().date()

    def _latest_post_time(self, tweets: list) -> Optional[datetime]:
        latest = None
        for tweet in tweets:
            try:
                parsed = datetime.fromisoformat(tweet.posted_at.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                parsed = parsed.astimezone(ZoneInfo(config.BOT_TIMEZONE))
                if latest is None or parsed > latest:
                    latest = parsed
            except Exception:
                continue
        return latest

    def _research_supports_thread(self) -> bool:
        try:
            path = Path(config.LATEST_RESEARCH_BRIEF_FILE)
            if not path.exists():
                return False
            brief = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return False

        return (
            len(brief.get("top_insights", [])) >= 3
            and len(brief.get("angles", [])) >= 3
            and bool(str(brief.get("emerging_narrative", "")).strip())
        )


# Global experiment manager instance
experimenter = ExperimentManager()
