"""Orchestrates scraping, filtering, ranking, and research brief generation."""

from __future__ import annotations

from datetime import datetime
from time import monotonic
from typing import Any, Dict, List, Optional, Sequence

import config
from filtering.signal_filter import SignalFilter
from ingestion.models import CreatorTarget, SignalTweet
from ingestion.storage import (
    append_jsonl,
    load_json,
    load_latest_jsonl,
    upsert_jsonl_by_key,
    write_json,
)
from ingestion.targets import build_run_targets
from ingestion.x_scraper import PlaywrightXScraper
from logger import logger
from research.brief_engine import ResearchBriefEngine


class SignalEngine:
    """Run the low-risk signal ingestion and research pipeline."""

    def __init__(
        self,
        *,
        scraper: Optional[PlaywrightXScraper] = None,
        signal_filter: Optional[SignalFilter] = None,
        brief_engine: Optional[ResearchBriefEngine] = None,
    ):
        self.scraper = scraper or PlaywrightXScraper()
        self.signal_filter = signal_filter or SignalFilter()
        self.brief_engine = brief_engine or ResearchBriefEngine()

    async def run(self) -> Dict[str, Any]:
        started_at = monotonic()
        targets = build_run_targets()
        creators = [CreatorTarget(**item) for item in targets["creators"]]
        queries = list(targets["search_queries"])

        logger.info(
            "SIGNAL_ENGINE_START",
            phase="SIGNALS",
            data={"creators": len(creators), "queries": len(queries), "run_slot": targets["run_slot"]},
        )

        raw_signals: List[SignalTweet] = []
        if creators:
            raw_signals.extend(
                await self.scraper.scrape_creators(creators, max_tweets=config.SIGNAL_TWEETS_PER_CREATOR)
            )
        if queries:
            raw_signals.extend(
                await self.scraper.scrape_search_queries(queries, max_tweets=config.SIGNAL_TWEETS_PER_SEARCH)
            )

        unique_raw = self._dedupe_by_id(raw_signals)
        upsert_jsonl_by_key(
            config.SIGNAL_RAW_LOG_FILE,
            [signal.to_dict() for signal in unique_raw],
            key="tweet_id",
        )

        ranked = self.signal_filter.filter_and_rank(unique_raw)
        upsert_jsonl_by_key(
            config.SIGNAL_FILTERED_LOG_FILE,
            [signal.to_dict() for signal in ranked],
            key="tweet_id",
        )

        if not ranked:
            latest_brief = load_json(config.LATEST_RESEARCH_BRIEF_FILE) or load_latest_jsonl(config.RESEARCH_BRIEF_LOG_FILE)
            logger.warn("SIGNAL_ENGINE_NO_RANKED_SIGNALS", phase="SIGNALS", data={"raw_count": len(unique_raw)})
            return {
                "raw_count": len(unique_raw),
                "filtered_count": 0,
                "ranked_count": 0,
                "analyses_count": 0,
                "duration_secs": round(monotonic() - started_at, 2),
                "error_count": 0,
                "research_brief": latest_brief,
                "used_fallback_brief": bool(latest_brief),
            }

        analyses, brief = await self.brief_engine.build_brief(ranked)
        append_jsonl(config.SIGNAL_ANALYSIS_LOG_FILE, analyses)
        append_jsonl(config.RESEARCH_BRIEF_LOG_FILE, [brief])
        write_json(config.LATEST_RESEARCH_BRIEF_FILE, brief)

        logger.info(
            "SIGNAL_ENGINE_COMPLETE",
            phase="SIGNALS",
            data={
                "raw_count": len(unique_raw),
                "ranked_count": len(ranked),
                "top_insights": len(brief.get("top_insights", [])),
            },
        )
        return {
            "raw_count": len(unique_raw),
            "filtered_count": len(ranked),
            "ranked_count": len(ranked),
            "analyses_count": len(analyses),
            "duration_secs": round(monotonic() - started_at, 2),
            "error_count": 0,
            "research_brief": brief,
            "used_fallback_brief": False,
        }

    def _dedupe_by_id(self, signals: Sequence[SignalTweet]) -> List[SignalTweet]:
        seen = {}
        for signal in signals:
            seen[signal.tweet_id] = signal
        return list(seen.values())
