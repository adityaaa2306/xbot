"""Mistral-backed pattern extraction and research brief generation."""

import json
import re
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

import config
from ingestion.models import SignalTweet
from ingestion.storage import load_latest_jsonl
from logger import logger
from memory import memory
from nim_client import NimAsyncClient


class ResearchBriefEngine:
    """Turn ranked signals into a compact research brief for generation."""

    def __init__(self, client: Optional[NimAsyncClient] = None):
        self.client = client or NimAsyncClient(config.NVIDIA_API_KEY)

    async def build_brief(self, signals: Sequence[SignalTweet]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        if not signals:
            raise ValueError("No signals provided to research engine")

        analyses = await self._extract_patterns(signals)
        aggregate = await self._aggregate_patterns(analyses)
        insights = await self._compress_insights(aggregate, analyses)
        brief = self._build_research_brief(signals, analyses, aggregate, insights)
        return analyses, brief

    async def _extract_patterns(self, signals: Sequence[SignalTweet]) -> List[Dict[str, Any]]:
        system_message = (
            "You analyze high-performing tweets for structure and psychological signal. "
            "Return only valid JSON."
        )
        user_message = f"""
You are analyzing high-performing tweets.

For each tweet, extract:
1. Core Idea (1 sentence)
2. Hook Type (choose one: contrarian, curiosity, authority, warning, insight)
3. Emotional Trigger (e.g. fear, ambition, validation, urgency)
4. Writing Style (short punchy, structured, storytelling, etc.)
5. Why it worked (specific, not generic)

Return a JSON array of objects with keys:
tweet_id, core_idea, hook_type, emotional_trigger, writing_style, why_it_worked

Tweets:
{json.dumps([self._signal_payload(signal) for signal in signals], ensure_ascii=False)}
"""
        response = await self.client.chat(
            system_message,
            user_message,
            phase="RESEARCH_EXTRACT",
            temperature=0.2,
            max_tokens=1600,
        )
        parsed = self._parse_json_response(response, default=None)
        if isinstance(parsed, list) and parsed:
            return parsed

        logger.warn(
            "RESEARCH_EXTRACT_FALLBACK",
            phase="RESEARCH",
            data={"reason": self._fallback_reason(response, parsed, expected_type="list")},
        )
        return [self._heuristic_analysis(signal) for signal in signals]

    async def _aggregate_patterns(self, analyses: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        system_message = (
            "You summarize recurring patterns from tweet analyses. "
            "Return only valid JSON."
        )
        user_message = f"""
Given these tweet analyses, identify:
1. Top 5 recurring ideas
2. Top 3 hook patterns
3. Common emotional drivers
4. Emerging narrative (what people are currently resonating with)
5. Best angles to write from

Return a JSON object with keys:
recurring_ideas, hook_patterns, emotional_drivers, emerging_narrative, angles

Analyses:
{json.dumps(list(analyses), ensure_ascii=False)}
"""
        response = await self.client.chat(
            system_message,
            user_message,
            phase="RESEARCH_AGGREGATE",
            temperature=0.2,
            max_tokens=1200,
        )
        parsed = self._parse_json_response(response, default=None)
        if isinstance(parsed, dict) and parsed:
            return parsed

        logger.warn(
            "RESEARCH_AGGREGATE_FALLBACK",
            phase="RESEARCH",
            data={"reason": self._fallback_reason(response, parsed, expected_type="dict")},
        )
        return self._heuristic_aggregate(analyses)

    async def _compress_insights(
        self,
        aggregate: Dict[str, Any],
        analyses: Sequence[Dict[str, Any]],
    ) -> List[str]:
        system_message = (
            "You turn observed patterns into original, concise, earned-sounding insights. "
            "Return only valid JSON."
        )
        user_message = f"""
You are generating high-signal insights for a Twitter account.

Based on these patterns, generate 5 insights that:
- are original (not copied)
- are concise (max 15 words)
- feel like earned wisdom
- are slightly contrarian or sharp

Avoid generic advice.

Return a JSON array of strings.

Patterns:
{json.dumps(aggregate, ensure_ascii=False)}

Analyses:
{json.dumps(list(analyses), ensure_ascii=False)}
"""
        response = await self.client.chat(
            system_message,
            user_message,
            phase="RESEARCH_COMPRESS",
            temperature=0.35,
            max_tokens=700,
        )
        parsed = self._parse_json_response(response, default=None)
        if isinstance(parsed, list) and parsed:
            return [str(item).strip() for item in parsed if str(item).strip()][:5]

        logger.warn(
            "RESEARCH_COMPRESS_FALLBACK",
            phase="RESEARCH",
            data={"reason": self._fallback_reason(response, parsed, expected_type="list")},
        )
        return self._heuristic_insights(aggregate)

    def _build_research_brief(
        self,
        signals: Sequence[SignalTweet],
        analyses: Sequence[Dict[str, Any]],
        aggregate: Dict[str, Any],
        insights: Sequence[str],
    ) -> Dict[str, Any]:
        recent_posts = memory.get_recent_tweets(days=14, limit=5)
        recent_hooks = [tweet.hook for tweet in recent_posts if tweet.hook][:5]
        recent_ideas = [tweet.content[:140] for tweet in recent_posts if tweet.content][:5]

        winning_patterns = list(aggregate.get("hook_patterns", []))[:3]
        failed_patterns = self._collect_recent_failed_patterns()

        return {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "top_insights": list(insights)[:5],
            "hook_patterns": list(aggregate.get("hook_patterns", []))[:3],
            "angles": list(aggregate.get("angles", []))[:5],
            "emotional_drivers": list(aggregate.get("emotional_drivers", []))[:4],
            "emerging_narrative": aggregate.get("emerging_narrative", ""),
            "viral_examples": [self._signal_payload(signal) for signal in signals[:5]],
            "analyses_count": len(analyses),
            "winning_patterns": winning_patterns,
            "failed_patterns": failed_patterns,
            "avoid_recent_hooks": recent_hooks,
            "avoid_recent_ideas": recent_ideas,
            "source_summary": dict(Counter(signal.source for signal in signals)),
        }

    def _collect_recent_failed_patterns(self) -> List[str]:
        recent_posts = memory.get_recent_tweets(days=21, limit=10)
        failed = [
            f"{tweet.format_type}:{tweet.topic_bucket}"
            for tweet in recent_posts
            if tweet.engagement_score is not None and tweet.engagement_score <= 0
        ]
        return failed[:5]

    def _parse_json_response(self, response: Optional[str], default: Any) -> Any:
        if not response:
            return default

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            match = re.search(r"(\[.*\]|\{.*\})", response, re.DOTALL)
            if not match:
                return default
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                return default

    def _fallback_reason(self, response: Optional[str], parsed: Any, *, expected_type: str) -> str:
        """Explain why the engine fell back from an LLM response."""
        if not response:
            return "no_llm_response"
        if parsed is None:
            return "invalid_llm_json"
        if expected_type == "list" and not isinstance(parsed, list):
            return f"unexpected_json_type:{type(parsed).__name__}"
        if expected_type == "dict" and not isinstance(parsed, dict):
            return f"unexpected_json_type:{type(parsed).__name__}"
        return "unknown_fallback_reason"

    def _signal_payload(self, signal: SignalTweet) -> Dict[str, Any]:
        return {
            "tweet_id": signal.tweet_id,
            "author": signal.author,
            "text": signal.text,
            "likes": signal.likes,
            "replies": signal.replies,
            "retweets": signal.retweets,
            "rank_score": signal.rank_score,
            "timestamp": signal.timestamp,
            "source": signal.source,
        }

    def _heuristic_analysis(self, signal: SignalTweet) -> Dict[str, Any]:
        hook_type = "contrarian" if any(word in signal.text.lower() for word in ("not", "never", "stop", "most people")) else "insight"
        emotional_trigger = "ambition" if any(word in signal.text.lower() for word in ("freedom", "wealth", "leverage", "build")) else "validation"
        writing_style = "short punchy" if len(signal.text.split(".")) <= 2 else "structured"
        core_idea = signal.text.split(".")[0].strip()
        why_it_worked = "Strong contrast, clear takeaway, and obvious status or leverage signal."
        return {
            "tweet_id": signal.tweet_id,
            "core_idea": core_idea,
            "hook_type": hook_type,
            "emotional_trigger": emotional_trigger,
            "writing_style": writing_style,
            "why_it_worked": why_it_worked,
        }

    def _heuristic_aggregate(self, analyses: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        ideas = [item.get("core_idea", "") for item in analyses if item.get("core_idea")]
        hooks = Counter(item.get("hook_type", "") for item in analyses if item.get("hook_type"))
        emotions = Counter(item.get("emotional_trigger", "") for item in analyses if item.get("emotional_trigger"))

        recurring_ideas = ideas[:5]
        hook_patterns = [hook for hook, _ in hooks.most_common(3)]
        emotional_drivers = [emotion for emotion, _ in emotions.most_common(3)]
        angles = recurring_ideas[:3]

        return {
            "recurring_ideas": recurring_ideas,
            "hook_patterns": hook_patterns,
            "emotional_drivers": emotional_drivers,
            "emerging_narrative": recurring_ideas[0] if recurring_ideas else "",
            "angles": angles,
        }

    def _heuristic_insights(self, aggregate: Dict[str, Any]) -> List[str]:
        candidates = aggregate.get("recurring_ideas") or aggregate.get("angles") or []
        trimmed = []
        for item in candidates:
            words = str(item).split()
            trimmed.append(" ".join(words[:15]))
        fallback = trimmed[:5]
        if fallback:
            return fallback
        return [
            "Leverage compounds where labor plateaus.",
            "Audience ownership beats borrowed reach.",
            "Clarity scales faster than intensity.",
        ]


def load_latest_research_brief() -> Optional[Dict[str, Any]]:
    """Read the most recent persisted research brief when available."""
    return load_latest_jsonl(config.RESEARCH_BRIEF_LOG_FILE)
