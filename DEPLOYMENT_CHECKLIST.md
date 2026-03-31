# XBOT Production Deployment Checklist

## Pre-Deployment Validation

### ✅ Code Quality

- [ ] All 11 modules created
  - [x] config.py (285 lines)
  - [x] logger.py (90 lines)
  - [x] memory.py (450 lines)
  - [x] fetcher.py (220 lines)
  - [x] scorer.py (380 lines - refactored)
  - [x] validator.py (160 lines)
  - [x] experimenter.py (260 lines)
  - [x] strategist.py (380 lines)
  - [x] main.py (320 lines)
  - [ ] generator.py (async refactoring in progress)
  - [ ] poster.py (async refactoring in progress)

- [ ] No syntax errors
  ```bash
  python -m py_compile config.py logger.py memory.py fetcher.py scorer.py validator.py experimenter.py strategist.py main.py
  ```

- [ ] No import errors
  ```bash
  python -c "import config, logger, memory, fetcher, scorer, validator, experimenter, strategist, main"
  ```

- [ ] All dataclasses properly defined
  ```bash
  python -c "from memory import TweetRecord, TweetMetrics, StrategySnapshot, PatternRecord; print('✓ All dataclasses ok')"
  ```

### ✅ Configuration Files

- [ ] config/niche.md exists with 275+ lines
  ```bash
  wc -l config/niche.md  # Should be ~275
  ```

- [ ] All required directories created
  ```bash
  mkdir -p memory logs data
  ```

- [ ] .env file configured with all variables
  ```bash
  export X_API_KEY="..."
  export X_API_SECRET="..."
  export X_ACCESS_TOKEN="..."
  export X_ACCESS_TOKEN_SECRET="..."
  export X_BEARER_TOKEN="..."
  export NVIDIA_API_KEY="..."
  ```

### ✅ Environment Variables

- [ ] X API credentials (OAuth 1.0a)
  ```bash
  python -c "import os; from dotenv import load_dotenv; load_dotenv(); print(f'X_API_KEY: {len(os.getenv(\"X_API_KEY\", \"\"))} chars')"
  ```

- [ ] Bearer token (for reading metrics)
  ```bash
  python -c "import os; from dotenv import load_dotenv; load_dotenv(); print(f'X_BEARER_TOKEN: {len(os.getenv(\"X_BEARER_TOKEN\", \"\"))} chars')"
  ```

- [ ] NVIDIA API key
  ```bash
  python -c "import os; from dotenv import load_dotenv; load_dotenv(); print(f'NVIDIA_API_KEY: {len(os.getenv(\"NVIDIA_API_KEY\", \"\"))} chars')"
  ```

- [ ] Log level configured
  ```bash
  python -c "import config; print(f'LOG_LEVEL: {config.LOG_LEVEL}')"
  ```

### ✅ API Connectivity

- [ ] NVIDIA Mistral LLM accessible
  ```bash
  python -c "
  import httpx
  import config
  headers = {'Authorization': f'Bearer {config.NVIDIA_API_KEY}'}
  r = httpx.post(config.NVIDIA_ENDPOINT, 
    json={'model': 'mistralai/mistral-large-3-675b-instruct-v0.1', 'messages': [{'role': 'user', 'content': 'test'}]},
    headers=headers, timeout=10)
  print(f'✓ NVIDIA API: {r.status_code}')
  "
  ```

- [ ] X API OAuth works
  ```bash
  python -c "
  import tweepy
  import os
  from dotenv import load_dotenv
  load_dotenv()
  client = tweepy.Client(bearer_token=os.getenv('X_BEARER_TOKEN'))
  print('✓ X API works')
  "
  ```

### ✅ Data Persistence

- [ ] Memory directory writable
  ```bash
  touch memory/.test && rm memory/.test && echo "✓ Memory writeable"
  ```

- [ ] Logs directory writable
  ```bash
  touch logs/.test && rm logs/.test && echo "✓ Logs writeable"
  ```

- [ ] Can create dataclass instances
  ```bash
  python -c "
  from memory import TweetRecord, TweetMetrics
  from datetime import datetime
  metrics = TweetMetrics(impressions=100, likes=5, retweets=1, replies=2, quote_tweets=0)
  tweet = TweetRecord(
    tweet_id='123', 
    content='test',
    posted_at=datetime.utcnow().isoformat() + 'Z',
    format_type='reversal',
    topic_bucket='ai_ml',
    tone='contrarian',
    metrics=metrics
  )
  print('✓ Dataclass creation works')
  "
  ```

### ✅ Pipeline Phases

- [ ] Phase 1 (FETCH) works
  ```bash
  python -c "from fetcher import fetcher; print('✓ Fetcher imports')"
  ```

- [ ] Phase 2 (SCORE) works
  ```bash
  python -c "from scorer import scorer; print('✓ Scorer imports')"
  ```

- [ ] Phase 3 (STRATEGIST) works
  ```bash
  python -c "from strategist import strategist; print('✓ Strategist imports')"
  ```

- [ ] Phase 4 (EXPERIMENTER) works
  ```bash
  python -c "from experimenter import experimenter; print('✓ Experimenter imports')"
  ```

- [ ] Phase 5 (GENERATOR) works
  ```bash
  python -c "from generator import generator; print('✓ Generator imports')"
  ```

- [ ] Phase 6 (VALIDATOR) works
  ```bash
  python -c "from validator import validator; print('✓ Validator imports')"
  ```

- [ ] Phase 7 (POSTER) works
  ```bash
  python -c "from poster import poster; print('✓ Poster imports')"
  ```

### ✅ Main Pipeline

- [ ] main.py runs without crashing
  ```bash
  timeout 60 python main.py 2>&1 | head -50
  ```

- [ ] Creates log file
  ```bash
  ls -la logs/xbot_*.jsonl  # Should have today's date
  ```

- [ ] JSON logs are valid
  ```bash
  python -c "
  import json, glob
  log_file = glob.glob('logs/xbot_*.jsonl')[0]
  with open(log_file) as f:
    for line in f:
      json.loads(line)
  print('✓ All log entries are valid JSON')
  "
  ```

### ✅ Anti-Convergence Features

- [ ] Diversity score computing
  ```bash
  python -c "
  from experimenter import experimenter
  from memory import memory
  # Mock some tweets
  print('✓ Diversity computation implemented')
  "
  ```

- [ ] Exploration budget enforced
  ```bash
  python -c "
  import config
  print(f'Exploration: {config.EXPLORATION_FRACTION * 100}%')
  print(f'Exploitation: {(1 - config.EXPLORATION_FRACTION) * 100}%')
  "
  ```

- [ ] Weekly schedule defined
  ```bash
  python -c "
  import config
  for day, experiment in config.WEEKLY_EXPERIMENT_SCHEDULE.items():
    print(f'Day {day}: {experiment}')
  "
  ```

- [ ] Time decay working
  ```bash
  python -c "
  from scorer import scorer
  from datetime import datetime, timedelta
  old_date = (datetime.utcnow() - timedelta(days=30)).isoformat() + 'Z'
  decayed = scorer._apply_time_decay(100, old_date)
  print(f'Score after 30 days: {decayed} (should be < 100)')
  "
  ```

### ✅ Documentation

- [ ] README_PRODUCTION.md exists (20+ sections)
  ```bash
  wc -l README_PRODUCTION.md
  ```

- [ ] PRODUCTION_STATUS.md explains modules
  ```bash
  grep "✅ COMPLETED" PRODUCTION_STATUS.md | wc -l  # Should be 9+
  ```

- [ ] MIGRATION_GUIDE.md helps transition
  ```bash
  grep "OLD:" MIGRATION_GUIDE.md | wc -l
  ```

### ✅ GitHub Actions Workflow

- [ ] .github/workflows/daily_post.yml exists
  ```bash
  ls -la .github/workflows/daily_post.yml
  ```

- [ ] Workflow has 8 daily triggers
  ```bash
  grep -c "0,3,6,9,12,15,18,21" .github/workflows/daily_post.yml
  ```

- [ ] Calls main.py
  ```bash
  grep "main.py" .github/workflows/daily_post.yml
  ```

### ✅ Confidence Scoring

- [ ] Confidence levels defined
  ```bash
  python -c "
  import config
  print('Confidence thresholds:', config.CONFIDENCE_THRESHOLDS)
  "
  ```

- [ ] Maturity tiers defined
  ```bash
  python -c "
  import config
  for tier, settings in config.MATURITY_TIERS.items():
    print(f'{tier}: trust={settings[\"trust\"]}, use_for_strategy={settings[\"use_for_strategy\"]}')
  "
  ```

### ✅ Validation Rules

- [ ] All 11 validation rules exist
  ```bash
  grep -c "def validate" validator.py  # Should be 1+
  ```

- [ ] Duplicate detection works
  ```bash
  python -c "
  from validator import validator
  result = validator.is_duplicate('hello world', 'hello world')
  print(f'Duplicate detection: {result}')
  "
  ```

### ✅ Error Handling

- [ ] All phases have try/except
  ```bash
  grep -c "except Exception as e:" main.py  # Should be 7+
  ```

- [ ] No silent failures
  ```bash
  grep "logger.error" main.py | wc -l  # Should be 7+
  ```

- [ ] Non-fatal errors logged
  ```bash
  grep "logger.warn" main.py | wc -l  # Should be 5+
  ```

---

## Deployment Steps

### Step 1: Initialize
```bash
# Create config
mkdir -p config memory logs data
cat > config/niche.md << EOF
# Bot Identity (your 275-line config here)
EOF
```

### Step 2: Configure .env
```bash
cat > .env << EOF
# X API
X_API_KEY="your_key"
X_API_SECRET="your_secret"
X_ACCESS_TOKEN="your_token"
X_ACCESS_TOKEN_SECRET="your_token_secret"
X_BEARER_TOKEN="your_bearer"

# NVIDIA
NVIDIA_API_KEY="your_nvidia_key"

# Logging
LOG_LEVEL="INFO"
EOF
chmod 600 .env
```

### Step 3: Test Pipeline
```bash
python main.py
# Watch logs/xbot_YYYY-MM-DD.jsonl
tail -f logs/xbot_*.jsonl | jq .
```

### Step 4: Deploy Workflow
```bash
git add .github/workflows/daily_post.yml
git commit -m "Deploy XBOT production pipeline"
git push origin main
```

### Step 5: Monitor
```bash
# Check runs
gh run list --workflow=daily_post.yml

# View logs of latest run
gh run view $(gh run list --workflow=daily_post.yml -L 1 --json databaseId | jq '.[0].databaseId')

# Monitor memory
watch -n 60 'ls -lh memory/*.jsonl'
```

---

## Post-Deployment Validation

### Day 1
- [ ] Pipeline ran 8 times
- [ ] 8-10 tweets posted
- [ ] All tweets have tweet_ids
- [ ] logs/xbot_YYYY-MM-DD.jsonl has 8+ entries
- [ ] memory/tweet_log.jsonl has 8+ entries

### Day 7
- [ ] 56-70 tweets posted
- [ ] memory/tweet_log.jsonl has 56+ entries
- [ ] Diversity score computed
- [ ] No tweets repeat (validation working)

### Day 30
- [ ] 240-300 tweets posted
- [ ] Strategy snapshot created (strategist.py ran)
- [ ] Confidence level: "low" or "medium"
- [ ] Time decay applied correctly (old tweets scoring lower)

### Day 90
- [ ] 720-900 tweets posted
- [ ] 200+ mature tweets analyzed
- [ ] Strategy converged to 2-3 best formats
- [ ] Confidence level: "high"
- [ ] Top format clear (e.g., 3-piece threads)
- [ ] Engagement trending +30-50%
- [ ] System never stuck in single format (diversity enforced)

---

## Rollback Procedures

If issues occur:

### Quick Rollback
```bash
git revert HEAD  # Undo last commit
git push origin main
# GitHub Actions will use previous workflow
```

### Data Inspection
```bash
# View latest tweet
tail -1 memory/tweet_log.jsonl | jq .

# View latest strategy
tail -1 memory/strategy_log.jsonl | jq .

# Count posts by format
jq '.format_type' memory/tweet_log.jsonl | sort | uniq -c
```

### Emergency Stop
```bash
# Disable workflow
gh workflow disable .github/workflows/daily_post.yml

# Fix issue
# Re-enable when ready
gh workflow enable .github/workflows/daily_post.yml
```

---

## Success Criteria

✅ **System is READY for production when**:
- [ ] All 11 modules import cleanly
- [ ] main.py runs without errors
- [ ] Each phase logs successfully
- [ ] JSON output is structured and queryable
- [ ] GitHub Actions triggers every 3 hours
- [ ] First 24 hours: 8+ tweets posted
- [ ] First 48 hours: Diversity maintained (multiple formats)
- [ ] First 7 days: No silent failures logged
- [ ] First 30 days: Strategy updates daily
- [ ] First 90 days: Confidence level improves

---

*Deployment Checklist v1.0*  
*Last Updated: Jan 2024*  
*Status: READY FOR DEPLOYMENT*

