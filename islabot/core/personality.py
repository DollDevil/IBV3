from __future__ import annotations
import json
import os
from typing import Any

from core.isla_text import sanitize_isla_text
from core.tone import DEFAULT_POOLS

class Personality:
    """
    Loads tone pools from a JSON file. If file missing/invalid, uses fallback.
    File format example:
    {
      "balance": { "stage_0": ["..."], "stage_1": ["..."] },
      "daily":   { "stage_0": ["..."], ... }
    }
    """
    def __init__(self, path: str, fallback: dict[str, Any]):
        self.path = path
        self.fallback = fallback
        self.pools = fallback
        self.last_mtime = 0.0

    def load(self) -> tuple[bool, str]:
        """Load personality from file. Returns (success, message)."""
        if not os.path.exists(self.path):
            self.pools = self.fallback
            return False, "personality file missing; using fallback"

        try:
            mtime = os.path.getmtime(self.path)
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("Root must be object/dict")
            self.pools = data
            self.last_mtime = mtime
            return True, "loaded"
        except Exception as e:
            self.pools = self.fallback
            return False, f"failed to load; fallback used: {e}"

    def maybe_reload(self) -> bool:
        """Check if file changed and reload if needed. Returns True if reloaded."""
        try:
            if not os.path.exists(self.path):
                return False
            mtime = os.path.getmtime(self.path)
            if mtime > self.last_mtime:
                self.load()
                return True
        except Exception:
            pass
        return False

    def sanitize(self):
        """Sanitize all strings in pools."""
        for k, block in list(self.pools.items()):
            if not isinstance(block, dict):
                continue
            for stage, lines in list(block.items()):
                if isinstance(lines, list):
                    block[stage] = [sanitize_isla_text(str(x)) for x in lines]

