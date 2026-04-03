"""Data models for signal ingestion and research."""

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


@dataclass
class CreatorTarget:
    display_name: str
    username: str
    tier: str
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SignalTweet:
    tweet_id: str
    text: str
    author: str
    likes: int
    replies: int
    retweets: int
    timestamp: str
    source: str
    url: str
    query: Optional[str] = None
    scraped_at: Optional[str] = None
    creator_tier: Optional[str] = None
    rank_score: Optional[float] = None
    recency_decay: Optional[float] = None
    kept: Optional[bool] = None
    rejection_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "SignalTweet":
        return cls(**value)
