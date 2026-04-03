"""Load creator and search targets for the signal engine."""

import json
import random
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import config
from ingestion.models import CreatorTarget


def load_signal_sources(path: str = config.SIGNAL_SOURCES_FILE) -> Dict[str, List]:
    with open(Path(path), "r", encoding="utf-8") as handle:
        raw = json.load(handle)

    core = [
        CreatorTarget(
            display_name=item["display_name"],
            username=item["username"],
            tier="core",
            enabled=item.get("enabled", True),
        )
        for item in raw.get("core_creators", [])
        if item.get("enabled", True) and item.get("username")
    ]
    rotating = [
        CreatorTarget(
            display_name=item["display_name"],
            username=item["username"],
            tier="rotating",
            enabled=item.get("enabled", True),
        )
        for item in raw.get("rotating_creators", [])
        if item.get("enabled", True) and item.get("username")
    ]

    queries = [query for query in raw.get("search_queries", []) if query]
    return {"core_creators": core, "rotating_creators": rotating, "search_queries": queries}


def build_run_targets(now: datetime | None = None) -> Dict[str, List]:
    now = now or datetime.utcnow()
    sources = load_signal_sources()
    run_slot = now.hour // 3

    core = sources["core_creators"][: config.SIGNAL_CORE_CREATORS_PER_RUN]

    rotating_pool = sources["rotating_creators"]
    rotating_count = min(config.SIGNAL_ROTATING_CREATORS_PER_RUN, len(rotating_pool))
    start_index = (run_slot * rotating_count) % len(rotating_pool) if rotating_pool and rotating_count else 0

    rotating: List[CreatorTarget] = []
    if rotating_pool and rotating_count:
        for offset in range(rotating_count):
            rotating.append(rotating_pool[(start_index + offset) % len(rotating_pool)])

    creators = core + rotating
    random.shuffle(creators)

    queries: List[str] = []
    if config.SIGNAL_ENABLE_SEARCH and sources["search_queries"]:
        if run_slot % max(config.SIGNAL_SEARCH_RUN_INTERVAL, 1) == 0:
            queries = sources["search_queries"][: config.SIGNAL_SEARCH_QUERIES_PER_RUN]
            random.shuffle(queries)

    return {
        "creators": [asdict(target) for target in creators],
        "search_queries": queries,
        "run_slot": run_slot,
    }

