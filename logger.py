"""
logger.py — Structured Logging System

All events logged as JSON for auditability and analysis.
Logs to both stdout and daily JSONL files.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Dict

import config


class StructuredLogger:
    """Log all events with phase, level, timestamp, and context."""

    def __init__(self, log_dir: str = config.LOG_DIR):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)

    def _log(
        self,
        level: str,
        event: str,
        phase: str = "SYSTEM",
        data: Optional[Dict[str, Any]] = None,
        tweet_id: Optional[str] = None,
        error: Optional[Exception] = None,
    ) -> None:
        """Internal log function."""
        
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level,
            "phase": phase,
            "event": event,
            "data": data or {},
            "tweet_id": tweet_id,
        }

        if error:
            log_entry["error"] = {
                "type": error.__class__.__name__,
                "message": str(error),
            }

        # Print to stdout
        print(json.dumps(log_entry), file=sys.stdout)

        # Write to daily JSONL file
        log_file = self.log_dir / f"xbot_{datetime.utcnow().strftime('%Y-%m-%d')}.jsonl"
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
        except IOError as e:
            print(f"ERROR: Failed to write to log file {log_file}: {e}", file=sys.stderr)

    def info(
        self,
        event: str,
        phase: str = "SYSTEM",
        data: Optional[Dict[str, Any]] = None,
        tweet_id: Optional[str] = None,
    ) -> None:
        """Log informational message."""
        self._log("INFO", event, phase, data, tweet_id)

    def warn(
        self,
        event: str,
        phase: str = "SYSTEM",
        data: Optional[Dict[str, Any]] = None,
        tweet_id: Optional[str] = None,
    ) -> None:
        """Log warning message."""
        self._log("WARN", event, phase, data, tweet_id)

    def error(
        self,
        event: str,
        phase: str = "SYSTEM",
        data: Optional[Dict[str, Any]] = None,
        tweet_id: Optional[str] = None,
        error: Optional[Exception] = None,
    ) -> None:
        """Log error message."""
        self._log("ERROR", event, phase, data, tweet_id, error)

    def debug(
        self,
        event: str,
        phase: str = "SYSTEM",
        data: Optional[Dict[str, Any]] = None,
        tweet_id: Optional[str] = None,
    ) -> None:
        """Log debug message."""
        if config.LOG_LEVEL == "DEBUG":
            self._log("DEBUG", event, phase, data, tweet_id)


# Global logger instance
logger = StructuredLogger()
