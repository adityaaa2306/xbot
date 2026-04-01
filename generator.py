"""
generator.py — Async LLM Tweet Generation

Generates tweets and threads using NVIDIA Mistral LLM.
Features:
- Async/await for non-blocking API calls
- 3-attempt retry logic with exponential backoff
- Anti-pattern injection (tells model what NOT to repeat)
- Archetype/topic/thread_length guidance
- JSON validation + fallback parsing
"""

import asyncio
import json
import os
import httpx
from typing import Optional, Dict, Any

import config
from logger import logger
from memory import memory
from validator import validator


# Globals
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
MISTRAL_API_URL = config.NVIDIA_ENDPOINT
MISTRAL_MODEL = config.NVIDIA_MODEL


class MistralAsyncClient:
    """Async wrapper for NVIDIA Mistral LLM."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    async def chat(self, system_message: str, user_message: str, temperature: float = 0.7) -> Optional[str]:
        """Call Mistral chat API asynchronously."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    MISTRAL_API_URL,
                    headers=self.headers,
                    json={
                        "model": MISTRAL_MODEL,
                        "messages": [
                            {"role": "system", "content": system_message},
                            {"role": "user", "content": user_message}
                        ],
                        "temperature": temperature,
                        "top_p": 0.95,
                        "max_tokens": 1024
                    }
                )
                
                if response.status_code != 200:
                    logger.error(
                        "MISTRAL_ERROR",
                        data={"status_code": response.status_code, "response": response.text},
                    )
                    return None
                
                data = response.json()
                return data.get("choices", [{}])[0].get("message", {}).get("content")
                
            except Exception as e:
                logger.error("MISTRAL_ERROR", data={"error": str(e)})
                return None


async def load_context() -> Dict:
    """Load niche.md, strategy.md, and recent patterns for prompt injection."""
    context = {}
    
    try:
        # Load niche
        niche_path = "config/niche.md"
        if os.path.exists(niche_path):
            with open(niche_path, "r") as f:
                context["niche"] = f.read()
        
        # Load strategy
        strategy_logs = memory.get_strategy_logs(days=1)
        if strategy_logs:
            context["strategy"] = strategy_logs[0]
        
        # Load recent patterns (what NOT to repeat)
        recent = memory.get_recent_tweets(days=7, limit=20)
        avoid_patterns = []
        for tweet in recent:
            avoid_patterns.append({
                "archetype": tweet.format_type,
                "topic": tweet.topic_bucket,
                "length": 1,
            })
        context["avoid_patterns"] = avoid_patterns
        
        return context
        
    except Exception as e:
        logger.warn("LOAD_CONTEXT_ERROR", data={"error": str(e)})
        return {}


def build_generation_prompt(archetype: str, topic: str, thread_length: int, is_experiment: bool, context: Dict) -> tuple:
    """Build system and user messages for LLM."""
    
    niche = context.get("niche", "")
    strategy = context.get("strategy", {})
    avoid_patterns = context.get("avoid_patterns", [])
    
    # Build system message
    system_msg = f"""You are an autonomous X (Twitter) bot that generates engaging, authentic tweets.

BOT IDENTITY:
{niche}

CURRENT STRATEGY:
{json.dumps(strategy, indent=2)[:500]}

IMPORTANT: Generate tweets that follow the bot's personality and topic expertise.
- Be authentic and avoid overly promotional language
- Follow X best practices for engagement
- Include relevant hashtags if appropriate
- Keep technical jargon accessible
- HARD LIMIT: every single tweet must be 280 characters or fewer
- TARGET: aim for 180-240 characters for single tweets
- If you cannot fit the idea cleanly, simplify it instead of exceeding the limit

Return ONLY a JSON object (no other text) with structure:
{{
  "tweet": "the tweet content here",
  "format_type": "{archetype}",
  "topic_bucket": "{topic}",
  "tone": "analytical",
  "hook": "opening hook",
  "thread_length": {thread_length},
  "reasoning": "why this tweet was generated"
}}
"""
    
    # Build user message
    avoid_str = "\n".join([
        f"- {p['archetype']} + {p['topic']} (recent post)" 
        for p in avoid_patterns[-5:]
    ])
    
    experiment_note = "This is an EXPERIMENT - try something novel that we haven't tested yet." if is_experiment else "Follow current top-performing patterns."
    
    user_msg = f"""Generate a {'thread' if thread_length > 1 else 'single'} tweet.

ARCHETYPE: {archetype}
TOPIC: {topic}
THREAD_LENGTH: {thread_length}
MODE: {experiment_note}

RECENTLY USED (AVOID IMMEDIATE REPETITION):
{avoid_str}

Generate a new, engaging tweet now:"""
    
    return system_msg, user_msg


async def generate_tweet_async(
    archetype: str,
    topic: str,
    thread_length: int = 1,
    is_experiment: bool = False,
    retry_count: int = 0
) -> Optional[Dict]:
    """Generate a tweet using async Mistral API with retries."""
    
    if retry_count >= config.MAX_GENERATION_ATTEMPTS:
        logger.error("GENERATE_FAILED", data={"archetype": archetype, "topic": topic})
        return None
    
    try:
        # Load context
        context = await load_context()
        
        # Build prompts
        system_msg, user_msg = build_generation_prompt(archetype, topic, thread_length, is_experiment, context)
        
        # Call Mistral
        client = MistralAsyncClient(NVIDIA_API_KEY)
        response = await client.chat(system_msg, user_msg)
        
        if not response:
            raise Exception("Mistral returned empty response")
        
        # Parse JSON
        try:
            tweet_obj = json.loads(response)
        except json.JSONDecodeError:
            # Fallback: try to extract JSON from response
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                tweet_obj = json.loads(json_match.group())
            else:
                raise Exception(f"Could not parse JSON from response: {response[:100]}")

        tweet_obj = normalize_tweet_object(tweet_obj, archetype, topic, thread_length)
        
        # Validate tweet
        validation = validator.validate_tweet(tweet_obj)
        if not validation["valid"]:
            logger.warn(
                "VALIDATION_FAILED",
                data={"failures": validation.get("failures", [])},
            )
            if retry_count < config.MAX_GENERATION_ATTEMPTS - 1:
                await asyncio.sleep(1)
                return await generate_tweet_async(archetype, topic, thread_length, is_experiment, retry_count + 1)
            return None
        
        logger.info(
            "GENERATE_SUCCESS",
            data={
                "archetype": archetype,
                "topic": topic,
                "thread_length": thread_length,
                "attempt": retry_count + 1,
            },
        )
        
        return tweet_obj
        
    except Exception as e:
        logger.error(
            "GENERATE_ERROR",
            data={
                "error": str(e),
                "archetype": archetype,
                "attempt": retry_count + 1,
            },
        )
        
        if retry_count < config.MAX_GENERATION_ATTEMPTS - 1:
            await asyncio.sleep(1)  # Brief backoff
            return await generate_tweet_async(archetype, topic, thread_length, is_experiment, retry_count + 1)
        
        return None


async def generate_tweet(
    archetype: str,
    topic: str,
    thread_length: int = 1,
    is_experiment: bool = False
) -> Optional[Dict]:
    """Async wrapper that delegates to generate_tweet_async."""
    return await generate_tweet_async(archetype, topic, thread_length, is_experiment)


def normalize_tweet_object(raw: Dict[str, Any], archetype: str, topic: str, thread_length: int) -> Dict[str, Any]:
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
        "tone": raw.get("tone") or "analytical",
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

    # Prefer trimming at sentence boundaries first.
    sentences = [sentence.strip() for sentence in compact.replace("! ", "!|").replace("? ", "?|").replace(". ", ".|").split("|") if sentence.strip()]
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

    # Fall back to trimming at word boundaries with an ellipsis.
    words = compact.split()
    candidate = ""
    for word in words:
        proposed = f"{candidate} {word}".strip()
        if len(proposed) + 1 <= max_length:
            candidate = proposed
        else:
            break

    candidate = candidate.rstrip(" ,;:-")
    if not candidate:
        return compact[: max_length - 1].rstrip() + "…"
    if len(candidate) < len(compact):
        return candidate[: max_length - 1].rstrip(" ,;:-") + "…"
    return candidate
