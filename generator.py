"""
generator.py - Async LLM Tweet Generation

Generates tweets and threads using the NVIDIA-hosted chat-completions API.
Includes retry protection, response validation, and a deterministic fallback
so temporary provider failures do not fail the whole posting cycle.
"""

import asyncio
import json
import os
import re
from typing import Any, Dict, Optional, Tuple

import config
from ingestion.storage import load_json
from logger import logger
from memory import memory
from nim_client import NimAsyncClient, is_valid_model_response
from validator import validator


NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")


async def load_context() -> Dict[str, Any]:
    """Load lightweight prompt context from niche, strategy, research, and recent posts."""
    context: Dict[str, Any] = {}

    try:
        niche_path = config.NICHE_CONFIG_PATH
        if os.path.exists(niche_path):
            with open(niche_path, "r", encoding="utf-8") as handle:
                context["niche"] = handle.read()

        strategy_logs = memory.get_strategy_logs(days=1)
        if strategy_logs:
            context["strategy"] = strategy_logs[0]

        research_brief = load_json(config.LATEST_RESEARCH_BRIEF_FILE)
        if research_brief:
            context["research_brief"] = research_brief

        recent = memory.get_recent_tweets(days=7, limit=20)
        avoid_patterns = []
        recent_hooks = []
        recent_ideas = []
        for tweet in recent:
            avoid_patterns.append(
                {
                    "archetype": tweet.format_type,
                    "topic": tweet.topic_bucket,
                    "length": 1,
                }
            )
            if tweet.hook:
                recent_hooks.append(tweet.hook)
            if tweet.content:
                recent_ideas.append(tweet.content[:140])
        context["avoid_patterns"] = avoid_patterns
        context["recent_hooks"] = recent_hooks[:5]
        context["recent_ideas"] = recent_ideas[:5]
        return context
    except Exception as exc:
        logger.warn("LOAD_CONTEXT_ERROR", phase="GENERATOR", data={"error": str(exc)})
        return {}


def build_generation_prompt(
    archetype: str,
    topic: str,
    tone: str,
    thread_length: int,
    is_experiment: bool,
    context: Dict[str, Any],
) -> Tuple[str, str]:
    """Build system and user messages for the LLM."""
    niche = context.get("niche", "")
    strategy = context.get("strategy", {})
    avoid_patterns = context.get("avoid_patterns", [])
    research_brief = context.get("research_brief", {})
    recent_hooks = context.get("recent_hooks", [])
    recent_ideas = context.get("recent_ideas", [])

    research_summary = {
        "top_insights": research_brief.get("top_insights", [])[:5],
        "hook_patterns": research_brief.get("hook_patterns", [])[:3],
        "angles": research_brief.get("angles", [])[:5],
        "emotional_drivers": research_brief.get("emotional_drivers", [])[:4],
        "emerging_narrative": research_brief.get("emerging_narrative", ""),
        "winning_patterns": research_brief.get("winning_patterns", [])[:3],
        "failed_patterns": research_brief.get("failed_patterns", [])[:5],
    }

    system_msg = f"""You are an autonomous X (Twitter) bot that generates engaging, authentic tweets.

BOT IDENTITY:
{niche}

CURRENT STRATEGY:
{json.dumps(strategy, indent=2)[:500]}

LIVE SIGNAL RESEARCH BRIEF:
{json.dumps(research_summary, indent=2)[:1200]}

IMPORTANT: Generate tweets that follow the bot's personality and topic expertise.
- Be authentic and avoid overly promotional language
- Follow X best practices for engagement
- Keep technical jargon accessible
- HARD LIMIT: every single tweet must be 280 characters or fewer
- TARGET: aim for 180-240 characters for single tweets
- If you cannot fit the idea cleanly, simplify it instead of exceeding the limit
- Use the research brief as inspiration, not as copy
- Never copy or closely paraphrase viral examples
- Prefer patterns, structures, and emotional angles over borrowed wording

Return ONLY a JSON object (no other text) with structure:
{{
  "tweet": "the tweet content here",
  "format_type": "{archetype}",
  "topic_bucket": "{topic}",
  "tone": "{tone}",
  "hook": "opening hook",
  "thread_length": {thread_length},
  "reasoning": "why this tweet was generated"
}}
"""

    avoid_str = "\n".join(
        [f"- {pattern['archetype']} + {pattern['topic']} (recent post)" for pattern in avoid_patterns[-5:]]
    )
    recent_hook_str = "\n".join(f"- {hook}" for hook in recent_hooks[:5]) or "- none"
    recent_idea_str = "\n".join(f"- {idea}" for idea in recent_ideas[:5]) or "- none"
    experiment_note = (
        "This is an EXPERIMENT - try something novel that we haven't tested yet."
        if is_experiment
        else "Follow current top-performing patterns."
    )

    user_msg = f"""Generate a {'thread' if thread_length > 1 else 'single'} tweet.

ARCHETYPE: {archetype}
TOPIC: {topic}
TONE: {tone}
THREAD_LENGTH: {thread_length}
MODE: {experiment_note}

RECENTLY USED (AVOID IMMEDIATE REPETITION):
{avoid_str}

RECENT BOT HOOKS TO AVOID REPEATING:
{recent_hook_str}

RECENT BOT IDEAS TO AVOID REPEATING:
{recent_idea_str}

LIVE MARKET SIGNALS TO LEARN FROM:
{json.dumps(research_summary, indent=2)[:1200]}

Generate a new, engaging tweet now:"""

    return system_msg, user_msg


def get_generation_max_tokens(thread_length: int) -> int:
    """Cap generation length tightly so CI runners respond faster."""
    if thread_length and thread_length > 1:
        return config.GENERATION_MAX_TOKENS_THREAD
    return config.GENERATION_MAX_TOKENS_SINGLE


def retry_delay_seconds(attempt_number: int) -> float:
    """Exponential backoff with a cap."""
    return min(
        config.GENERATION_RETRY_MAX_DELAY_SECS,
        config.GENERATION_RETRY_BASE_DELAY_SECS * (2 ** max(0, attempt_number - 1)),
    )


def build_template_fallback(
    archetype: str,
    topic: str,
    tone: str,
    is_experiment: bool,
    failure_reason: str,
) -> Dict[str, Any]:
    """Build a deterministic fallback tweet when the provider gives no content."""
    topic_map = {
        "wealth_leverage": "wealth and leverage",
        "creator_economy": "one-person businesses",
        "psychology": "performance psychology",
        "freedom": "freedom-first living",
    }
    subject = topic_map.get(topic, topic.replace("_", " "))

    archetype_templates = {
        "brutal_truth": f"Nobody tells you this: {subject} rewards ownership more than effort. The people who look lucky usually built leverage before they needed it.",
        "most_people_vs_smart_people": f"Most people use {subject} to feel productive. Smart people use it to buy back their time.",
        "if_you_understand_this": f"If you understand this, you win: {subject} compounds when you build assets, not when you keep renting out your hours.",
        "kill_a_belief": f"Stop believing that harder work fixes {subject}. The real shift comes when you redesign the system producing the result.",
        "equation": f"Clarity + leverage = better {subject}. Better {subject} + time = freedom.",
        "stacked_insight": f"Learn to think clearly about {subject}. Learn to build assets around {subject}. Learn to wait while {subject} compounds.",
        "identity_shift": f"You're not behind in {subject}. You're just still measuring progress with the wrong scoreboard.",
        "contrarian_insight": f"The real problem isn't effort in {subject}. It's building a life that still depends on effort after you learn better.",
        "reframe": f"{subject.title()} is not about doing more. {subject.title()} is about needing less force to create the same result.",
        "thread_opener": f"Most people never get free through {subject}. They just find a more impressive version of dependence. Here's what they miss:",
    }
    tone_suffixes = {
        "contrarian": "Most people only notice this after the cost is obvious.",
        "analytical": "That pattern shows up long before the metrics make it undeniable.",
        "educational": "Once you see it, a lot of second-order decisions get easier.",
        "observational": "You can watch this happen in real time if you stop listening to the loudest narrative.",
        "provocative": "The uncomfortable part is that almost everyone pretends not to see it until it is expensive.",
    }

    base_text = archetype_templates.get(archetype, archetype_templates["brutal_truth"])
    suffix = tone_suffixes.get(tone, tone_suffixes["analytical"])
    text = shorten_tweet_text(f"{base_text} {suffix}")
    hook = text.split(".")[0].strip() or text[: config.MAX_HOOK_LENGTH]

    return {
        "tweet": text,
        "format_type": archetype,
        "topic_bucket": topic,
        "tone": tone if tone in config.VALID_TONES else "analytical",
        "hook": hook[: config.MAX_HOOK_LENGTH],
        "thread_length": 1,
        "reasoning": f"Template fallback used after generation retries failed ({failure_reason}).",
        "confidence": 0.35 if is_experiment else 0.5,
    }


async def generate_tweet_async(
    archetype: str,
    topic: str,
    tone: str = "analytical",
    thread_length: int = 1,
    is_experiment: bool = False,
) -> Optional[Dict[str, Any]]:
    """Generate a tweet with retries and template fallback."""
    context = await load_context()
    system_msg, user_msg = build_generation_prompt(archetype, topic, tone, thread_length, is_experiment, context)
    client = NimAsyncClient(NVIDIA_API_KEY)
    last_error = "unknown_generation_error"

    for attempt in range(1, config.MAX_GENERATION_ATTEMPTS + 1):
        try:
            response = await client.chat(
                system_msg,
                user_message=user_msg,
                temperature=config.GENERATION_TEMPERATURE,
                max_tokens=get_generation_max_tokens(thread_length),
                phase="GENERATOR",
            )

            if not is_valid_model_response(response):
                last_error = "empty_response"
                raise ValueError("Mistral returned empty response")

            try:
                raw_tweet = json.loads(response)
            except json.JSONDecodeError:
                json_match = re.search(r"\{.*\}", response, re.DOTALL)
                if not json_match:
                    last_error = "unparseable_response"
                    raise ValueError(f"Could not parse JSON from response: {response[:100]}")
                raw_tweet = json.loads(json_match.group())

            tweet_obj = normalize_tweet_object(raw_tweet, archetype, topic, thread_length, tone=tone)
            validation = validator.validate_tweet(tweet_obj)
            if validation["valid"]:
                logger.info(
                    "GENERATE_SUCCESS",
                    phase="SYSTEM",
                    data={
                        "archetype": archetype,
                        "topic": topic,
                        "thread_length": tweet_obj.get("thread_length", 1),
                        "attempt": attempt,
                    },
                )
                return tweet_obj

            last_error = "validation_failed"
            logger.warn(
                "VALIDATION_FAILED",
                phase="GENERATOR",
                data={"attempt": attempt, "failures": validation.get("failures", [])},
            )
        except Exception as exc:
            last_error = last_error if last_error != "unknown_generation_error" else str(exc)
            logger.error(
                "GENERATE_ERROR",
                phase="SYSTEM",
                data={
                    "error": str(exc),
                    "archetype": archetype,
                    "topic": topic,
                    "attempt": attempt,
                },
            )

        if attempt < config.MAX_GENERATION_ATTEMPTS:
            delay = retry_delay_seconds(attempt)
            logger.warn(
                "GENERATE_RETRYING",
                phase="GENERATOR",
                data={"attempt": attempt, "backoff_seconds": delay, "reason": last_error},
            )
            await asyncio.sleep(delay)

    if config.GENERATION_TEMPLATE_FALLBACK_ENABLED:
        fallback_raw = build_template_fallback(archetype, topic, tone, is_experiment, last_error)
        fallback_tweet = normalize_tweet_object(fallback_raw, archetype, topic, 1, tone=tone)
        fallback_validation = validator.validate_tweet(fallback_tweet)
        if fallback_validation["valid"]:
            logger.warn(
                "GENERATE_FALLBACK_USED",
                phase="GENERATOR",
                data={
                    "archetype": archetype,
                    "topic": topic,
                    "tone": tone,
                    "reason": last_error,
                },
            )
            return fallback_tweet

        logger.error(
            "GENERATE_FALLBACK_INVALID",
            phase="GENERATOR",
            data={"reason": last_error, "failures": fallback_validation.get("failures", [])},
        )

    logger.error(
        "GENERATE_FAILED",
        phase="GENERATOR",
        data={"archetype": archetype, "topic": topic, "tone": tone, "reason": last_error},
    )
    return None


async def generate_tweet(
    archetype: str,
    topic: str,
    tone: str = "analytical",
    thread_length: int = 1,
    is_experiment: bool = False,
) -> Optional[Dict[str, Any]]:
    """Async wrapper around the core generation routine."""
    return await generate_tweet_async(archetype, topic, tone, thread_length, is_experiment)


def normalize_tweet_object(
    raw: Dict[str, Any],
    archetype: str,
    topic: str,
    thread_length: int,
    tone: str = "analytical",
) -> Dict[str, Any]:
    """Normalize model output into the validator/poster schema."""
    text = raw.get("tweet") or raw.get("text") or ""
    text_parts = raw.get("text_parts")

    if isinstance(text, list):
        text_parts = text
        text = "\n\n".join(text)

    if thread_length > 1 and not text_parts:
        parts = [part.strip() for part in str(text).split("\n\n") if part.strip()]
        text_parts = parts if parts else [str(text)]

    if isinstance(text_parts, list):
        text_parts = [shorten_tweet_text(str(part)) for part in text_parts]
        text = "\n\n".join(text_parts)
    else:
        text = shorten_tweet_text(str(text))

    lines = [line.strip() for line in str(text).splitlines() if line.strip()]
    hook = raw.get("hook") or (lines[0] if lines else str(text)[: config.MAX_HOOK_LENGTH])

    return {
        "tweet": str(text),
        "text": str(text),
        "text_parts": text_parts,
        "format_type": raw.get("format_type") or raw.get("archetype") or archetype,
        "topic_bucket": raw.get("topic_bucket") or raw.get("topic") or topic,
        "tone": raw.get("tone") or tone or "analytical",
        "hook": str(hook)[: config.MAX_HOOK_LENGTH],
        "thread_length": int(raw.get("thread_length") or thread_length or 1),
        "reasoning": raw.get("reasoning") or "Generated from current strategy context.",
        "confidence": raw.get("confidence", 0.8),
    }


def shorten_tweet_text(text: str, max_length: int = config.MAX_TWEET_LENGTH) -> str:
    """Trim overlong model output to a tweet-safe length while preserving readability."""
    compact = " ".join(text.split())
    if len(compact) <= max_length:
        return compact

    sentences = [
        sentence.strip()
        for sentence in compact.replace("! ", "!|").replace("? ", "?|").replace(". ", ".|").split("|")
        if sentence.strip()
    ]
    if sentences:
        candidate = ""
        for sentence in sentences:
            proposed = f"{candidate} {sentence}".strip()
            if len(proposed) <= max_length:
                candidate = proposed
            else:
                break
        if candidate:
            return candidate

    words = compact.split()
    candidate = ""
    for word in words:
        proposed = f"{candidate} {word}".strip()
        if len(proposed) + 3 <= max_length:
            candidate = proposed
        else:
            break

    candidate = candidate.rstrip(" ,;:-")
    if not candidate:
        return compact[: max_length - 3].rstrip() + "..."
    if len(candidate) < len(compact):
        return candidate[: max_length - 3].rstrip(" ,;:-") + "..."
    return candidate
