"""
nim_client.py - Shared NVIDIA NIM chat client helpers.

Keeps the model-call plumbing in one place so both generation and the
signal-research engine can use the same response validation logic.
"""

import json
from typing import Any, Dict, Optional, Tuple

import httpx

import config
from logger import logger


class NimAsyncClient:
    """Minimal async wrapper around NVIDIA chat completions."""

    def __init__(self, api_key: str, model: Optional[str] = None):
        self.api_key = api_key
        self.model = model or config.NVIDIA_MODEL
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def chat(
        self,
        system_message: str,
        user_message: str,
        *,
        temperature: float = 0.3,
        max_tokens: int = 512,
        phase: str = "NIM",
    ) -> Optional[str]:
        """Call the chat API and return extracted message content."""
        async with httpx.AsyncClient(timeout=float(config.LLM_TIMEOUT_SECS)) as client:
            try:
                response = await client.post(
                    config.NVIDIA_ENDPOINT,
                    headers=self.headers,
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_message},
                            {"role": "user", "content": user_message},
                        ],
                        "temperature": temperature,
                        "top_p": config.GENERATION_TOP_P,
                        "max_tokens": max_tokens,
                    },
                )
            except Exception as exc:
                logger.error("NIM_REQUEST_FAILED", phase=phase, data={"error": str(exc)})
                return None

        if response.status_code != 200:
            logger.error(
                "NIM_BAD_STATUS",
                phase=phase,
                data={"status_code": response.status_code, "response": response.text[:400]},
            )
            return None

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            logger.error(
                "NIM_INVALID_JSON",
                phase=phase,
                data={"response": response.text[:400]},
                error=exc,
            )
            return None

        content, metadata = extract_message_content(payload)
        if not is_valid_model_response(content):
            logger.warn("NIM_EMPTY_RESPONSE", phase=phase, data=metadata)
            return None
        return content


def is_valid_model_response(response: Optional[str]) -> bool:
    """Return True when a response contains non-whitespace text."""
    return bool(response and response.strip())


def extract_message_content(payload: Dict[str, Any]) -> Tuple[Optional[str], Dict[str, Any]]:
    """Extract text content from NVIDIA/OpenAI-style response payloads."""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None, {"reason": "no_choices", "top_level_keys": sorted(payload.keys())[:10]}

    choice = choices[0] or {}
    message = choice.get("message") or {}
    content = message.get("content")
    metadata = {
        "reason": "empty_content",
        "finish_reason": choice.get("finish_reason"),
        "content_type": type(content).__name__,
        "has_message": bool(message),
    }

    if isinstance(content, str):
        cleaned = content.strip()
        return (cleaned or None), metadata

    if isinstance(content, list):
        blocks = []
        for block in content:
            if isinstance(block, dict):
                text = block.get("text") or block.get("content")
                if text:
                    blocks.append(str(text).strip())
            elif isinstance(block, str) and block.strip():
                blocks.append(block.strip())

        cleaned = "\n".join(part for part in blocks if part)
        return (cleaned or None), metadata

    return None, metadata

