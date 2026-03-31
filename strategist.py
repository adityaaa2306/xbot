"""
strategist.py — Learning Engine & Strategy Reflection

Analyzes mature tweet performance.
Uses Mistral to generate new strategy recommendations.
Updates strategy.md with confidence levels.
"""

import json
from datetime import datetime
from typing import Dict, Any, List, Optional

import httpx

import config
from logger import logger
from memory import memory


class Strategist:
    """Reflects on tweet performance and generates strategy recommendations."""

    def __init__(self):
        self.mistral_client = httpx.AsyncClient()

    async def reflect_and_update_strategy(self) -> Dict[str, Any]:
        """
        Main learning cycle.
        
        1. Load mature tweets
        2. Compute top/bottom combinations
        3. Call Mistral for analysis
        4. Update strategy.md
        5. Return new strategy snapshot
        """
        logger.info("Starting strategy reflection", phase="STRATEGIST")
        
        # Step 1: Load mature tweets
        mature_tweets = memory.load_mature_tweets()
        
        if not mature_tweets:
            logger.warn(
                "No mature tweets to analyze",
                phase="STRATEGIST"
            )
            return None
        
        # Step 2: Compute statistics by (format, topic, tone)
        cohort_stats = self._compute_cohort_stats(mature_tweets)
        
        # Step 3: Identify top and bottom performers
        top_combos = self._identify_top_combinations(cohort_stats, k=3)
        bottom_combos = self._identify_bottom_combinations(cohort_stats, k=3)
        
        logger.debug(
            "Computed top/bottom combos",
            phase="STRATEGIST",
            data={
                "top_combos": len(top_combos),
                "bottom_combos": len(bottom_combos),
                "total_combos": len(cohort_stats)
            }
        )
        
        # Step 4: Build context for Mistral
        mistral_prompt = self._build_reflection_prompt(
            cohort_stats,
            top_combos,
            bottom_combos,
            mature_tweets
        )
        
        # Step 5: Call Mistral
        try:
            reflection = await self._call_mistral(mistral_prompt)
        except Exception as e:
            logger.error(
                f"Mistral reflection failed: {str(e)}",
                phase="STRATEGIST",
                error=str(e)
            )
            reflection = self._default_strategy(top_combos, bottom_combos)
        
        # Step 6: Parse response
        strategy_snapshot = self._parse_mistral_response(reflection)
        
        # Step 7: Determine confidence level
        confidence_level = self._compute_confidence_level(
            len(mature_tweets),
            cohort_stats
        )
        strategy_snapshot["confidence_level"] = confidence_level
        
        # Step 8: Save strategy snapshot
        memory.save_strategy(strategy_snapshot)
        
        logger.info(
            "Strategy reflection complete",
            phase="STRATEGIST",
            data={
                "confidence": confidence_level,
                "top_format": strategy_snapshot.get("top_formats", [None])[0] if strategy_snapshot.get("top_formats") else None
            }
        )
        
        return strategy_snapshot

    def _compute_cohort_stats(self, tweets) -> Dict[tuple, Dict[str, Any]]:
        """
        Group tweets by (format, topic, tone).
        Compute avg score and engagement stats per group.
        """
        cohorts = {}
        
        for tweet in tweets:
            key = (tweet.format_type, tweet.topic_bucket, tweet.tone)
            
            if key not in cohorts:
                cohorts[key] = {
                    "tweets": [],
                    "scores": [],
                    "impressions": [],
                    "likes": [],
                    "retweets": [],
                    "replies": [],
                    "quote_tweets": []
                }
            
            cohorts[key]["tweets"].append(tweet)
            cohorts[key]["scores"].append(tweet.engagement_score or 0)
            
            if tweet.metrics:
                cohorts[key]["impressions"].append(tweet.metrics.impressions)
                cohorts[key]["likes"].append(tweet.metrics.likes)
                cohorts[key]["retweets"].append(tweet.metrics.retweets)
                cohorts[key]["replies"].append(tweet.metrics.replies)
                cohorts[key]["quote_tweets"].append(tweet.metrics.quote_tweets)
        
        # Compute averages
        for key, data in cohorts.items():
            data["avg_score"] = sum(data["scores"]) / len(data["scores"]) if data["scores"] else 0
            data["avg_impressions"] = sum(data["impressions"]) / len(data["impressions"]) if data["impressions"] else 0
            data["avg_likes"] = sum(data["likes"]) / len(data["likes"]) if data["likes"] else 0
            data["avg_retweets"] = sum(data["retweets"]) / len(data["retweets"]) if data["retweets"] else 0
            data["avg_replies"] = sum(data["replies"]) / len(data["replies"]) if data["replies"] else 0
            data["avg_quote_tweets"] = sum(data["quote_tweets"]) / len(data["quote_tweets"]) if data["quote_tweets"] else 0
            data["n_tweets"] = len(data["tweets"])
        
        return cohorts

    def _identify_top_combinations(self, cohorts: Dict, k: int = 3) -> List[tuple]:
        """Return top k (format, topic, tone) combinations by avg score."""
        sorted_combos = sorted(
            cohorts.items(),
            key=lambda x: x[1]["avg_score"],
            reverse=True
        )
        return [combo[0] for combo in sorted_combos[:k]]

    def _identify_bottom_combinations(self, cohorts: Dict, k: int = 3) -> List[tuple]:
        """Return bottom k (format, topic, tone) combinations by avg score."""
        sorted_combos = sorted(
            cohorts.items(),
            key=lambda x: x[1]["avg_score"]
        )
        return [combo[0] for combo in sorted_combos[:k]]

    def _build_reflection_prompt(
        self,
        cohorts: Dict,
        top_combos: List[tuple],
        bottom_combos: List[tuple],
        mature_tweets: List
    ) -> str:
        """Build prompt for Mistral's strategic reflection."""
        
        # Load current strategy for context
        current_strategy = memory.load_latest_strategy()
        
        top_stats = []
        for combo in top_combos:
            stats = cohorts[combo]
            top_stats.append(
                f"- Format: {combo[0]}, Topic: {combo[1]}, Tone: {combo[2]} "
                f"(avg_score: {stats['avg_score']:.0f}, n={stats['n_tweets']})"
            )
        
        bottom_stats = []
        for combo in bottom_combos:
            stats = cohorts[combo]
            bottom_stats.append(
                f"- Format: {combo[0]}, Topic: {combo[1]}, Tone: {combo[2]} "
                f"(avg_score: {stats['avg_score']:.0f}, n={stats['n_tweets']})"
            )
        
        prompt = f"""You are a strategic analyst for a Twitter bot.

CURRENT STRATEGY:
{json.dumps(current_strategy, indent=2) if current_strategy else "No prior strategy"}

TOP PERFORMING COMBINATIONS (last 14 days):
{chr(10).join(top_stats)}

BOTTOM PERFORMING COMBINATIONS (last 14 days):
{chr(10).join(bottom_stats)}

TOTAL MATURE TWEETS ANALYZED: {len(mature_tweets)}

TASK:
1. Identify 2-3 patterns that explain why top combos succeed
2. Identify 2-3 reasons why bottom combos underperform
3. Suggest 1 new hypothesis to test
4. Recommend confidence level (low/medium/high) based on data amount

RESPOND WITH JSON:
{{
    "patterns_observed": ["pattern1", "pattern2"],
    "failure_modes": ["failure1", "failure2"],
    "hypothesis_to_test": "hypothesis",
    "why_this_hypothesis": "reasoning",
    "confidence_level": "low|medium|high",
    "next_experiment": "suggested next format/topic/tone to test"
}}
"""
        return prompt

    async def _call_mistral(self, prompt: str) -> str:
        """Call Mistral API for strategic reflection."""
        
        payload = {
            "model": "mistralai/mistral-large-3-675b-instruct-v0.1",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 1024
        }
        
        headers = {
            "Authorization": f"Bearer {config.NVIDIA_API_KEY}",
            "Content-Type": "application/json"
        }
        
        try:
            response = await self.mistral_client.post(
                config.NVIDIA_ENDPOINT,
                json=payload,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(
                f"Mistral API error: {str(e)}",
                phase="STRATEGIST",
                error=str(e)
            )
            raise

    def _parse_mistral_response(self, response_text: str) -> Dict[str, Any]:
        """Parse Mistral's JSON response."""
        try:
            # Extract JSON from response
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = json.loads(response_text)
            
            return {
                "date": datetime.utcnow().isoformat(),
                "version": 1,
                "patterns_observed": data.get("patterns_observed", []),
                "failure_modes": data.get("failure_modes", []),
                "hypothesis_to_test": data.get("hypothesis_to_test", ""),
                "why_this_hypothesis": data.get("why_this_hypothesis", ""),
                "next_experiment": data.get("next_experiment", ""),
                "reasoning": data.get("why_this_hypothesis", "")
            }
        except Exception as e:
            logger.error(
                f"Failed to parse Mistral response: {str(e)}",
                phase="STRATEGIST",
                error=str(e)
            )
            return self._default_strategy([], [])

    def _default_strategy(self, top_combos: List, bottom_combos: List) -> Dict[str, Any]:
        """Fallback strategy when Mistral is unavailable."""
        return {
            "date": datetime.utcnow().isoformat(),
            "version": 1,
            "patterns_observed": ["Insufficient data for analysis"],
            "failure_modes": ["System unavailable"],
            "hypothesis_to_test": "Continue exploration",
            "why_this_hypothesis": "Not enough data to form hypothesis",
            "next_experiment": "Systematic rotation of all formats",
            "reasoning": "Fallback strategy"
        }

    def _compute_confidence_level(self, n_mature: int, cohorts: Dict) -> str:
        """
        Determine confidence level based on data maturity and coverage.
        
        low: <20 mature tweets or <3 cohorts
        medium: 20-100 mature tweets, 3-10 cohorts
        high: >100 mature tweets, >10 cohorts with n>2 each
        """
        n_cohorts = len(cohorts)
        well_tested = sum(1 for c in cohorts.values() if c["n_tweets"] >= 3)
        
        if n_mature < 20 or n_cohorts < 3:
            return "low"
        elif n_mature > 100 and well_tested > 10:
            return "high"
        else:
            return "medium"


# Global strategist instance
strategist = Strategist()
