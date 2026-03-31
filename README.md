# xbot — Autonomous X (Twitter) Bot with Self-Improving Strategy

**xbot** is an autonomous agent that posts to X (Twitter), measures engagement, learns what works, and autonomously improves its posting strategy over time using AI.

Instead of posting the same content repeatedly, xbot runs every 3 hours: it generates new tweets (1-3 pieces per run) based on your niche, posts them, waits for engagement to accumulate, scores them using a weighted engagement formula, analyzes patterns, and updates its strategy. Over time, it discovers which formats, tones, topics, **and posting times** drive the most valuable engagement for your account.

The bot continuously experiments with different posting hours to find your audience's peak engagement windows.

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                    Your Bot Identity                             │
│              (config/niche.md — you write once)                 │
│                                                                   │
│  • Topic/niche  • Audience  • Tone  • Success metrics            │
│  • Engagement weights  • Content boundaries                      │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
        ┌────────────────────────────────────┐
        │      DAILY RESEARCH LOOP            │
        │    (researcher.py runs daily)      │
        └────────────────────────────────────┘
                         │
            ┌────────────┼────────────┐
            │            │            │
            ▼            ▼            ▼
        ┌────────┐  ┌─────────┐  ┌────────┐
        │ SCORE  │  │GENERATE │  │  POST  │
        │ past   │→ │new tweet│→ │ to X   │
        │tweets  │  │(Gemini) │  │       │
        └────────┘  └─────────┘  └────────┘
            │            │            │
            │            └────────────┤
            │                         │
            └─────────────────┬───────┘
                              │
                         Wait 23hrs
                              │
                              ▼
                        ┌──────────────┐
                        │  REFLECT     │
                        │  Analyze     │
                        │  patterns &  │
                        │  update      │
                        │  strategy    │
                        └──────────────┘
                              │
                              ▼
        ┌────────────────────────────────────┐
        │  Updated Strategy (strategy.md)     │
        │  • Best formats & avg scores        │
        │  • Next hypothesis to test          │
        │  • Experiment history               │
        │  • Discarded approaches             │
        └────────────────────────────────────┘
```

**The loop:** Generate → Post → Wait → Score → Reflect → Update Strategy → Repeat

Each tweet is an experiment. The bot learns which formats, tones, and topics drive engagement. Over weeks, it discovers the optimal content mix for your niche.

---

## Continuous Re-Scoring: Learning from Mature Engagement

**The Problem:** Traditional bots score tweets once at 24 hours and lock the score in. But tweets continue gathering engagement for days. So the model learns from an incomplete picture.

**xbot's Solution:** Continuous re-scoring with intelligent priorities.

### How It Works:
- **Days 0-1:** Engagement accumulating, no score yet
- **Days 1-7:** Re-scored daily, latest score used for learning
  - Day 2: Score = 100 pts
  - Day 3: Score = 145 pts (re-scored, reflects fuller engagement)
  - Day 5: Score = 200 pts (re-scored again, used for strategy)
- **Days 7-30:** Optional re-score (30% chance to check for late engagement)
- **Days 30+:** Score locked, never re-scored

**Why This Matters:**
- ✅ Learns from mature engagement data, not 24-hour snapshots
- ✅ Distinguishes "flash engagement" (peaks fast, dies) from "sustainable engagement" (slow grow, stays high)
- ✅ Better trend detection—if an archetype is declining, you notice faster
- ✅ Score history shows engagement arc, revealing valuable patterns

**Example:**
```
"Question + Data" format:
- Initial (24h): 100 pts
- Later (7d): 280 pts

Without re-scoring, model thinks this format scores 100 pts.
With re-scoring, model learns it scores 280 pts.
Huge difference in strategy!
```

All scoring details: See "Score Tracking & Continuous Re-Scoring" in [`strategy.md`](strategy.md).

---

## Anti-Convergence: Preventing Stagnation

The bot is designed to prevent a common problem: **convergence**. Without safeguards, optimization leads to the bot discovering "Topic X + Format Y + Hour Z = highest score" and then repeating it forever until followers get bored.

**xbot prevents this with 5 layers of anti-convergence:**

1. **Time Decay**: Scores older than 60 days are dropped. This ensures the bot adapts when X's algorithm changes or trends shift.

2. **Novelty Bonuses**: Unexplored combinations get bonus scores (+15% to +50%). If "Thread Format" was tested 30 days ago but not recently, it gets a novelty boost to encourage re-testing.

3. **Diversity Quotas**: Hard limits on repetition. Max 2 archetypes per topic per 7 days, ensuring followers see variety.

4. **Decline Detection**: If a "best practice" starts scoring 20%+ worse recently, the bot automatically reduces reliance and explores alternatives.

5. **Contrarian Testing**: Every 5 posts, force testing the opposite of what's working best to discover new meta-strategies.

**Result:** The bot continuously improves while staying unpredictable and adapting to real-time algorithm changes.

Details on anti-convergence tracking: See the "Anti-Convergence Strategy" section in [`strategy.md`](strategy.md).

---

## Setup

### Step 1: Clone the repo
```bash
git clone https://github.com/yourusername/xbot.git
cd xbot
```

### Step 2: Set up environment variables
```bash
cp .env.example .env
# Edit .env and fill in your X API and Gemini API keys
```

See **[Where to Get API Keys](#where-to-get-api-keys)** below.

### Step 3: Define your bot's identity
Edit `config/niche.md` and fill in:
- Account topic/niche (what your bot posts about)
- Target audience (who should find it valuable?)
- Tone and voice (casual? technical? contrarian?)
- Content boundaries (what never to post about)
- Success metrics (what matters most: replies? followers? impressions?)
- Engagement weights (customize the scoring formula)
- Posting constraints (character limits, emoji usage, hashtags, etc.)

This file defines your bot's entire personality. Spend time on it.

### Step 4: Install dependencies
```bash
pip install -r requirements.txt
```

Requires: Python 3.11+

### Step 5: Test posting
```bash
python poster.py
```

This posts a test tweet and logs the experiment. Check your X account to verify it worked.

### Step 6: Test scoring (after 24+ hours)
```bash
python scorer.py
```

This fetches engagement metrics for tweets posted >23 hours ago and scores them. Won't do anything if no tweets are old enough yet.

### Step 7: Run the full loop manually
```bash
python researcher.py
```

This runs one complete research loop cycle:
1. Score old experiments (posts 23+ hours old)
2. Analyze strategy and update strategy.md
3. Generate 1-3 content pieces dynamically (mix of single tweets and threads)
4. Post each piece
5. Log each experiment with archetype, topic, thread length, **and posting hour**

Watch the console output to see each step progress.

### Step 8: Automate with GitHub Actions
Push the repo to GitHub:
```bash
git add .
git commit -m "Initial autobot setup"
git push -u origin main
```

Then add your API keys as GitHub repository secrets:
1. Go to **Settings → Secrets and variables → Actions**
2. Click **New repository secret** and add each of these:
   - `X_API_KEY`
   - `X_API_SECRET`
   - `X_ACCESS_TOKEN`
   - `X_ACCESS_TOKEN_SECRET`
   - `X_BEARER_TOKEN`
   - `NVIDIA_API_KEY`

The workflow in `.github/workflows/daily_post.yml` will now run automatically **every 3 hours** (at 00:00, 03:00, 06:00, 09:00, 12:00, 15:00, 18:00, 21:00 UTC) and commit changes back to the repo. This enables the bot to discover which hours drive the best engagement.

---

## Where to Get API Keys

### X (Twitter) API Keys
1. Go to [X Developer Portal](https://developer.twitter.com/en/portal/dashboard)
2. Create a new project or use an existing one
3. Create an "App" within the project
4. Go to **Keys and tokens** tab
5. Generate/copy these values:
   - **API Key** → `X_API_KEY`
   - **API Secret** → `X_API_SECRET`
   - **Access Token** → `X_ACCESS_TOKEN`
   - **Access Token Secret** → `X_ACCESS_TOKEN_SECRET`
   - **Bearer Token** → `X_BEARER_TOKEN`

**Permissions needed:**
- Read: tweets, follows, blocks, mutes, bookmarks, users
- Write: tweets, follows, bookmarks

### NVIDIA API Key
1. Go to [NVIDIA API Catalog](https://build.nvidia.com/qwen/qwen3-5-122b-a10b)
2. Sign in or create an account
3. Generate an API key
4. Copy it → `NVIDIA_API_KEY`

The bot uses the Qwen 3.5-122B model via NVIDIA's API for tweet generation and strategy analysis.

---

## Files You Own vs Files the Agent Owns

| File | Owner | Notes |
|------|-------|-------|
| `config/niche.md` | **You** | Define bot identity once. Update if strategy shifts. |
| `strategy.md` | **Agent** | Autonomously rewritten daily by researcher.py based on experiment results. Don't edit manually. |
| `data/experiments.jsonl` | **Agent** | Append-only log of all posts. Each line is one experiment (JSON). Don't edit. |
| `generator.py` | **You** | Generates tweets using NVIDIA API (Qwen 3.5-122B). Modify prompts if needed. |
| `poster.py` | **You** | Posts tweets and logs experiments. Core posting logic. |
| `scorer.py` | **You** | Fetches metrics and scores tweets. Modify weights here if needed. |
| `researcher.py` | **You** | Main orchestration loop. Analyzes strategy using NVIDIA API. Modify schedule or add steps here. |
| `requirements.txt` | **You** | Dependencies. Update if you add new packages. |
| `.env` | **You** | API keys. Keep secret. Never commit to git. |
| `.env.example` | **You** | Template for .env. Safe to commit. |
| `.gitignore` | **You** | Already ignores .env, data/, and __pycache__. |

---

## How to Read the Experiment Log

Experiments are appended to `data/experiments.jsonl`—one JSON object per line.

Each record looks like:
```json
{
  "tweet_id": "1234567890",
  "text": "Your posted tweet text here or [\"tweet 1\", \"tweet 2\", ...]",
  "archetype": "The Controversial Opinion",
  "topic": "Founder Reality",
  "thread_length": 3,
  "posted_hour": 9,
  "hypothesis": "Testing if 3-piece threads on Founder Reality drive more replies",
  "format_used": "3-piece thread",
  "posted_at": "2026-03-31T09:15:30Z",
  "score": 285.5
}
```

**Columns:**
- `tweet_id`: X's unique identifier for the tweet
- `text`: The exact tweet text (string for single tweets, array for threads)
- `archetype`: Which of the 10 archetypes was used (e.g., "The Debate Starter", "The Data Drop")
- `topic`: Topic cluster covered (e.g., "AI & Future", "Founder Reality")
- `thread_length`: How many parts (1 for single, 2-7 for threads)
- `posted_hour`: UTC hour when posted (0-23) — tracks best posting times
- `hypothesis`: One sentence: what was this tweet testing?
- `format_used`: Short label combining archetype + thread length
- `posted_at`: ISO 8601 timestamp (UTC) when posted
- `score`: Weighted engagement score (null until 23+ hours have passed)

**To analyze experiments:**
```bash
# See the last 5 experiments
tail -5 data/experiments.jsonl

# Pretty-print one experiment
cat data/experiments.jsonl | jq '.' | head -20

# Find highest-scoring experiments by archetype
cat data/experiments.jsonl | jq 'select(.score != null) | {archetype, score}' | sort -rn

# See which posting hours perform best
cat data/experiments.jsonl | jq 'select(.score != null) | {posted_hour, score}' | sort -rn
```

The agent reads this file daily to identify which archetypes, topics, thread lengths, **and posting times** score highest, then updates strategy.md accordingly.

---

## Tips for Tuning Engagement Weights

The engagement weights in `config/niche.md` determine your bot's priorities. They're in the **Engagement Weights** section:

```markdown
| Interaction Type | Points |
|---|---|
| Impression | 0.1 |
| Like | 2 |
| Retweet | 6 |
| Reply | 8 |
```

**How to think about it:**

- **Replies** (high value): Direct engagement, signals readers are interested enough to respond. Set high (4-7).
- **Retweets** (medium-high): Active endorsement, spreads your reach. Set medium (4-6).
- **Likes** (medium): Passive approval, good but less meaningful than replies. Set lower (2-4).
- **Impressions** (low): Just means it was shown. Set very low (0.1-0.5).

**Different goals, different weights:**

- **Building community / driving replies:** Increase reply weight to 7+, keep others low
- **Going viral / maximizing reach:** Increase retweet weight to 8+, impression weight to 1+
- **Balanced growth:** Keep all 2-5 (current defaults are good)
- **Engagement over vanity metrics:** Lower likes/impressions, raise replies/retweets

The agent uses these weights to score every tweet, so changing them changes what the bot considers "success"—and thus what it generates more of.

**Adjust weights and observe:** Change them, run the loop a few times, then check which formats the agent starts favoring in strategy.md. The weights directly shape the agent's learning.

---

## Troubleshooting

**"Error: Missing X_API_KEY in .env"**
→ Copy `.env.example` to `.env` and fill in all 6 keys. See **Where to Get API Keys**.

**"Tweet posting failed"**
→ Check that your X app has **write:tweets** permission. Go to [Developer Portal](https://developer.twitter.com/).

**"No pending experiments to score"**
→ Tweets need to be 23+ hours old to score. Post a tweet, wait a day, then run `python scorer.py`.

**"Strategy update failed"**
→ Check that `GEMINI_API_KEY` is valid. Visit [Google AI Studio](https://aistudio.google.com/).

**"Git push failed in GitHub Actions"**
→ The workflow uses the default GitHub token. If it still fails, check repo permissions under **Settings → Actions → General**.

---

## Project Structure

```
xbot/
├── config/
│   └── niche.md              # Bot identity (you fill this in)
├── data/
│   ├── .gitkeep
│   └── experiments.jsonl     # Experiment log (agent appends)
├── .github/
│   └── workflows/
│       └── daily_post.yml    # GitHub Actions scheduler
├── strategy.md               # Current strategy (agent rewrites daily)
├── generator.py              # Generate tweets with Gemini
├── poster.py                 # Post tweets to X
├── scorer.py                 # Score tweets by engagement
├── researcher.py             # Main orchestration loop
├── requirements.txt          # Dependencies
├── .env.example              # Template for secrets (commit this)
├── .env                      # Your actual secrets (git-ignored)
├── .gitignore                # Ignores .env, __pycache__, data/
└── README.md                 # This file
```

---

## Next Steps

1. **Set up your identity:** Fill in `config/niche.md` with your bot's niche, tone, and success metrics.
2. **Test locally:** Run `python researcher.py` a few times to ensure everything works.
3. **Go live:** Push to GitHub, add secrets (including `NVIDIA_API_KEY`), and let it run daily.
4. **Monitor:** Check `strategy.md` daily to see what the agent learned. Read `data/experiments.jsonl` to spot trends.
5. **Iterate:** If results aren't great, adjust niche.md (success metrics, tone, content boundaries) or tune engagement weights.

Good luck! 🚀

---

## License

MIT

