"""
Shared GetXAPI helpers for posting and reading tweet data.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

import config
from logger import logger


class GetXAPIError(Exception):
    """Raised when GetXAPI returns an error payload or HTTP status."""


_cached_auth_token: Optional[str] = None


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {config.GETXAPI_API_KEY}",
        "Content-Type": "application/json",
    }


def _extract_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except Exception:
        return response.text.strip() or f"HTTP {response.status_code}"

    if isinstance(payload, dict):
        return (
            payload.get("error")
            or payload.get("message")
            or payload.get("msg")
            or str(payload)
        )
    return str(payload)


def _extract_auth_token(payload: Dict[str, Any]) -> Optional[str]:
    if not isinstance(payload, dict):
        return None

    data = payload.get("data")
    candidates = [
        payload.get("auth_token"),
        payload.get("authToken"),
        data.get("auth_token") if isinstance(data, dict) else None,
        data.get("authToken") if isinstance(data, dict) else None,
        data.get("cookies", {}).get("auth_token")
        if isinstance(data, dict) and isinstance(data.get("cookies"), dict)
        else None,
    ]
    for candidate in candidates:
        if candidate:
            return candidate
    return None


def _login_payload() -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "userName": config.GETXAPI_USERNAME,
        "password": config.GETXAPI_PASSWORD,
    }
    if config.GETXAPI_EMAIL:
        payload["email"] = config.GETXAPI_EMAIL
    if config.GETXAPI_TOTP_SECRET:
        payload["totp_secret"] = config.GETXAPI_TOTP_SECRET
    if config.GETXAPI_PROXY:
        payload["proxy"] = config.GETXAPI_PROXY
    return payload


async def get_auth_token_async() -> str:
    global _cached_auth_token

    if _cached_auth_token:
        return _cached_auth_token
    if config.GETXAPI_AUTH_TOKEN:
        _cached_auth_token = config.GETXAPI_AUTH_TOKEN
        return _cached_auth_token

    if not config.GETXAPI_USERNAME or not config.GETXAPI_PASSWORD:
        raise GetXAPIError(
            "GetXAPI posting requires GETXAPI_AUTH_TOKEN or GETXAPI_USERNAME/GETXAPI_PASSWORD."
        )

    async with httpx.AsyncClient(timeout=config.POSTER_TIMEOUT_SECS) as client:
        response = await client.post(
            f"{config.GETXAPI_BASE_URL}/twitter/user_login",
            headers=_headers(),
            json=_login_payload(),
        )

    if response.status_code >= 400:
        raise GetXAPIError(_extract_error(response))

    payload = response.json()
    auth_token = _extract_auth_token(payload)
    if not auth_token:
        raise GetXAPIError("GetXAPI login succeeded but no auth_token was returned.")

    _cached_auth_token = auth_token
    logger.info("Fetched GetXAPI auth token via login", phase="SYSTEM")
    return auth_token


def get_auth_token_sync() -> str:
    global _cached_auth_token

    if _cached_auth_token:
        return _cached_auth_token
    if config.GETXAPI_AUTH_TOKEN:
        _cached_auth_token = config.GETXAPI_AUTH_TOKEN
        return _cached_auth_token

    if not config.GETXAPI_USERNAME or not config.GETXAPI_PASSWORD:
        raise GetXAPIError(
            "GetXAPI posting requires GETXAPI_AUTH_TOKEN or GETXAPI_USERNAME/GETXAPI_PASSWORD."
        )

    with httpx.Client(timeout=config.POSTER_TIMEOUT_SECS) as client:
        response = client.post(
            f"{config.GETXAPI_BASE_URL}/twitter/user_login",
            headers=_headers(),
            json=_login_payload(),
        )

    if response.status_code >= 400:
        raise GetXAPIError(_extract_error(response))

    payload = response.json()
    auth_token = _extract_auth_token(payload)
    if not auth_token:
        raise GetXAPIError("GetXAPI login succeeded but no auth_token was returned.")

    _cached_auth_token = auth_token
    logger.info("Fetched GetXAPI auth token via login", phase="SYSTEM")
    return auth_token


def build_post_payload(text: str, reply_to_tweet_id: Optional[str] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "auth_token": config.GETXAPI_AUTH_TOKEN or _cached_auth_token,
        "text": text,
    }
    if reply_to_tweet_id:
        payload["reply_to_tweet_id"] = str(reply_to_tweet_id)
    if config.GETXAPI_PROXY:
        payload["proxy"] = config.GETXAPI_PROXY
    return payload


def api_headers() -> Dict[str, str]:
    return _headers()
