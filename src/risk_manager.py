"""
Risk Manager - Position sizing, daily loss limits, cooldowns, circuit breaker.
"""

import time
import logging
from typing import Dict, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class TradeRecord:
    market_id: str
    sport: str
    outcome: str
    size: float
    entry_price: float
    pnl: float = 0.0
    timestamp: float = 0.0
    closed: bool = False


class RiskManager:
    def __init__(self, config: dict, state):
        self.state = state
        self.daily_loss_limit = config.get("daily_loss_limit", 3.00)
        self.max_positions = config.get("max_positions", 5)
        self.max_per_sport = config.get("max_per_sport", 10.00)
        self.kelly_fraction = config.get("kelly_fraction", 0.25)
        self.max_bet_size = config.get("max_bet_size", 5.00)
        self.cooldown_seconds = config.get("cooldown_seconds", 60)
        self.no_trade_before_expiry_minutes = config.get(
            "no_trade_before_expiry_minutes", 5
        )

        # State
        self.daily_pnl: float = state.get("daily_pnl", 0.0)
        self.daily_start: float = state.get("daily_start", time.time())
        self.trade_count: int = state.get("trade_count", 0)
        self.open_positions: Dict[str, TradeRecord] = state.get(
            "open_positions", {}
        )
        self._last_trade_time: Dict[str, float] = {}  # market_id -> timestamp
        self.circuit_breaker_tripped = False

    def can_trade(self, opportunity: dict) -> bool:
        """Check if we can open a new position."""
        # Circuit breaker
        if self.circuit_breaker_tripped:
            return False

        # Daily loss check
        if self.daily_pnl <= -abs(self.daily_loss_limit):
            if not self.circuit_breaker_tripped:
                logger.error(
                    f"CIRCUIT BREAKER: daily loss ${self.daily_pnl:+.2f} "
                    f"exceeds limit -${self.daily_loss_limit:.2f}"
                )
                self.circuit_breaker_tripped = True
            return False

        # Max positions
        open_count = sum(1 for p in self.open_positions.values() if not p.closed)
        if open_count >= self.max_positions:
            return False

        # Max per sport exposure
        sport = opportunity.get("sport", "")
        sport_exposure = sum(
            p.size
            for p in self.open_positions.values()
            if not p.closed and p.sport == sport
        )
        if sport_exposure >= self.max_per_sport:
            return False

        return True

    def check_cooldown(self, market_id: str) -> bool:
        """Check cooldown for a specific market. Returns True if OK to trade."""
        last = self._last_trade_time.get(market_id, 0)
        if time.time() - last < self.cooldown_seconds:
            return False
        return True

    def calculate_size(self, edge: float, confidence: float) -> float:
        """Calculate position size using fractional Kelly criterion."""
        if edge <= 0:
            return 0.0
        # Kelly: f = (bp - q) / b where b = payout ratio, p = our prob, q = 1-p
        # Simplified: size = edge * kelly_fraction * confidence
        raw_kelly = edge * self.kelly_fraction * confidence
        size = min(raw_kelly * 100, self.max_bet_size)  # Scale to USDC
        return max(min(size, self.max_bet_size), 0.50)  # Min 50 cents

    def record_trade(self, opportunity: dict, result: dict):
        """Record a new trade."""
        market_id = opportunity.get("market_id", "")
        size = result.get("size", opportunity.get("size", 1.0))
        price = result.get("fill_price", opportunity.get("market_price", 0.5))

        trade = TradeRecord(
            market_id=market_id,
            sport=opportunity.get("sport", ""),
            outcome=opportunity.get("outcome", ""),
            size=size,
            entry_price=price,
            timestamp=time.time(),
        )

        self.open_positions[market_id] = trade
        self._last_trade_time[market_id] = time.time()
        self.trade_count += 1

        # Persist
        self.state.set("daily_pnl", self.daily_pnl)
        self.state.set("trade_count", self.trade_count)
        self.state.set("open_positions", self.open_positions)

    def record_close(self, market_id: str, pnl: float):
        """Record a closed position."""
        if market_id in self.open_positions:
            self.open_positions[market_id].closed = True
            self.open_positions[market_id].pnl = pnl
            self.daily_pnl += pnl
            self.state.set("daily_pnl", self.daily_pnl)

        # Reset circuit breaker at day boundary
        if time.time() - self.daily_start > 86400:
            self.daily_pnl = 0.0
            self.daily_start = time.time()
            self.circuit_breaker_tripped = False

    def daily_summary(self) -> str:
        """Get daily summary for notifications."""
        open_count = sum(1 for p in self.open_positions.values() if not p.closed)
        return (
            f"Trades: {self.trade_count} | "
            f"Open: {open_count} | "
            f"P&L: ${self.daily_pnl:+.2f} | "
            f"Circuit breaker: {'YES' if self.circuit_breaker_tripped else 'no'}"
        )
