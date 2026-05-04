"""Shared LLM helpers for strategy signals and analysis agents.

Environment variables:
  MINIMAX_API_KEY   – required; absent → returns None (template fallback)
  MINIMAX_MODEL     – default: MiniMax-M2 (reasoning model)
  MINIMAX_API_BASE  – default: https://api.minimax.chat/v1
  GEMINI_API_KEY    – required for Gemini calls; absent → returns None
  GEMINI_MODEL      – default: gemini-2.5-flash
  GEMINI_API_HOST   – default: https://generativelanguage.googleapis.com
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
_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
_GEMINI_API_HOST = os.environ.get("GEMINI_API_HOST", "https://generativelanguage.googleapis.com")

# M2 is a reasoning model → response is "<think>...</think>\nActual answer".
_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)
_BAD_RATIONALE_RE = re.compile(
    r"(无法满足|不能满足|抱歉|对不起|无法提供|不能提供|无法协助|不能协助|"
    r"cannot\s+(comply|fulfill|satisfy)|sorry)",
    re.IGNORECASE,
)


def usable_rationale(text: str | None) -> str | None:
    """Return cleaned rationale text only if it is suitable for the UI."""
    if not text:
        return None
    cleaned = _THINK_RE.sub("", text).strip()
    if not cleaned:
        return None
    if _BAD_RATIONALE_RE.search(cleaned):
        return None
    return cleaned


def call_minimax(prompt: str, *, max_tokens: int = 2000, temperature: float = 0.3) -> str | None:
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
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=60,
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]
        return usable_rationale(raw)
    except Exception:
        return None


def call_gemini(prompt: str, *, max_tokens: int = 2000, temperature: float = 0.3) -> str | None:
    """Single Gemini generateContent call. Returns cleaned Chinese text or None on failure."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        resp = requests.post(
            f"{_GEMINI_API_HOST.rstrip('/')}/v1beta/models/{_GEMINI_MODEL}:generateContent",
            params={"key": api_key},
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": max_tokens,
                },
            },
            timeout=90,
        )
        resp.raise_for_status()
        payload = resp.json()
        parts = payload["candidates"][0]["content"]["parts"]
        raw = "\n".join(part.get("text", "") for part in parts if isinstance(part, dict)).strip()
        return usable_rationale(raw)
    except Exception:
        return None


def cached_rationale(namespace: str, key: str, prompt_builder: Callable[[], str]) -> str | None:
    """Cache-wrapped LLM call. prompt_builder only invoked on cache miss."""
    def _fetch() -> str | None:
        return call_minimax(prompt_builder())
    try:
        return usable_rationale(cache.fetch(namespace, key, TTL_LLM, _fetch))
    except Exception:
        return None
