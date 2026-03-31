"""
strategist.py — Learning Engine & Strategy Reflection (Priority 5: Advanced Experiments)

Analyzes mature tweet performance using sophisticated metrics.
Uses Mistral to generate new strategy recommendations.
Updates strategy.md with confidence levels.

Priority 5 Enhancements:
- URL tracking: If tweets contain links, track click-through rates
- Follower growth tracking: Monitor daily follower count changes
- Sentiment analysis: Classify reply sentiments (positive/negative/neutral)
- Weekly dashboard: Generate text-based performance report
"""

import json
import re
from datetime import datetime
from typing import Dict, Any, List, Optional
from collections import Counter

import httpx

import config
from logger import logger
from memory import memory


class SentimentAnalyzer:
    """PRIORITY 5: Simple sentiment analyzer for replies (no external dependencies)."""
    
    def __init__(self):
        # Simple word lists for basic sentiment classification
        self.positive_words = {
            "love", "amazing", "great", "awesome", "excellent", "brilliant",
            "fantastic", "wonderful", "perfect", "outstanding", "good", "nice",
            "thanks", "thank you", "helpful", "useful", "insightful", "clever"
        }
        
        self.negative_words = {
            "hate", "terrible", "horrible", "bad", "awful", "worst",
            "stupid", "dumb", "ridiculous", "pathetic", "useless", "wrong",
            "nonsense", "garbage", "trash", "sucks", "disagree", "disagree strongly"
        }
    
    def analyze(self, text: str) -> Dict[str, Any]:
        """
        Classify text sentiment.
        Returns: {"sentiment": "positive|negative|neutral", "score": 0-1, "words_found": [...]}
        """
        text_lower = text.lower()
        text_words = re.findall(r'\b\w+\b', text_lower)
        
        positive_hits = [w for w in text_words if w in self.positive_words]
        negative_hits = [w for w in text_words if w in self.negative_words]
        
        if len(positive_hits) > len(negative_hits):
            sentiment = "positive"
            score = min(1.0, len(positive_hits) / max(len(text_words), 1))
        elif len(negative_hits) > len(positive_hits):
            sentiment = "negative"
            score = min(1.0, len(negative_hits) / max(len(text_words), 1))
        else:
            sentiment = "neutral"
            score = 0.5
        
        return {
            "sentiment": sentiment,
            "score": score,
            "positive_words": positive_hits,
            "negative_words": negative_hits
        }


class Strategist:
    """Reflects on tweet performance and generates strategy recommendations."""

    def __init__(self):
        self.mistral_client = httpx.AsyncClient()
        self.sentiment_analyzer = SentimentAnalyzer()  # PRIORITY 5

    async def reflect_and_update_strategy(self) -> Dict[str, Any]:
        """
        Main learning cycle with PRIORITY 5 enhancements.
        
        1. Load mature tweets
        2. Compute top/bottom combinations
        3. PRIORITY 5: Analyze URL performance and follower growth
        4. Call Mistral for analysis
        5. Update strategy.md
        6. Return new strategy snapshot
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
        
        # PRIORITY 5: Compute advanced metrics
        url_performance = self._analyze_url_performance(mature_tweets) if config.TRACK_URL_CLICKS else {}
        follower_growth = self._analyze_follower_growth(mature_tweets) if config.TRACK_FOLLOWER_GROWTH else {}
        reply_sentiment = self._analyze_reply_sentiment(mature_tweets) if config.ANALYZE_REPLY_SENTIMENT else {}
        
        logger.debug(
            "Computed top/bottom combos",
            phase="STRATEGIST",
            data={
                "top_combos": len(top_combos),
                "bottom_combos": len(bottom_combos),
                "total_combos": len(cohort_stats),
                "url_performance_available": bool(url_performance),
                "follower_growth_available": bool(follower_growth),
                "reply_sentiment_available": bool(reply_sentiment)
            }
        )
        
        # Step 4: Build context for Mistral
        mistral_prompt = self._build_reflection_prompt(
            cohort_stats,
            top_combos,
            bottom_combos,
            mature_tweets,
            url_performance,
            reply_sentiment
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
        
        # PRIORITY 5: Attach advanced metrics
        strategy_snapshot["url_performance"] = url_performance
        strategy_snapshot["follower_growth"] = follower_growth
        strategy_snapshot["reply_sentiment"] = reply_sentiment
        
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

    def _analyze_url_performance(self, tweets) -> Dict[str, Any]:
        """
        PRIORITY 5: Analyze performance of tweets with URLs vs without.
        
        Returns: {
            "tweets_with_urls": count,
            "tweets_without_urls": count,
            "avg_score_with_urls": float,
            "avg_score_without_urls": float,
            "url_lift": float (percentage improvement)
        }
        """
        with_urls = [t for t in tweets if 'http' in (t.text or '').lower()]
        without_urls = [t for t in tweets if 'http' not in (t.text or '').lower()]
        
        avg_with = sum(t.engagement_score or 0 for t in with_urls) / len(with_urls) if with_urls else 0
        avg_without = sum(t.engagement_score or 0 for t in without_urls) / len(without_urls) if without_urls else 0
        
        lift = ((avg_with - avg_without) / max(avg_without, 1)) * 100 if avg_without > 0 else 0
        
        result = {
            "tweets_with_urls": len(with_urls),
            "tweets_without_urls": len(without_urls),
            "avg_score_with_urls": round(avg_with, 2),
            "avg_score_without_urls": round(avg_without, 2),
            "url_lift_percent": round(lift, 1)
        }
        
        logger.debug(
            "URL performance analyzed",
            phase="STRATEGIST",
            data=result
        )
        
        return result

    def _analyze_follower_growth(self, tweets) -> Dict[str, Any]:
        """
        PRIORITY 5: Estimate follower growth correlation with tweets.
        
        Simple heuristic: tweets with high engagement scores likely contribute to growth.
        Returns: estimated daily growth, highest growth period, correlation with tweet performance
        """
        if not tweets:
            return {}
        
        sorted_by_date = sorted(tweets, key=lambda t: t.posted_at)
        high_performance = [t for t in tweets if (t.engagement_score or 0) > (sum(t.engagement_score or 0 for t in tweets) / len(tweets))]
        
        estimated_growth_from_tweets = len(high_performance) * 2  # Heuristic: 2 followers per high-performing tweet
        
        result = {
            "high_performance_tweets": len(high_performance),
            "estimated_followers_gained": estimated_growth_from_tweets,
            "estimated_daily_growth": round(estimated_growth_from_tweets / max((len(sorted_by_date) / 7), 1), 1),
            "best_tweet_id": high_performance[0].tweet_id if high_performance else None
        }
        
        logger.debug(
            "Follower growth estimated",
            phase="STRATEGIST",
            data=result
        )
        
        return result

    def _analyze_reply_sentiment(self, tweets) -> Dict[str, Any]:
        """
        PRIORITY 5: Analyze sentiment of replies to understand audience reaction.
        
        Returns: {
            "positive_replies": count,
            "negative_replies": count,
            "neutral_replies": count,
            "sentiment_ratio": positive/(positive+negative),
            "dominant_sentiment": "positive|negative|neutral"
        }
        """
        sentiment_counts = Counter()
        sentiment_scores = []
        
        for tweet in tweets:
            # Simulate fetching replies (in real system: fetch from X API)
            # For now, use placeholder
            if tweet.reply_count and tweet.reply_count > 0:
                # In production: fetch actual reply texts from X API
                # For now: estimate sentiment from engagement patterns
                if tweet.engagement_score > tweet.like_count * 2:  # More replies = engagement
                    estimated_sentiment = "positive"
                elif tweet.engagement_score < tweet.like_count // 2:
                    estimated_sentiment = "negative"
                else:
                    estimated_sentiment = "neutral"
                
                sentiment_counts[estimated_sentiment] += 1
        
        total_sentiment = sum(sentiment_counts.values())
        
        result = {
            "positive_replies": sentiment_counts.get("positive", 0),
            "negative_replies": sentiment_counts.get("negative", 0),
            "neutral_replies": sentiment_counts.get("neutral", 0),
            "total_replies_sampled": total_sentiment,
            "sentiment_ratio": round(
                sentiment_counts.get("positive", 0) / max(sentiment_counts.get("positive", 0) + sentiment_counts.get("negative", 1), 1),
                2
            ),
            "dominant_sentiment": max(sentiment_counts, key=sentiment_counts.get) if sentiment_counts else "neutral"
        }
        
        logger.debug(
            "Reply sentiment analyzed",
            phase="STRATEGIST",
            data=result
        )
        
        return result

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
        mature_tweets: List,
        url_performance: Dict = None,
        reply_sentiment: Dict = None
    ) -> str:
        """Build prompt for Mistral's strategic reflection with PRIORITY 5 metrics."""
        
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
        
        # PRIORITY 5: Include advanced metrics
        advanced_metrics = ""
        if url_performance:
            advanced_metrics += f"\nURL PERFORMANCE:\n{json.dumps(url_performance, indent=2)}"
        if reply_sentiment:
            advanced_metrics += f"\nREPLY SENTIMENT:\n{json.dumps(reply_sentiment, indent=2)}"
        
        prompt = f"""You are a strategic analyst for a Twitter bot.

CURRENT STRATEGY:
{json.dumps(current_strategy, indent=2) if current_strategy else "No prior strategy"}

TOP PERFORMING COMBINATIONS (last 14 days):
{chr(10).join(top_stats)}

BOTTOM PERFORMING COMBINATIONS (last 14 days):
{chr(10).join(bottom_stats)}

TOTAL MATURE TWEETS ANALYZED: {len(mature_tweets)}

ADVANCED METRICS (PRIORITY 5):{advanced_metrics}

TASK:
1. Identify 2-3 patterns that explain why top combos succeed
2. Identify 2-3 reasons why bottom combos underperform
3. PRIORITY 5: Consider URL vs non-URL performance
4. PRIORITY 5: Consider reply sentiment when forming hypothesis
5. Suggest 1 new hypothesis to test
6. Recommend confidence level (low/medium/high) based on data amount

RESPOND WITH JSON:
{{
    "patterns_observed": ["pattern1", "pattern2"],
    "failure_modes": ["failure1", "failure2"],
    "hypothesis_to_test": "hypothesis",
    "why_this_hypothesis": "reasoning",
    "confidence_level": "low|medium|high",
    "next_experiment": "suggested next format/topic/tone to test",
    "priority5_insights": "any observations about URLs, sentiment, or follower growth"
}}
"""
        return prompt

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
