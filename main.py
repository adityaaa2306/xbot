"""
main.py — Production-Grade Daily Pipeline Orchestrator with Timeout & Circuit Breaker

7-Phase Daily Workflow:
1. FETCH:      Fetch metrics for all pending tweets (2h, 24h, 72h windows)
2. SCORE:      Score mature tweets (48h+), detect pattern decay
3. STRATEGIST: Reflect on data, update strategy.md with LLM insights
4. PLAN:       Decide exploit vs explore for today's post
5. GENERATOR:  Generate tweet/thread using Mistral LLM (with timeout)
6. VALIDATOR:  Quality gate (11 checks), duplicate detection, toxicity
7. POSTER:     Post to X API, log experiment for learning

Production Features:
- Timeout protection: LLM calls max 30s, poster calls max 15s
- Circuit breaker: Stop posting after 3 consecutive failures
- JSON backup: Auto-backup memory state before risky operations
- Error recovery: Graceful degradation, detailed logging of all failures
- Structured logging: JSON to both stdout + JSONL files
"""

import asyncio
import json
import os
import sys
import shutil
from datetime import datetime
from pathlib import Path

import config
from logger import logger
from memory import memory
from fetcher import fetcher
from scorer import scorer
from validator import validator
from experimenter import experimenter
from strategist import strategist
from generator import generate_tweet
from poster import post_tweet, append_experiment


class PipelineCircuitBreaker:
    """
    Circuit breaker pattern to prevent cascading failures.
    If N consecutive failures occur, stops trying to post.
    """
    
    def __init__(self, threshold=config.CIRCUIT_BREAKER_THRESHOLD):
        self.threshold = threshold
        self.consecutive_failures = 0
        self.is_open = False
        self.last_failure_time = None
    
    def record_failure(self, reason="unknown"):
        self.consecutive_failures += 1
        self.last_failure_time = datetime.utcnow()
        
        if self.consecutive_failures >= self.threshold:
            self.is_open = True
            logger.error(
                "CIRCUIT_BREAKER",
                data={
                    "consecutive_failures": self.consecutive_failures,
                    "reason": reason,
                    "opened_at": self.last_failure_time.isoformat()
                }
            )
    
    def record_success(self):
        if self.consecutive_failures > 0:
            logger.info(
                "CIRCUIT_BREAKER",
                data={"previous_failures": self.consecutive_failures}
            )
        self.consecutive_failures = 0
        self.is_open = False
    
    def can_proceed(self) -> bool:
        return not self.is_open


def backup_memory():
    """
    Backup memory state before risky operations.
    Allows rollback if memory gets corrupted.
    """
    try:
        backup_dir = Path(config.JSON_BACKUP_DIR)
        backup_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        
        for src in [
            Path(config.TWEET_LOG_FILE),
            Path(config.STRATEGY_LOG_FILE),
            Path(config.PATTERN_LIBRARY_FILE),
            Path("strategy.md"),
            Path("data/experiments.jsonl"),
        ]:
            if src.exists():
                dest = backup_dir / f"{src.name}.{timestamp}.bkp"
                shutil.copy2(src, dest)
                
                # Keep only last 10 backups per file
                backups = sorted(list(backup_dir.glob(f"{src.name}.*.bkp")))
                if len(backups) > 10:
                    for old_backup in backups[:-10]:
                        old_backup.unlink()
        
        logger.debug("BACKUP", data={"timestamp": timestamp})
    except Exception as e:
        logger.warn("BACKUP", data={"error": str(e)})


async def verify_environment() -> bool:
    """Verify all credentials and directories."""
    logger.info("STARTUP", data={"status": "verifying"})
    
    required_vars = ["NVIDIA_API_KEY", "GETXAPI_API_KEY"]
    missing = [v for v in required_vars if not os.getenv(v)]
    
    if missing:
        logger.error("STARTUP", data={"missing": missing})
        return False

    if not os.getenv("GETXAPI_AUTH_TOKEN"):
        logger.error(
            "STARTUP",
            data={
                "missing": [
                    "GETXAPI_AUTH_TOKEN"
                ]
            },
        )
        return False
    
    for directory in ["logs", "memory", "data", config.JSON_BACKUP_DIR]:
        Path(directory).mkdir(parents=True, exist_ok=True)
    
    logger.info("STARTUP", data={"status": "verified"})
    return True


async def phase_1_fetch_metrics() -> bool:
    """Phase 1: Fetch metrics for pending tweets (NON-FATAL)."""
    try:
        logger.info("Phase 1 START", phase="FETCH", data={})
        
        pending = memory.get_recent_tweets(days=3, limit=100)
        if not pending:
            logger.info("Phase 1 SKIP", phase="FETCH", data={"reason": "no_pending"})
            return True
        
        updated = fetcher.fetch_all_pending(memory)
        logger.info("Phase 1 COMPLETE", phase="FETCH", data={"updated": updated})
        return True
        
    except Exception as e:
        logger.error("Phase 1 FAILED (non-fatal, continuing)", phase="FETCH", error=str(e))
        return False  # Non-fatal: continue to next phase


async def phase_2_score_mature() -> bool:
    """Phase 2: Score mature tweets (NON-FATAL)."""
    try:
        logger.info("Phase 2 START", phase="SCORE", data={})
        
        mature = memory.get_mature_tweets()
        if not mature:
            logger.info("Phase 2 SKIP", phase="SCORE", data={"reason": "no_mature"})
            return True
        
        scored = 0
        for tweet in mature:
            try:
                score = scorer.score_tweet(tweet)
                memory.update_score(tweet.tweet_id, score)
                scored += 1
            except Exception as e:
                logger.warn(f"Score failed for {tweet.tweet_id}", phase="SCORE", error=str(e))
        
        logger.info("Phase 2 COMPLETE", phase="SCORE", data={"scored": scored})
        return True
        
    except Exception as e:
        logger.error("Phase 2 FAILED (non-fatal, continuing)", phase="SCORE", error=str(e))
        return False  # Non-fatal: continue to next phase


async def phase_3_update_strategy() -> bool:
    """Phase 3: Update strategy with LLM reflection (NON-FATAL)."""
    try:
        logger.info("Phase 3 START", phase="STRATEGIST", data={})
        
        mature_count = len(memory.get_mature_tweets())
        if mature_count < config.MIN_MATURE_TWEETS_TO_LEARN:
            logger.info("Phase 3 SKIP", phase="STRATEGIST", 
                       data={"reason": "insufficient_data", "mature_count": mature_count})
            return True
        
        strategy = await strategist.reflect_and_update_strategy()
        if strategy:
            logger.info("Phase 3 COMPLETE", phase="STRATEGIST", 
                       data={"confidence": strategy.get("confidence_level")})
        else:
            logger.info("Phase 3 SKIP", phase="STRATEGIST", data={"reason": "reflection_returned_none"})
        return True
        
    except Exception as e:
        logger.warn(f"Phase 3 NON-FATAL: {str(e)}", phase="STRATEGIST", error=str(e))
        return True  # Non-fatal: continue


async def phase_4_plan_post() -> dict:
    """Phase 4: Plan today's post (exploit vs explore) (FATAL)."""
    try:
        logger.info("Phase 4 START", phase="EXPERIMENTER", data={})
        
        plan = experimenter.get_todays_plan()
        
        with open("data/todays_plan.json", "w") as f:
            json.dump(plan, f)
        
        logger.info("Phase 4 COMPLETE", phase="EXPERIMENTER", 
                   data={
                       "format": plan.get("format_type"),
                       "topic": plan.get("topic_bucket"), 
                       "is_experiment": plan.get("is_experiment")
                   })
        return plan
        
    except Exception as e:
        logger.error("Phase 4 FAILED (FATAL)", phase="EXPERIMENTER", error=str(e))
        return None


async def phase_5_generate() -> dict:
    """Phase 5: Generate tweet with LLM (FATAL, with timeout protection)."""
    try:
        logger.info("Phase 5 START", phase="GENERATOR", data={})
        
        with open("data/todays_plan.json", "r") as f:
            plan = json.load(f)
        
        # Wrap generator call with timeout
        try:
            logger.debug(
                f"Calling Mistral with {config.LLM_TIMEOUT_SECS}s request timeout and {config.GENERATION_PHASE_TIMEOUT_SECS}s phase timeout",
                        phase="GENERATOR", data={})
            tweet_obj = await asyncio.wait_for(
                generate_tweet(
                    archetype=plan.get("format_type"),
                    topic=plan.get("topic_bucket"),
                    tone=plan.get("tone", "analytical"),
                    thread_length=plan.get("thread_length", 1),
                    is_experiment=plan.get("is_experiment", False)
                ),
                timeout=config.GENERATION_PHASE_TIMEOUT_SECS
            )
        except asyncio.TimeoutError:
            logger.error(
                "Phase 5 TIMEOUT",
                phase="GENERATOR",
                data={
                    "request_timeout_seconds": config.LLM_TIMEOUT_SECS,
                    "phase_timeout_seconds": config.GENERATION_PHASE_TIMEOUT_SECS,
                }
            )
            return None
        
        if not tweet_obj:
            logger.error("Phase 5 FAILED (FATAL)", phase="GENERATOR", error="generation_returned_none")
            return None
        
        with open("data/generated_tweet.json", "w") as f:
            json.dump(tweet_obj, f)
        
        logger.info("Phase 5 COMPLETE", phase="GENERATOR",
                   data={"thread_length": tweet_obj.get("thread_length", 1)})
        return tweet_obj
        
    except Exception as e:
        logger.error("Phase 5 FAILED (FATAL)", phase="GENERATOR", error=str(e))
        return None


async def phase_6_validate(circuit_breaker) -> dict:
    """Phase 6: Validate tweet quality (FATAL)."""
    try:
        logger.info("Phase 6 START", phase="VALIDATOR", data={})
        
        with open("data/generated_tweet.json", "r") as f:
            tweet_obj = json.load(f)
        
        result = validator.validate_tweet(tweet_obj)
        
        if not result["valid"]:
            logger.error("Phase 6 FAILED (FATAL)", phase="VALIDATOR",
                        data={"failures": result.get("failures", [])})
            circuit_breaker.record_failure(reason="validation_failed")
            return None
        
        if result.get("warnings"):
            logger.warn("Phase 6 warnings", phase="VALIDATOR",
                       data={"warnings": result.get("warnings", [])})
        
        logger.info("Phase 6 COMPLETE", phase="VALIDATOR", data={})
        return tweet_obj
        
    except Exception as e:
        logger.error("Phase 6 FAILED (FATAL)", phase="VALIDATOR", error=str(e))
        circuit_breaker.record_failure(reason="validation_exception")
        return None


async def phase_7_post(circuit_breaker) -> bool:
    """Phase 7: Post to X (FATAL, with timeout protection)."""
    
    if circuit_breaker.is_open:
        logger.error("Phase 7 BLOCKED: Circuit breaker is OPEN", phase="POSTER",
                    data={"consecutive_failures": circuit_breaker.consecutive_failures})
        return False
    
    try:
        logger.info("Phase 7 START", phase="POSTER", data={})
        
        with open("data/generated_tweet.json", "r") as f:
            tweet_obj = json.load(f)
        
        with open("data/todays_plan.json", "r") as f:
            plan = json.load(f)
        
        # Backup memory before risky operation
        backup_memory()
        
        # Wrap poster call with timeout
        try:
            logger.debug(f"Calling X API with timeout", phase="POSTER", data={})
            result = await asyncio.wait_for(
                post_tweet(tweet_obj),
                timeout=config.POSTER_TIMEOUT_SECS
            )
        except asyncio.TimeoutError:
            logger.error(
                "Phase 7 TIMEOUT",
                phase="POSTER",
                data={"timeout_seconds": config.POSTER_TIMEOUT_SECS}
            )
            circuit_breaker.record_failure(reason="post_timeout")
            return False
        
        if not result:
            logger.error("Phase 7 FAILED (FATAL)", phase="POSTER", error="posting_returned_none")
            circuit_breaker.record_failure(reason="post_returned_none")
            return False
        
        # Log to memory
        try:
            memory.add_tweet_to_log(tweet_obj, result, plan)
            append_experiment({
                "tweet_id": result.get("tweet_id") or result.get("thread_id"),
                "text": tweet_obj.get("text"),
                "archetype": tweet_obj.get("format_type"),
                "thread_length": tweet_obj.get("thread_length", 1),
                "topic": tweet_obj.get("topic_bucket"),
                "posted_hour": datetime.utcnow().hour,
                "hypothesis": plan.get("experiment_type") or tweet_obj.get("reasoning"),
                "format_used": tweet_obj.get("format_type"),
                "posted_at": result.get("posted_at"),
                "score": None,
            })
            circuit_breaker.record_success()
        except Exception as e:
            logger.error("Failed to log tweet to memory", phase="POSTER", error=str(e))
            # Don't fail yet - tweet posted successfully
        
        logger.info("Phase 7 COMPLETE", phase="POSTER",
                   data={"tweet_id": result.get("tweet_id")})
        return True
        
    except Exception as e:
        logger.error("Phase 7 FAILED (FATAL)", phase="POSTER", error=str(e))
        circuit_breaker.record_failure(reason="post_exception")
        return False


async def run_daily_pipeline():
    """Execute full 7-phase pipeline with error recovery."""
    start = datetime.utcnow()
    logger.info("PIPELINE_START", data={"started_at": start.isoformat()})
    
    circuit_breaker = PipelineCircuitBreaker()
    
    # Verify environment
    if not await verify_environment():
        logger.error("PIPELINE_ABORT", data={"reason": "environment_verification_failed"})
        return False
    
    try:
        # ===== NON-FATAL PHASES (1-3) =====
        await phase_1_fetch_metrics()
        await phase_2_score_mature()
        await phase_3_update_strategy()
        
        # ===== FATAL PHASES (4-7) =====
        # Phase 4: Plan
        plan = await phase_4_plan_post()
        if not plan:
            logger.error("PIPELINE_SKIP", data={"phase": 4})
            return False
        
        # Phase 5: Generate
        tweet_obj = await phase_5_generate()
        if not tweet_obj:
            logger.error("PIPELINE_SKIP", data={"phase": 5})
            return False
        
        # Phase 6: Validate
        validated = await phase_6_validate(circuit_breaker)
        if not validated:
            logger.error("PIPELINE_SKIP", data={"phase": 6})
            return False
        
        # Phase 7: Post
        posted = await phase_7_post(circuit_breaker)
        if not posted:
            logger.error("PIPELINE_SKIP", data={"phase": 7})
            return False
        
        # Success!
        end = datetime.utcnow()
        duration = (end - start).total_seconds()
        logger.info("PIPELINE_SUCCESS", 
                   data={"completed_at": end.isoformat(), "duration_seconds": duration})
        return True
        
    except Exception as e:
        logger.error("PIPELINE_FATAL", data={"error": str(e)})
        return False


def main():
    """Entry point."""
    try:
        success = asyncio.run(run_daily_pipeline())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("INTERRUPT")
        sys.exit(1)
    except Exception as e:
        logger.error("FATAL", data={"error": str(e)})
        sys.exit(1)


if __name__ == "__main__":
    main()
