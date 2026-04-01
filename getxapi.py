"""
Shared GetXAPI helpers for posting and reading tweet data.
"""

from __future__ import annotations

from typing import Dict, Optional

import config


class GetXAPIError(Exception):
    """Raised when GetXAPI returns an error payload or HTTP status."""


_cached_auth_token: Optional[str] = None


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {config.GETXAPI_API_KEY}",
        "Content-Type": "application/json",
    }


async def get_auth_token_async() -> str:
    global _cached_auth_token

    if _cached_auth_token:
        return _cached_auth_token
    if config.GETXAPI_AUTH_TOKEN:
        _cached_auth_token = config.GETXAPI_AUTH_TOKEN
        return _cached_auth_token

    raise GetXAPIError("GetXAPI posting requires GETXAPI_AUTH_TOKEN.")


def get_auth_token_sync() -> str:
    global _cached_auth_token

    if _cached_auth_token:
        return _cached_auth_token
    if config.GETXAPI_AUTH_TOKEN:
        _cached_auth_token = config.GETXAPI_AUTH_TOKEN
        return _cached_auth_token

    raise GetXAPIError("GetXAPI posting requires GETXAPI_AUTH_TOKEN.")


def build_post_payload(text: str, reply_to_tweet_id: Optional[str] = None) -> Dict[str, str]:
    payload: Dict[str, str] = {
        "auth_token": config.GETXAPI_AUTH_TOKEN or _cached_auth_token,
        "text": text,
    }
    if reply_to_tweet_id:
        payload["reply_to_tweet_id"] = str(reply_to_tweet_id)
    return payload


def api_headers() -> Dict[str, str]:
    return _headers()
