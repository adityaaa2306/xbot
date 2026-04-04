"""Shared loader for machine-readable posting cadence and fallback content policy."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import config
from logger import logger


@lru_cache(maxsize=1)
def load_content_policy() -> Dict[str, Any]:
    """Load the machine-readable content policy once per process."""
    path = Path(config.CONTENT_POLICY_PATH)
    if not path.exists():
        logger.warn(
            "CONTENT_POLICY_MISSING",
            phase="CONFIG",
            data={"path": str(path)},
        )
        return {}

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warn(
            "CONTENT_POLICY_INVALID",
            phase="CONFIG",
            data={"path": str(path), "error": str(exc)},
        )
        return {}


def reload_content_policy() -> Dict[str, Any]:
    """Clear cache and reload the policy."""
    load_content_policy.cache_clear()
    return load_content_policy()
