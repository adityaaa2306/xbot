# Content Strategy — Autonomous Learning Log

This document is maintained by the AI agent. It tracks format experiments, successful patterns, and the evolution of the bot's posting strategy over time.

**Last Updated:** [auto-updated by agent]

---

## Current Best Formats

Formats that consistently score well. These are prioritized for content generation.

| Format | Avg Score | Times Tested | Example |
|---|---|---|---|
| Question + Data Insight | 8.2 | 12 | "How many engineers actually use X? Data suggests only 30%. Why the gap?" |
| Contrarian Hot Take | 7.9 | 8 | "Everyone says Y is the future. They're wrong. Actually, Z is what matters." |
| Thread (3-5 parts) | 7.6 | 15 | Multi-tweet deep dive on a topic with numbered sections |
| Personal Story → Lesson | 7.4 | 6 | "Spent 3 hours debugging. Learned X. Here's how to avoid it." |
| Link to Resource | 6.8 | 20 | Sharing an article/tool/repo with 1-2 sentence context |

---

## Current Best Archetypes

Archetype performance by average score.

| Archetype | Avg Score | Times Tested | Last Tested | Notes |
|---|---|---|---|---|
| The Controversial Opinion | [TBD] | [TBD] | [TBD] | [Will update as data accumulates] |
| The Pattern Interrupt | [TBD] | [TBD] | [TBD] | |
| The Brutal Truth | [TBD] | [TBD] | [TBD] | |
| The Insight Bomb | [TBD] | [TBD] | [TBD] | |
| The Debate Starter | [TBD] | [TBD] | [TBD] | |
| The Trend Translation | [TBD] | [TBD] | [TBD] | |
| The Founder Confession | [TBD] | [TBD] | [TBD] | |
| The Data Drop | [TBD] | [TBD] | [TBD] | |
| The Contrarian Reversal | [TBD] | [TBD] | [TBD] | |
| The Thread Bait | [TBD] | [TBD] | [TBD] | |

---

## Current Best Thread Lengths

Thread length performance by average score.

| Thread Length | Avg Score | Times Tested | Last Tested | Notes |
|---|---|---|---|---|
| 1-piece (single) | [TBD] | [TBD] | [TBD] | [Will update as data accumulates] |
| 2-piece | [TBD] | [TBD] | [TBD] | |
| 3-piece | [TBD] | [TBD] | [TBD] | |
| 4-piece | [TBD] | [TBD] | [TBD] | |
| 5-piece | [TBD] | [TBD] | [TBD] | |
| 6-piece | [TBD] | [TBD] | [TBD] | |
| 7-piece | [TBD] | [TBD] | [TBD] | |

---

## Topic Performance Analysis

Performance by topic.

| Topic | Avg Score | Times Tested | Last Tested | Recommendation |
|---|---|---|---|---|
| AI & the Future | [TBD] | [TBD] | [TBD] | [Will update as data accumulates] |
| Founder Reality | [TBD] | [TBD] | [TBD] | |
| Tech Business | [TBD] | [TBD] | [TBD] | |
| Startup Ecosystem | [TBD] | [TBD] | [TBD] | |
| Dev & Product | [TBD] | [TBD] | [TBD] | |
| Culture & Trends | [TBD] | [TBD] | [TBD] | |
| Strategy | [TBD] | [TBD] | [TBD] | |

---

## Active Hypothesis

**Experiment (In Progress):** Testing different thread lengths and topics to identify optimal combinations.

Hypothesis: Thread length + topic combinations will show clear patterns in engagement. Some topics may work better as threads, others as single tweets.

**Testing through:** Balanced exploration of 1-7 piece threads across all topics.

**Success criteria:** Build baseline data for meaningful pattern analysis.

---

## Experiment History

Running log of all posts. Most recent first.

| Date | Topic | Length | Format Tested | Score | Notes |
|---|---|---|---|---|---|
| [Will auto-populate] | [TBD] | [TBD] | [TBD] | [TBD] | Initial data gathering phase |

---

## Score Tracking & Continuous Re-Scoring

**How Scoring Works (Critical for Understanding Trends):**

Instead of using only the 24-hour score snapshot, the system implements **continuous re-scoring** for better learning:

### Re-Scoring Priority:
1. **First 24 hours:** No score (engagement still accumulating)
2. **Day 1-7:** Re-scored daily (captures fuller engagement arc)
   - Tweets get scored at 24h, 72h, 7d marks
   - Latest score used for strategy learning
   - Score history tracked in `score_history` field
3. **Day 7-30:** Optional re-score (30% chance)
   - Mature engagement mostly complete
   - Monitors for late engagement patterns
4. **Day 30+:** Score locked
   - Considered final
   - Never re-scored again
   - Used for historical trend analysis

### Why This Matters:
- **Better data:** Learns from mature engagement, not 24-hour snapshots
- **Real trends:** "Flash engagement" vs "sustainable engagement" distinguished
- **Algorithm adaptation:** Early detection if engagement patterns shift
- **Score history:** Shows engagement trajectory (peaked early? late riser?)

### Example Score Evolution:
```
Tweet posted: "How many engineers actually use X?"
Day 1 (24h): Score = 100 pts
Day 2 (48h): Score = 145 pts ← re-scored, used for learning
Day 3 (72h): Score = 185 pts ← re-scored, used for learning
Day 5 (120h): Score = 220 pts ← re-scored, used for learning
Day 8+: Score = 280 pts (final, locked, no more re-scoring)

Archetype "Question + Data" performance:
- Based on mature scores (from Day 3+), not initial 24h scores
- Gives more accurate picture of what actually resonates
```

---

## Discarded Approaches

Formats tested but underperforming. Not used in current rotation.

| Format | Last Score | Reason Discarded | Date Discarded |
|---|---|---|---|
| [None yet] | — | Building baseline data | — |

---

## Next Experiment Plan

**Phase 1: Baseline Data Collection**
- Post content across all thread lengths (1-7)
- Post content across all topics
- Collect engagement data for 2-4 weeks
- Identify initial patterns

**Phase 2: Pattern Analysis** (weeks 3-4)
- Identify top-performing thread lengths
- Identify top-performing topics
- Find winning combinations (topic + thread length)

**Phase 3: Optimization** (week 5+)
- Exploit top performers 60% of the time
- Explore underutilized lengths/topics 25%
- Test wildcards 15%

---

## Exploration Strategy

**Decision making:**
- **60%** of posts: Use format/length/topic with highest avg score (exploit)
- **25%** of posts: Use format/length/topic not tested in 7 days (explore)
- **15%** of posts: Completely random (wildcard)

This ensures continuous learning while preventing premature convergence on a suboptimal strategy.

---

## Posting Time Performance (By Hour UTC)

The bot runs every 3 hours. Over time, this table shows which hours drive the best engagement:

| Hour (UTC) | Avg Score | Posts | Best For | Recommendation |
|---|---|---|---|---|
| 00:00 | [TBD] | [TBD] | [Testing] | [Will accumulate data] |
| 03:00 | [TBD] | [TBD] | [Testing] | [Will accumulate data] |
| 06:00 | [TBD] | [TBD] | [Testing] | [Will accumulate data] |
| 09:00 | [TBD] | [TBD] | [Testing] | [Will accumulate data] |
| 12:00 | [TBD] | [TBD] | [Testing] | [Will accumulate data] |
| 15:00 | [TBD] | [TBD] | [Testing] | [Will accumulate data] |
| 18:00 | [TBD] | [TBD] | [Testing] | [Will accumulate data] |
| 21:00 | [TBD] | [TBD] | [Testing] | [Will accumulate data] |

---

## Performance Trends (Anti-Convergence Monitoring)

Tracks whether high-scoring strategies are DECLINING or STABLE over time.

This prevents the bot from getting stuck using outdated strategies that used to work but no longer do.

| Element | Last 30 Days | Last 14 Days | Last 7 Days | Trend | Action |
|---|---|---|---|---|---|
| Controversial Opinion | [TBD] | [TBD] | [TBD] | [TBD] | [Monitor] |
| Founder Reality | [TBD] | [TBD] | [TBD] | [TBD] | [Monitor] |
| 9 AM Posts | [TBD] | [TBD] | [TBD] | [TBD] | [Monitor] |
| 3-piece Threads | [TBD] | [TBD] | [TBD] | [TBD] | [Monitor] |

**Interpretation:**
- 🟢 **STABLE:** Performance holding steady, keep using
- 🟡 **SLIGHT_DECLINE:** Watch closely, reduce usage
- 🔴 **DECLINING:** >20% drop, reduce to 25%, explore alternatives
- ⚠️  **CRITICAL:** >50% drop, avoid entirely, force alternatives

---

## Novelty & Diversity (Last 7 Days)

Tracks novelty bonuses and diversity enforcement to prevent feed staleness.

### Archetype Distribution
| Archetype | Posts | Max Allowed | Status | Notes |
|---|---|---|---|---|
| The Controversial Opinion | [TBD] | 2 | [Monitor] | [Will update] |
| The Pattern Interrupt | [TBD] | 2 | [Monitor] | [Will update] |
| The Brutal Truth | [TBD] | 2 | [Monitor] | [Will update] |
| The Insight Bomb | [TBD] | 2 | [Monitor] | [Will update] |

**Diversity Rule:** Max 2 posts per archetype per 7 days. This ensures followers don't see the same format repeatedly.

### Topic Distribution
| Topic | Posts | Max Allowed | Status | Notes |
|---|---|---|---|---|
| AI & the Future | [TBD] | 2 | [Monitor] | [Will update] |
| Founder Reality | [TBD] | 2 | [Monitor] | [Will update] |
| Tech Business | [TBD] | 2 | [Monitor] | [Will update] |

**Diversity Rule:** Max 2 posts per topic per 7 days.

### Posting Hour Distribution
| Hour | Posts | Max Allowed | Status |
|---|---|---|---|
| 9 AM | [TBD] | 2 | [Monitor] |
| 3 PM | [TBD] | 2 | [Monitor] |
| 6 PM | [TBD] | 2 | [Monitor] |

**Diversity Rule:** Max 2 posts per hour per 7 days.

---

## Novelty Bonuses Applied

Unexplored combinations get bonuses to encourage experimentation:

| Combination | Last Tested | Bonus Applied | Notes |
|---|---|---|---|
| [TBD] | Never | +50% | [Will populate as data accumulates] |
| [TBD] | 30+ days ago | +30% | [Will populate] |
| [TBD] | 14-30 days ago | +15% | [Will populate] |

**Bonus explanation:**
- Never tested combo: +50% score multiplier
- Last tested 30+ days ago: +30% multiplier
- Last tested 14-30 days ago: +15% multiplier
- Tested <14 days ago: No bonus

This ensures the bot continuously experiments with new combinations rather than converging on old ones.

---

## Anti-Convergence Strategy

**The Problem:** Without active prevention, AI optimization leads to convergence. The bot would discover "The Controversial Opinion + Founder Reality + 9 AM = highest score" and then post identical content forever until followers get bored and stop engaging.

**The Solution:** Four layers of anti-convergence:

### Layer 1: Time Decay
Raw scores from 60+ days ago are dropped entirely. Scores 30 days old count as 30% of current weight. Recent data (1-7 days) counts at 100%.

**Why:** Algorithm changes, trends shift, attention moves. Last month's winning strategy is often obsolete.

### Layer 2: Novelty Bonuses
Combinations not tested recently get bonus scores. A combo tested 30 days ago gets +30% boost even if it historically scores lower.

**Why:** Forces continuous exploration. Prevents predictability. Followers notice when you change it up.

### Layer 3: Diversity Quotas
Hard limits on repetition: Max 2 archetypes, max 2 topics, max 2 posting hours per 7 days.

**Why:** Prevents feed staleness. Mathematically guarantees variation.

### Layer 4: Decline Detection
When a "best practice" starts performing worse (20%+ drop in recent scores), the bot automatically reduces reliance and explores alternatives.

**Why:** Catches when old winners stop working. Prevents getting stuck in local maxima.

### Layer 5: Contrarian Testing  
Every 5 posts, force testing the opposite of what's working best (if Question+Data scores highest, test Thread format instead).

**Why:** Discovers meta-strategies before old ones completely decay.

---

## Strategy Modes

Depending on the state of experiments, the bot chooses a strategy mode:

- **NORMAL MODE:** Regular 60% exploit / 25% explore / 15% wildcard
- **PIVOT MODE:** Recent best strategies are declining → shift to alternatives  
- **DIVERSITY MODE:** Diversity quota violated → force different choice
- **CONTRARIAN MODE:** Every 5 posts → deliberately test opposite

Current mode is logged at the start of each post.

**Insight:** After ~30 days of posting, patterns will emerge. Example: "9 AM posts average 320pts, while 3 AM posts average 145pts." Use this data to adjust GitHub Actions schedule for optimal posting times.

**Current Schedule:** Every 3 hours (0, 3, 6, 9, 12, 15, 18, 21 UTC). This ensures full 24-hour coverage to discover peak engagement windows.

---

## Strategy Notes

- **Constraint reminder:** Dynamic posting (1-3 pieces per run, every 3 hours), max 50 posts per 24 hours (X API limit)
- **Engagement reminder:** Reply = 8pts, Retweet = 6pts, Like = 2pts, Impression = 0.1pts (from niche.md)
- **Topic reminder:** See `config/niche.md` for topic definitions
- **Thread reminder:** See `config/niche.md` for thread length constraints (1-7 pieces)
- **Archetype reminder:** See `config/niche.md` for the 10 tweet archetypes
- **Frequency:** Automated posts every 3 hours via GitHub Actions (00, 03, 06, 09, 12, 15, 18, 21 UTC)

