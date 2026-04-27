"""Tag config loader.

Reads ``portfolio_tags.json`` from the project root. The file is checked
into the repo so the same vocabulary follows the codebase across worktrees
and machines — edit it directly and restart the backend to apply.

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
