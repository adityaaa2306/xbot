"""
main.py — Production-Grade Daily Pipeline Orchestrator

7-Phase Daily Workflow:
1. FETCH:      Fetch metrics for all pending tweets (2h, 24h, 72h windows)
2. SCORE:      Score mature tweets (48h+), detect pattern decay
3. STRATEGIST: Reflect on data, update strategy.md with LLM insights
4. PLAN:       Decide exploit vs explore for today's post
5. GENERATOR:  Generate tweet/thread using Mistral LLM
6. VALIDATOR:  Quality gate (11 checks), duplicate detection
7. POSTER:     Post to X API, log experiment for learning

Design Principles:
- Async/await for I/O operations
- No silent failures (all errors logged)
- Graceful degradation (Phase 7 failure doesn't crash)
- Structured logging (JSON to both stdout + JSONL files)
- Memory persistence (all state survives crashes)
"""

import asyncio
import json
import os
import sys
from datetime import datetime

import config
from logger import logger
from memory import memory
from fetcher import fetcher
from scorer import scorer
from validator import validator
from experimenter import experimenter
from strategist import strategist
from generator import generate_tweet
from poster import post_tweet


async def verify_environment() -> bool:
    """Verify all credentials and directories."""
    logger.info("Verifying environment", event="STARTUP", data={})
    
    required_vars = ["NVIDIA_API_KEY", "X_API_KEY", "X_API_SECRET", 
                     "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET", "X_BEARER_TOKEN"]
    missing = [v for v in required_vars if not os.getenv(v)]
    
    if missing:
        logger.error("Missing environment variables", event="STARTUP", data={"missing": missing})
        return False
    
    for directory in ["logs", "memory", "data"]:
        os.makedirs(directory, exist_ok=True)
    
    logger.info("Environment verified", event="STARTUP", data={})
    return True


async def phase_1_fetch_metrics() -> bool:
    """Phase 1: Fetch metrics for pending tweets."""
    try:
        logger.info("Phase 1 START", phase="FETCH", data={})
        
        pending = memory.get_recent_tweets(days=3, limit=100)
        if not pending:
            logger.info("Phase 1 SKIP", phase="FETCH", data={"reason": "no_pending"})
            return True
        
        updated = await fetcher.fetch_all_pending(pending)
        logger.info("Phase 1 COMPLETE", phase="FETCH", data={"updated": updated})
        return True
        
    except Exception as e:
        logger.error("Phase 1 FAILED", phase="FETCH", error=str(e))
        return False


async def phase_2_score_mature() -> bool:
    """Phase 2: Score mature tweets."""
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
                memory.update_score(tweet["tweet_id"], score)
                scored += 1
            except Exception as e:
                logger.warn(f"Score failed for {tweet.get('tweet_id')}", phase="SCORE", error=str(e))
        
        logger.info("Phase 2 COMPLETE", phase="SCORE", data={"scored": scored})
        return True
        
    except Exception as e:
        logger.error("Phase 2 FAILED", phase="SCORE", error=str(e))
        return False


async def phase_3_update_strategy() -> bool:
    """Phase 3: Update strategy with LLM reflection."""
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
        return True


async def phase_4_plan_post() -> bool:
    """Phase 4: Plan today's post (exploit vs explore)."""
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
        return True
        
    except Exception as e:
        logger.error("Phase 4 FAILED", phase="EXPERIMENTER", error=str(e))
        return False


async def phase_5_generate() -> bool:
    """Phase 5: Generate tweet with LLM."""
    try:
        logger.info("Phase 5 START", phase="GENERATOR", data={})
        
        with open("data/todays_plan.json", "r") as f:
            plan = json.load(f)
        
        tweet_obj = await generate_tweet(
            archetype=plan.get("format_type"),
            topic=plan.get("topic_bucket"),
            thread_length=plan.get("thread_length", 1),
            is_experiment=plan.get("is_experiment", False)
        )
        
        if not tweet_obj:
            logger.error("Phase 5 FAILED", phase="GENERATOR", error="generation_returned_none")
            return False
        
        with open("data/generated_tweet.json", "w") as f:
            json.dump(tweet_obj, f)
        
        logger.info("Phase 5 COMPLETE", phase="GENERATOR",
                   data={"thread_length": tweet_obj.get("thread_length", 1)})
        return True
        
    except Exception as e:
        logger.error("Phase 5 FAILED", phase="GENERATOR", error=str(e))
        return False


async def phase_6_validate() -> bool:
    """Phase 6: Validate tweet quality."""
    try:
        logger.info("Phase 6 START", phase="VALIDATOR", data={})
        
        with open("data/generated_tweet.json", "r") as f:
            tweet_obj = json.load(f)
        
        result = validator.validate_tweet(tweet_obj)
        
        if not result["valid"]:
            logger.error("Phase 6 FAILED", phase="VALIDATOR",
                        data={"failures": result.get("failures", [])})
            return False
        
        if result.get("warnings"):
            logger.warn("Phase 6 warnings", phase="VALIDATOR",
                       data={"warnings": result.get("warnings", [])})
        
        logger.info("Phase 6 COMPLETE", phase="VALIDATOR", data={})
        return True
        
    except Exception as e:
        logger.error("Phase 6 FAILED", phase="VALIDATOR", error=str(e))
        return False


async def phase_7_post() -> bool:
    """Phase 7: Post to X."""
    try:
        logger.info("Phase 7 START", phase="POSTER", data={})
        
        with open("data/generated_tweet.json", "r") as f:
            tweet_obj = json.load(f)
        
        with open("data/todays_plan.json", "r") as f:
            plan = json.load(f)
        
        result = await post_tweet(tweet_obj)
        
        if not result:
            logger.error("Phase 7 FAILED", phase="POSTER", error="posting_returned_none")
            return False
        
        # Log to memory
        memory.add_tweet_to_log(tweet_obj, result, plan)
        
        logger.info("Phase 7 COMPLETE", phase="POSTER",
                   data={"tweet_id": result.get("tweet_id")})
        return True
        
    except Exception as e:
        logger.error("Phase 7 FAILED", phase="POSTER", error=str(e))
        return False


async def run_daily_pipeline():
    """Execute full 7-phase pipeline."""
    start = datetime.utcnow()
    logger.info("=== XBOT DAILY PIPELINE START ===", event="PIPELINE_START", 
               data={"started_at": start.isoformat()})
    
    # Verify environment
    if not await verify_environment():
        logger.error("Environment verification failed", event="PIPELINE_ABORT")
        return False
    
    # Execute phases with error handling
    phases = [
        ("FETCH", phase_1_fetch_metrics),
        ("SCORE", phase_2_score_mature),
        ("STRATEGIST", phase_3_update_strategy),
        ("EXPERIMENTER", phase_4_plan_post),
        ("GENERATOR", phase_5_generate),
        ("VALIDATOR", phase_6_validate),
        ("POSTER", phase_7_post)
    ]
    
    results = {}
    for phase_name, phase_func in phases:
        success = await phase_func()
        results[phase_name] = "PASS" if success else "FAIL"
        
        # Fatal phases abort if they fail
        if not success and phase_name in ["EXPERIMENTER", "GENERATOR", "VALIDATOR", "POSTER"]:
            logger.error(f"Fatal phase {phase_name} failed, aborting pipeline", event="PIPELINE_ABORT")
            break
    
    # Summary
    end = datetime.utcnow()
    duration = (end - start).total_seconds()
    passed = sum(1 for v in results.values() if v == "PASS")
    
    logger.info("=== XBOT DAILY PIPELINE END ===", event="PIPELINE_END",
               data={
                   "completed_at": end.isoformat(),
                   "duration_seconds": duration,
                   "phases_passed": passed,
                   "total_phases": len(phases),
                   "results": results
               })
    
    return all(v == "PASS" for v in results.values())


def main():
    """Entry point."""
    try:
        loop = asyncio.get_event_loop()
        success = loop.run_until_complete(run_daily_pipeline())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("Pipeline interrupted by user", event="INTERRUPT")
        sys.exit(1)
    except Exception as e:
        logger.error("Unhandled exception in main", event="FATAL", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
