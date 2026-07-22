"""Persistent state so the watcher only emails genuinely new activity."""
from __future__ import annotations

import json
import os
from typing import Any


class State:
    def __init__(self, path: str):
        self.path = path
        self._data: dict[str, Any] = {"initialized": False, "issues": {}}
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as fh:
                    self._data = json.load(fh)
            except (json.JSONDecodeError, OSError):
                pass
        self._data.setdefault("initialized", False)
        self._data.setdefault("issues", {})

    def save(self) -> None:
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self._data, fh, indent=2)
        os.replace(tmp, self.path)

    # -- flags --------------------------------------------------------------
    @property
    def initialized(self) -> bool:
        return bool(self._data.get("initialized"))

    def mark_initialized(self) -> None:
        self._data["initialized"] = True

    # -- per-issue accessors ------------------------------------------------
    def _issue(self, key: str) -> dict[str, Any]:
        return self._data["issues"].setdefault(
            key,
            {"last_comment_id": None, "last_comment_time": None, "status_category": None, "rca_sent": False},
        )

    def knows(self, key: str) -> bool:
        return key in self._data["issues"]

    def known_keys(self) -> set[str]:
        return set(self._data["issues"].keys())

    def last_comment_time(self, key: str) -> str | None:
        return self._issue(key).get("last_comment_time")

    def last_comment_id(self, key: str) -> str | None:
        return self._issue(key).get("last_comment_id")

    def set_last_comment(self, key: str, comment_id: str | None, created: str | None) -> None:
        issue = self._issue(key)
        issue["last_comment_id"] = comment_id
        issue["last_comment_time"] = created

    def status_category(self, key: str) -> str | None:
        return self._issue(key).get("status_category")

    def set_status_category(self, key: str, category: str) -> None:
        self._issue(key)["status_category"] = category

    def rca_sent(self, key: str) -> bool:
        return bool(self._issue(key).get("rca_sent"))

    def mark_rca_sent(self, key: str) -> None:
        self._issue(key)["rca_sent"] = True

    def set_rca_sent(self, key: str, value: bool) -> None:
        self._issue(key)["rca_sent"] = value
