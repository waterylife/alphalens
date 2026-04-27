"""Shared MiniMax LLM rationale helper for strategy signals.

Environment variables:
  MINIMAX_API_KEY   – required; absent → returns None (template fallback)
  MINIMAX_MODEL     – default: MiniMax-M2 (reasoning model)
  MINIMAX_API_BASE  – default: https://api.minimax.chat/v1
"""

from __future__ import annotations

import os
import re
from typing import Callable

import requests

from backend.data.cache import cache

TTL_LLM = 60 * 60 * 12  # 12 h

_MINIMAX_MODEL    = os.environ.get("MINIMAX_MODEL", "MiniMax-M2")
_MINIMAX_API_BASE = os.environ.get("MINIMAX_API_BASE", "https://api.minimax.chat/v1")

# M2 is a reasoning model → response is "<think>...</think>\nActual answer".
_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


def call_minimax(prompt: str) -> str | None:
    """Single MiniMax call. Returns cleaned Chinese text or None on failure."""
    api_key = os.environ.get("MINIMAX_API_KEY")
    if not api_key:
        return None
    try:
        resp = requests.post(
            f"{_MINIMAX_API_BASE}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": _MINIMAX_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 2000,
                "temperature": 0.3,
            },
            timeout=60,
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]
        text = _THINK_RE.sub("", raw).strip()
        return text or None
    except Exception:
        return None


def cached_rationale(namespace: str, key: str, prompt_builder: Callable[[], str]) -> str | None:
    """Cache-wrapped LLM call. prompt_builder only invoked on cache miss."""
    def _fetch() -> str | None:
        return call_minimax(prompt_builder())
    try:
        return cache.fetch(namespace, key, TTL_LLM, _fetch)
    except Exception:
        return None
