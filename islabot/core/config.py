from __future__ import annotations
import yaml
from typing import Any

class Config(dict):
    @staticmethod
    def load(path: str) -> "Config":
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return Config(data)

    def get(self, *keys, default=None):
        cur: Any = self
        for k in keys:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                return default
        return cur

