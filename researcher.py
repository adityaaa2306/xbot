"""
researcher.py — Main Autonomous Research Loop

Orchestrates the complete workflow: score past tweets, reflect on strategy,
generate new tweet, post it, and log the experiment. Runs daily.
"""

import os
import json
import random
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict, Counter

import requests
from dotenv import load_dotenv

# Import from local modules
from poster import post_tweet, append_experiment
from generator import generate_tweet
from scorer import EngagementScorer

# Helper function for reading files
def read_file(path: str) -> str:
    """Read file contents."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return f"(File not found: {path})"
    except Exception as e:
        return f"(Error reading file: {str(e)})"

# Load environment variables
load_dotenv()

# Configure NVIDIA API
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
INVOKE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL_NAME = "mistralai/mistral-large-3-675b-instruct-2512"


def score_pending_experiments() -> int:
    """
    Score all mature experiments (48h+ old engagement data).
    
    Uses maturity gating to ensure only tweets with sufficient engagement data
    are scored. Returns count of newly scored tweets.
    
    Returns:
        int: Number of tweets scored in this run
    """
    try:
        scorer = EngagementScorer()
        return scorer.score_all_mature()
    except Exception as e:
        from logger import logger
        logger.error(
            f"Failed to score pending experiments: {str(e)}",
            phase="SCORE_PENDING",
            error=str(e)
        )
        return 0


def reflect_and_update_strategy(
    niche_path: str = "config/niche.md",
    strategy_path: str = "strategy.md",
    experiments_path: str = "data/experiments.jsonl"
) -> Optional[str]:
    """
    Analyze experiment results and autonomously update strategy.md.
    
    Reads the bot's niche, current strategy, and full experiment history.
    Uses LATEST scores (not initial 24-hour scores) for more mature engagement data.
    Prompts Mistral to identify high-scoring formats, patterns, and recommend
    the next hypothesis to test. Rewrites strategy.md with the analysis.
    
    Args:
        niche_path (str): Path to config/niche.md
        strategy_path (str): Path to strategy.md
        experiments_path (str): Path to data/experiments.jsonl
        
    Returns:
        str: The new strategy content written to file, or None if update failed
        
    Note:
        - Uses latest scores from score_history for mature engagement
        - Errors are logged but do not raise exceptions.
    """
    try:
        # Read context
        niche_content = read_file(niche_path)
        strategy_content = read_file(strategy_path)
        
        # Read all experiments (latest scores are already in "score" field)
        experiments_content = ""
        if os.path.exists(experiments_path):
            with open(experiments_path, "r", encoding="utf-8") as f:
                experiments_content = f.read()
        
        if not experiments_content:
            experiments_content = "(No experiments yet)"
        
        # Build prompt for NVIDIA API
        prompt = f"""You are an AI research analyst for an autonomous X bot. Your job is to analyze past experiments and update the bot's strategy.

BOT NICHE & IDENTITY:
{niche_content}

CURRENT STRATEGY:
{strategy_content}

EXPERIMENT RESULTS (JSONL format — note: "score" field contains LATEST score, score_history shows progression):
{experiments_content}

Analyze the experiment results:
1. Which formats/hypotheses scored highest? Calculate average scores using LATEST scores.
2. What patterns do you see? What worked? What failed?
3. Based on the data, what format should we test next?
4. Update the "Current Best Formats" table with latest scores
5. Update the "Performance Trends" section noting which are STABLE vs DECLINING
6. Update the "Active Hypothesis" section with the next experiment to run
7. Add today's posts to "Experiment History"
8. Move any consistently low-scoring formats to "Discarded Approaches"

Output ONLY the complete, updated strategy.md content in markdown format. No preamble, no explanations—just the raw markdown text that should be saved to the file."""
        
        # Call NVIDIA API
        headers = {
            "Authorization": f"Bearer {NVIDIA_API_KEY}",
            "Accept": "application/json"
        }
        
        payload = {
            "model": MODEL_NAME,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2048,
            "temperature": 0.15,
            "top_p": 1.00,
            "frequency_penalty": 0.00,
            "presence_penalty": 0.00,
            "stream": False
        }
        
        response = requests.post(INVOKE_URL, headers=headers, json=payload)
        response.raise_for_status()
        
        result = response.json()
        
        if not result.get("choices"):
            print("⚠️  Empty response from NVIDIA API during strategy reflection")
            return None
        
        new_strategy = result["choices"][0]["message"]["content"].strip()
        
        # Write to file
        with open(strategy_path, "w", encoding="utf-8") as f:
            f.write(new_strategy)
        
        print(f"✅ Strategy updated and saved to {strategy_path}")
        return new_strategy
        
    except requests.RequestException as e:
        print(f"❌ Error updating strategy (API request failed): {str(e)}")
        return None
    except Exception as e:
        print(f"❌ Error updating strategy: {str(e)}")
        return None


def decide_thread_length(experiments_path: str = "data/experiments.jsonl") -> int:
    """
    Decide what thread length to use for the next post.
    
    Strategy:
    - 60% chance: Use length with highest avg score (exploit)
    - 25% chance: Use length not tested in last 7 days (explore)
    - 15% chance: Random length 1-7 (wildcard)
    
    Args:
        experiments_path (str): Path to experiments.jsonl
        
    Returns:
        int: Chosen thread length (1-7)
    """
    thread_scores = defaultdict(list)
    thread_dates = defaultdict(list)
    
    if os.path.exists(experiments_path):
        with open(experiments_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        record = json.loads(line)
                        length = record.get("thread_length", 1)
                        score = record.get("score")
                        posted_at = record.get("posted_at")
                        
                        if score is not None:
                            thread_scores[length].append(score)
                        
                        if posted_at:
                            posted_dt = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
                            thread_dates[length].append(posted_dt)
                    except json.JSONDecodeError:
                        continue
    
    # Calculate best length by avg score
    best_length = 1
    best_score = 0
    for length, scores in thread_scores.items():
        if scores:
            avg = sum(scores) / len(scores)
            if avg > best_score:
                best_score = avg
                best_length = length
    
    # Find untested/under-tested lengths
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    untested_lengths = []
    
    for length in range(1, 8):
        dates = thread_dates.get(length, [])
        recent_uses = [d for d in dates if d > week_ago]
        
        if len(recent_uses) == 0:
            untested_lengths.append(length)
    
    # Make weighted decision
    rand_val = random.random()
    
    if rand_val < 0.60:
        chosen_length = best_length
        reason = f"Exploit: {best_length}-piece has avg score {best_score:.1f}"
    elif rand_val < 0.85 and untested_lengths:
        chosen_length = random.choice(untested_lengths)
        reason = f"Explore: Testing {chosen_length}-piece (not tried in 7 days)"
    else:
        chosen_length = random.randint(1, 7)
        reason = f"Wildcard: Random {chosen_length}-piece thread"
    
    print(f"📊 Thread length: {chosen_length} ({reason})")
    return chosen_length


def decide_topic(experiments_path: str = "data/experiments.jsonl") -> str:
    """
    Decide what topic to cover for the next post.
    
    Strategy:
    - 65% chance: Use topic with highest avg score (exploit)
    - 25% chance: Use topic not tested in 7 days (explore)
    - 10% chance: Random topic (wildcard)
    
    Args:
        experiments_path (str): Path to experiments.jsonl
        
    Returns:
        str: Chosen topic
    """
    topic_scores = defaultdict(list)
    topic_dates = defaultdict(list)
    
    # List of available topics (from niche.md)
    available_topics = [
        "ML Trends", "AI Safety", "Code Tips", "Industry News",
        "Research", "Tools", "Strategy", "Beginner Tips"
    ]
    
    if os.path.exists(experiments_path):
        with open(experiments_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        record = json.loads(line)
                        topic = record.get("topic", "Unknown")
                        score = record.get("score")
                        posted_at = record.get("posted_at")
                        
                        if score is not None:
                            topic_scores[topic].append(score)
                        if posted_at:
                            posted_dt = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
                            topic_dates[topic].append(posted_dt)
                    except json.JSONDecodeError:
                        continue
    
    # Calculate best topic
    best_topic = available_topics[0]
    best_score = 0
    for topic, scores in topic_scores.items():
        if scores:
            avg = sum(scores) / len(scores)
            if avg > best_score:
                best_score = avg
                best_topic = topic
    
    # Find untested topics
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    untested = []
    
    for topic in available_topics:
        dates = topic_dates.get(topic, [])
        recent = [d for d in dates if d > week_ago]
        if len(recent) == 0:
            untested.append(topic)
    
    # Weighted decision
    rand_val = random.random()
    
    if rand_val < 0.65:
        chosen = best_topic
        reason = f"Exploit: {best_topic} scores {best_score:.0f}pts"
    elif rand_val < 0.90 and untested:
        chosen = random.choice(untested)
        reason = f"Explore: Testing {chosen} (not tried in 7 days)"
    else:
        chosen = random.choice(available_topics)
        reason = f"Wildcard: Random topic {chosen}"
    
    print(f"📚 Topic: {chosen} ({reason})")
    return chosen


def decide_posting_time(experiments_path="data/experiments.jsonl") -> int:
    """
    Decide if we should post now and what hour we're posting at.
    
    Returns the current UTC hour (0-23), and analyzes which hours historically
    get the best engagement. Over time, the bot learns patterns like:
    - "8 AM UTC gets 2x more engagement than 3 AM"
    - "Posts at 6 PM get more replies than likes"
    
    Strategy:
    - Always posts at the requested time (since GitHub Actions schedules it)
    - But tracks which hour gets best scores
    - Returns current UTC hour for logging
    """
    now = datetime.utcnow()
    current_hour = now.hour
    
    # Analyze historical performance by hour
    hour_scores = defaultdict(list)  # hour -> [scores]
    
    if os.path.exists(experiments_path):
        with open(experiments_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    record = json.loads(line)
                    if record.get("posted_hour") is not None and record.get("score") is not None:
                        hour = record["posted_hour"]
                        score = record["score"]
                        hour_scores[hour].append(score)
    
    # Calculate best hour
    if hour_scores:
        best_hour = max(hour_scores.items(), key=lambda x: sum(x[1]) / len(x[1]))[0]
        best_avg = sum(hour_scores[best_hour]) / len(hour_scores[best_hour])
        print(f"⏰ Best posting hour historically: {best_hour:02d}:00 UTC (avg score: {best_avg:.0f})")
    
    return current_hour


def decide_archetype(experiments_path="data/experiments.jsonl"):
    """
    Decide which tweet archetype to use next.
    
    Strategy:
    - 65% chance: Use archetype with highest avg score (exploit)
    - 25% chance: Use archetype not tested in 7 days (explore)
    - 10% chance: Random archetype (wildcard)
    """
    archetypes = [
        "The Controversial Opinion",
        "The Pattern Interrupt",
        "The Brutal Truth",
        "The Insight Bomb",
        "The Debate Starter",
        "The Trend Translation",
        "The Founder Confession",
        "The Data Drop",
        "The Contrarian Reversal",
        "The Thread Bait"
    ]
    
    arch_scores = defaultdict(list)
    arch_dates = defaultdict(list)
    
    if os.path.exists(experiments_path):
        with open(experiments_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        record = json.loads(line)
                        archetype = record.get("archetype", "Unknown")
                        score = record.get("score")
                        posted_at = record.get("posted_at")
                        
                        if score is not None:
                            arch_scores[archetype].append(score)
                        if posted_at:
                            posted_dt = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
                            arch_dates[archetype].append(posted_dt)
                    except json.JSONDecodeError:
                        continue
    
    best_arch = archetypes[0]
    best_score = 0
    for arch, scores in arch_scores.items():
        if scores:
            avg = sum(scores) / len(scores)
            if avg > best_score:
                best_score = avg
                best_arch = arch
    
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    untested = []
    
    for arch in archetypes:
        dates = arch_dates.get(arch, [])
        recent = [d for d in dates if d > week_ago]
        if len(recent) == 0:
            untested.append(arch)
    
    rand_val = random.random()
    
    if rand_val < 0.65:
        chosen = best_arch
        reason = f"Exploit: {best_arch} scores {best_score:.0f}pts"
    elif rand_val < 0.90 and untested:
        chosen = random.choice(untested)
        reason = f"Explore: Testing {chosen} (not tried in 7 days)"
    else:
        chosen = random.choice(archetypes)
        reason = f"Wildcard: Random archetype {chosen}"
    
    print(f"🎭 Archetype: {chosen} ({reason})")
    return chosen


def enforce_diversity_quota(experiments_path: str = "data/experiments.jsonl") -> dict:
    """
    Check if we're violating diversity quota in the last 7 days.
    
    Diversity rules:
    - Max 2 posts with same archetype per 7 days
    - Max 2 posts with same topic per 7 days
    - Max 2 posts at same hour per 7 days
    - Max 3 posts with same thread length per 7 days
    
    Returns:
        dict: {"violates": bool, "element_type": str, "element": str}
    """
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    
    archetype_counts = Counter()
    topic_counts = Counter()
    hour_counts = Counter()
    thread_counts = Counter()
    
    if os.path.exists(experiments_path):
        with open(experiments_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        record = json.loads(line)
                        posted_at_str = record.get("posted_at")
                        
                        if not posted_at_str:
                            continue
                        
                        posted_at = datetime.fromisoformat(posted_at_str.replace("Z", "+00:00"))
                        
                        if posted_at > week_ago:
                            archetype_counts[record.get("archetype")] += 1
                            topic_counts[record.get("topic")] += 1
                            hour_counts[record.get("posted_hour")] += 1
                            thread_counts[record.get("thread_length")] += 1
                    except:
                        continue
    
    # Check violations
    if max(archetype_counts.values() or [0]) >= 2:
        over_archetype = [a for a, c in archetype_counts.items() if c >= 2][0]
        print(f"🟡 Diversity warning: {over_archetype} already posted 2x this week")
        return {"violates": True, "element_type": "archetype", "element": over_archetype}
    
    if max(topic_counts.values() or [0]) >= 2:
        over_topic = [t for t, c in topic_counts.items() if c >= 2][0]
        print(f"🟡 Diversity warning: {over_topic} already posted 2x this week")
        return {"violates": True, "element_type": "topic", "element": over_topic}
    
    if max(hour_counts.values() or [0]) >= 2:
        over_hour = [h for h, c in hour_counts.items() if c >= 2][0]
        print(f"🟡 Diversity warning: Hour {over_hour:02d}:00 already used 2x this week")
        return {"violates": True, "element_type": "posted_hour", "element": over_hour}
    
    if max(thread_counts.values() or [0]) >= 3:
        over_length = [l for l, c in thread_counts.items() if c >= 3][0]
        print(f"🟡 Diversity warning: {over_length}-piece threads already posted 3x this week")
        return {"violates": True, "element_type": "thread_length", "element": over_length}
    
    return {"violates": False}


def should_test_opposite(experiments_path: str = "data/experiments.jsonl") -> bool:
    """
    Every 5 posts, force testing the opposite of what's working best.
    
    This prevents convergence by deliberately testing contrarian strategies.
    
    Returns:
        bool: True if we should force opposite test
    """
    if not os.path.exists(experiments_path):
        return False
    
    with open(experiments_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    post_count = len([l for l in lines if l.strip()])
    return post_count > 0 and post_count % 5 == 0


def get_novelty_boost(archetype: str, topic: str, thread_length: int, posted_hour: int, 
                      experiments_path: str = "data/experiments.jsonl") -> float:
    """
    Calculate novelty bonus for a specific combination.
    
    Rewards unexplored combinations:
    - Never tried this exact combo: +50%
    - Tried 30+ days ago: +30%
    - Tried 14-30 days ago: +15%
    - Tried <14 days ago: 0%
    
    Args:
        archetype, topic, thread_length, posted_hour: Elements of the combo
        experiments_path: Path to experiments.jsonl
        
    Returns:
        float: Novelty bonus multiplier (1.0 = no bonus, 1.50 = +50% bonus)
    """
    now = datetime.utcnow()
    cutoff_30 = now - timedelta(days=30)
    cutoff_14 = now - timedelta(days=14)
    
    never_tried = True
    oldest_use = None
    
    if os.path.exists(experiments_path):
        with open(experiments_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        record = json.loads(line)
                        if (record.get("archetype") == archetype and
                            record.get("topic") == topic and
                            record.get("thread_length") == thread_length and
                            record.get("posted_hour") == posted_hour):
                            
                            never_tried = False
                            posted_at = datetime.fromisoformat(record.get("posted_at", "").replace("Z", "+00:00"))
                            
                            if oldest_use is None or posted_at < oldest_use:
                                oldest_use = posted_at
                    except:
                        continue
    
    if never_tried:
        print(f"   ✨ Novelty bonus +50% (never tested this combo before!)")
        return 1.50
    elif oldest_use and oldest_use < cutoff_30:
        print(f"   ✨ Novelty bonus +30% (last tested 30+ days ago)")
        return 1.30
    elif oldest_use and oldest_use < cutoff_14:
        print(f"   ✨ Novelty bonus +15% (last tested 14-30 days ago)")
        return 1.15
    
    return 1.0


def check_declining_strategies(experiments_path: str = "data/experiments.jsonl") -> dict:
    """
    Detect which strategies are declining in performance.
    
    Returns:
        dict: {element_type: [declining_elements]}
    """
    declining = {
        "archetype": [],
        "topic": [],
        "posted_hour": [],
        "thread_length": []
    }
    
    # Get unique elements from experiments
    archetypes = set()
    topics = set()
    hours = set()
    lengths = set()
    
    if os.path.exists(experiments_path):
        with open(experiments_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        record = json.loads(line)
                        archetypes.add(record.get("archetype"))
                        topics.add(record.get("topic"))
                        hours.add(record.get("posted_hour"))
                        lengths.add(record.get("thread_length"))
                    except:
                        continue
    
    # Check each element for decline
    for arch in archetypes:
        if arch and arch != "Unknown":
            result = detect_declining_strategy(arch, "archetype", experiments_path)
            if result.get("is_declining"):
                declining["archetype"].append(arch)
    
    for topic in topics:
        if topic and topic != "Unknown":
            result = detect_declining_strategy(topic, "topic", experiments_path)
            if result.get("is_declining"):
                declining["topic"].append(topic)
    
    for hour in hours:
        if hour is not None:
            result = detect_declining_strategy(str(hour), "posted_hour", experiments_path)
            if result.get("is_declining"):
                declining["posted_hour"].append(hour)
    
    for length in lengths:
        if length is not None:
            result = detect_declining_strategy(str(length), "thread_length", experiments_path)
            if result.get("is_declining"):
                declining["thread_length"].append(length)
    
    return declining


def get_strategy_mode(experiments_path: str = "data/experiments.jsonl") -> str:
    """
    Determine which strategy mode to use for this post.
    
    Modes:
    - "pivot_mode": If current best is declining
    - "diversity_mode": If diversity quota violated
    - "contrarian_mode": Every 5 posts, test opposite
    - "normal_mode": Regular 50% exploit / 30% explore / 20% wildcard
    
    Returns:
        str: Strategy mode to use
    """
    # Check for pivoting need
    declining = check_declining_strategies(experiments_path)
    if any(declining.values()):
        print("🔄 PIVOT MODE: Recent strategies declining, shifting alternatives")
        return "pivot_mode"
    
    # Check diversity quota
    diversity_check = enforce_diversity_quota(experiments_path)
    if diversity_check.get("violates"):
        print("🎯 DIVERSITY MODE: Enforcing feed variety")
        return "diversity_mode"
    
    # Check for contrarian test
    if should_test_opposite(experiments_path):
        print("⚡ CONTRARIAN MODE: Testing opposite of current best")
        return "contrarian_mode"
    
    print("✅ NORMAL MODE: Regular exploit/explore balance")
    return "normal_mode"


def run_daily_loop(num_posts: int = None) -> None:
    """
    Execute one or more cycles of the autonomous research loop.
    
    Posts 1-3 content pieces dynamically in each run (each could be a single tweet or thread).
    Each piece can have different thread lengths and topics.
    
    Args:
        num_posts (int): Number of posts to make this cycle (1-3). If None, decides randomly: usually 1-2.
    
    Steps per post:
    1. Decide thread length and topic
    2. Generate content
    3. Post to X
    4. Log experiment
    
    Reflection and scoring happen once per cycle (before posts).
    Each post is wrapped in try/except so failures don't halt the entire loop.
    """
    
    start_time = datetime.utcnow()
    
    # Decide how many posts to make (1-3, but usually 1-2)
    if num_posts is None:
        rand_val = random.random()
        if rand_val < 0.70:
            num_posts = 1
        elif rand_val < 0.95:
            num_posts = 2
        else:
            num_posts = 3
    else:
        num_posts = min(max(num_posts, 1), 3)  # Clamp to 1-3
    
    print("\n" + "="*70)
    print("🤖 AUTOBOT RESEARCH LOOP")
    print(f"⏰ Started: {start_time.isoformat()}Z")
    print(f"📊 Plan: {num_posts} content piece(s) (mix of single tweets and threads)")
    print("="*70 + "\n")
    
    # Determine posting hour for this run
    posting_hour = decide_posting_time()
    print(f"📍 Running at {posting_hour:02d}:00 UTC\n")
    
    # ONCE PER CYCLE: Score pending experiments
    print("📍 Scoring pending experiments...")
    try:
        scored_results = score_pending_experiments()
        if scored_results:
            print(f"   ✅ Scored {scored_results} experiment(s)\n")
        else:
            print("   ℹ️  No new scores yet\n")
    except Exception as e:
        print(f"   ⚠️  Scoring error: {str(e)}\n")
    
    # ONCE PER CYCLE: Reflect on strategy
    print("📍 Analyzing strategy and patterns...")
    try:
        reflect_and_update_strategy()
        print("   ✅ Strategy updated\n")
    except Exception as e:
        print(f"   ⚠️  Strategy update error: {str(e)}\n")
    
    # NOW: Post content pieces
    posts_successful = 0
    
    for i in range(1, num_posts + 1):
        print(f"\n{'─'*70}")
        print(f"📝 Content Piece {i}/{num_posts}")
        print(f"{'─'*70}\n")
        
        # Get strategy mode and decide archetype, thread length, and topic
        target_archetype = "The Controversial Opinion"
        target_thread_length = 1
        target_topic = "Unknown"
        try:
            # Check what mode we should be in (normal, pivot, diversity, contrarian)
            strategy_mode = get_strategy_mode()
            
            # Make decisions based on strategy mode
            target_archetype = decide_archetype()
            target_thread_length = decide_thread_length()
            target_topic = decide_topic()
            
            # Calculate novelty boost for this specific combination
            novelty_boost = get_novelty_boost(target_archetype, target_topic, target_thread_length, 
                                             datetime.utcnow().hour)
            
            print(f"   Strategy mode: {strategy_mode}")
            
        except Exception as e:
            print(f"⚠️  Error deciding format: {str(e)}\n")
            continue
        
        # Generate content
        generated = None
        try:
            generated = generate_tweet(archetype=target_archetype, thread_length=target_thread_length, topic=target_topic)
            if generated.get("error"):
                print(f"⚠️  Generation error: {generated.get('error')}\n")
                continue
            
            print(f"✅ Generated\n")
            text_display = generated.get('text')
            if isinstance(text_display, list):
                print(f"   Format: {len(text_display)}-part thread")
                for idx, part in enumerate(text_display[:2], 1):
                    print(f"   [{idx}] {part[:60]}{'...' if len(part) > 60 else ''}")
                if len(text_display) > 2:
                    print(f"   ... +{len(text_display)-2} more")
            else:
                print(f"   Format: Single tweet")
                print(f"   {text_display[:70]}{'...' if len(text_display) > 70 else ''}")
            
            print(f"\n   Archetype: {target_archetype}")
            print(f"   Topic: {target_topic}")
            print(f"   Hypothesis: {generated.get('hypothesis')}\n")
            
        except Exception as e:
            print(f"❌ Generation error: {str(e)}\n")
            continue
        
        # Post to X
        posted = None
        try:
            posted = post_tweet(generated.get("text"))
            if posted.get("tweet_id"):
                print(f"✅ Posted to X\n")
                print(f"   Tweet ID: {posted.get('tweet_id')}\n")
            else:
                print(f"❌ Post failed: {posted.get('error')}\n")
                continue
        except Exception as e:
            print(f"❌ Posting error: {str(e)}\n")
            continue
        
        # Log experiment
        try:
            posting_hour = datetime.utcnow().hour
            experiment = {
                "tweet_id": posted.get("tweet_id"),
                "text": generated.get("text"),
                "archetype": target_archetype,
                "thread_length": posted.get("thread_length", generated.get("thread_length", 1)),
                "topic": target_topic,
                "posted_hour": posting_hour,
                "hypothesis": generated.get("hypothesis"),
                "format_used": generated.get("format_used"),
                "posted_at": posted.get("posted_at"),
                "score": None
            }
            append_experiment(experiment)
            print(f"📝 Logged to experiments.jsonl (posted at {posting_hour:02d}:00 UTC)")
            posts_successful += 1
        except Exception as e:
            print(f"⚠️  Logging error: {str(e)}")
    
    # Summary
    print(f"\n{'='*70}")
    print(f"✅ CYCLE COMPLETE")
    print(f"{'='*70}")
    print(f"\n📊 Results:")
    print(f"   Posts completed: {posts_successful}/{num_posts}")
    
    end_time = datetime.utcnow()
    duration = (end_time - start_time).total_seconds()
    print(f"   Duration: {duration:.1f}s")
    print(f"   Rate limit: ~{posts_successful}/50 posts used (X API)\n")


if __name__ == "__main__":
    run_daily_loop()
