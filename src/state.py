"""
State Manager - Persistent state storage in JSON.
Survives bot restarts. Tracks positions, P&L, trade history.
"""

import json
import os
import logging
import time
from typing import Any, Dict
from pathlib import Path

logger = logging.getLogger(__name__)


class StateManager:
    def __init__(self, path: str = "data/state.json"):
        self.path = path
        self._data: Dict[str, Any] = {}
        self._load()

    def _load(self):
        """Load state from disk."""
        try:
            if os.path.exists(self.path):
                with open(self.path) as f:
                    self._data = json.load(f)
                logger.debug(f"State loaded from {self.path}")
            else:
                self._data = {
                    "daily_pnl": 0.0,
                    "daily_start": time.time(),
                    "trade_count": 0,
                    "open_positions": {},
                    "trade_history": [],
                }
                self.save()
        except Exception as e:
            logger.warning(f"State load failed, starting fresh: {e}")
            self._data = {}

    def save(self):
        """Persist state to disk."""
        try:
            Path(os.path.dirname(self.path)).mkdir(parents=True, exist_ok=True)
            with open(self.path, "w") as f:
                json.dump(self._data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"State save failed: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any):
        self._data[key] = value

    def append_history(self, trade: dict):
        """Append trade to history (keep last 1000)."""
        history = self._data.setdefault("trade_history", [])
        history.append(trade)
        if len(history) > 1000:
            self._data["trade_history"] = history[-1000:]
