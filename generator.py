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
from typing import Optional, Dict

import config
from logger import logger
from memory import memory
from validator import validator


# Globals
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
MISTRAL_API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MISTRAL_MODEL = "mistral.large"


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
                    logger.error(f"Mistral API error: {response.status_code}", 
                               event="MISTRAL_ERROR", 
                               error=response.text)
                    return None
                
                data = response.json()
                return data.get("choices", [{}])[0].get("message", {}).get("content")
                
            except Exception as e:
                logger.error(f"Mistral API exception: {str(e)}", event="MISTRAL_ERROR", error=str(e))
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
                "archetype": tweet.get("archetype"),
                "topic": tweet.get("topic"),
                "length": tweet.get("thread_length")
            })
        context["avoid_patterns"] = avoid_patterns
        
        return context
        
    except Exception as e:
        logger.warn(f"Failed to load context: {str(e)}", event="LOAD_CONTEXT_ERROR", error=str(e))
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

Return ONLY a JSON object (no other text) with structure:
{{
  "text": "the tweet content here",
  "archetype": "{archetype}",
  "topic": "{topic}",
  "thread_length": {thread_length},
  "confidence": 0.8,
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
    
    if retry_count >= config.MAX_GEN_ATTEMPTS:
        logger.error("Max generation attempts exceeded", 
                   event="GENERATE_FAILED",
                   data={"archetype": archetype, "topic": topic})
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
        
        # Validate tweet
        validation = validator.validate_tweet(tweet_obj)
        if not validation["valid"]:
            logger.warn(f"Generated tweet failed validation", 
                      event="VALIDATION_FAILED",
                      data={"failures": validation.get("failures", [])})
            if retry_count < config.MAX_GEN_ATTEMPTS - 1:
                await asyncio.sleep(1)
                return await generate_tweet_async(archetype, topic, thread_length, is_experiment, retry_count + 1)
            return None
        
        logger.info("Tweet generated successfully",
                  event="GENERATE_SUCCESS",
                  data={
                      "archetype": archetype,
                      "topic": topic,
                      "thread_length": thread_length,
                      "attempt": retry_count + 1
                  })
        
        return tweet_obj
        
    except Exception as e:
        logger.error(f"Generation failed (attempt {retry_count + 1}): {str(e)}",
                   event="GENERATE_ERROR",
                   data={
                       "error": str(e),
                       "archetype": archetype,
                       "attempt": retry_count + 1
                   })
        
        if retry_count < config.MAX_GEN_ATTEMPTS - 1:
            await asyncio.sleep(1)  # Brief backoff
            return await generate_tweet_async(archetype, topic, thread_length, is_experiment, retry_count + 1)
        
        return None


def generate_tweet(
    archetype: str,
    topic: str,
    thread_length: int = 1,
    is_experiment: bool = False
) -> Optional[Dict]:
    """Synchronous wrapper for async generation (compatibility)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(
            generate_tweet_async(archetype, topic, thread_length, is_experiment)
        )
    finally:
        loop.close()
