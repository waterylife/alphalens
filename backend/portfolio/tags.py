"""Tag config loader.

Reads and writes ``portfolio_tags.json`` from the project root. The file is
checked into the repo so the same vocabulary follows the codebase across
worktrees and machines.

Override the path with the ``PORTFOLIO_TAGS_CONFIG`` env var if you want a
machine-local copy outside the repo.

Reads are cached for one process lifetime; restart to pick up edits.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path


_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "portfolio_tags.json"
_LIVE_PATH = Path(os.environ.get("PORTFOLIO_TAGS_CONFIG", _DEFAULT_PATH))


@lru_cache(maxsize=1)
def load_tags() -> dict[str, list[str]]:
    if not _LIVE_PATH.exists():
        return {"tag_l1": [], "tag_l2": []}
    with _LIVE_PATH.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return {
        "tag_l1": list(data.get("tag_l1") or []),
        "tag_l2": list(data.get("tag_l2") or []),
    }


def reload_tags() -> dict[str, list[str]]:
    load_tags.cache_clear()
    return load_tags()


def save_tags(data: dict[str, list[str]]) -> dict[str, list[str]]:
    _LIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cleaned = {
        "tag_l1": _clean_values(data.get("tag_l1") or []),
        "tag_l2": _clean_values(data.get("tag_l2") or []),
    }
    with _LIVE_PATH.open("w", encoding="utf-8") as fh:
        json.dump(cleaned, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    load_tags.cache_clear()
    return cleaned


def _clean_values(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out
