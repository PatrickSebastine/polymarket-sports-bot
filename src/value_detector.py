"""
Value Detector - Finds mispriced markets by comparing predictions vs prices.
Only surfaces opportunities with sufficient edge and liquidity.
"""

import logging
from typing import List, Dict
from dataclasses import dataclass

from src.predictor import Prediction

logger = logging.getLogger(__name__)


@dataclass
class Opportunity:
    market_id: str
    question: str
    sport: str
    bet_type: str
    outcome: str
    token_id: str
    predicted_prob: float
    market_price: float
    edge: float  # predicted_prob - market_price
    confidence: float
    expected_value: float  # edge * confidence
    liquidity: float
    end_date: str


class ValueDetector:
    def __init__(self, config: dict):
        self.min_edge = config.get("min_edge", 0.05)  # 5% minimum edge
        self.min_confidence = config.get("min_confidence", 0.4)
        self.min_liquidity = config.get("min_liquidity", 100)
        self.no_trade_before_expiry_minutes = config.get(
            "no_trade_before_expiry_minutes", 5
        )

    def find_value(
        self,
        predictions: Dict[str, List[Prediction]],
        markets: list,
    ) -> List[Opportunity]:
        """Find all value opportunities across markets."""
        opportunities = []
        market_map = {m.market_id: m for m in markets}

        for market_id, preds in predictions.items():
            market = market_map.get(market_id)
            if not market:
                continue

            # Skip markets ending soon
            if market.time_remaining_seconds() < self.no_trade_before_expiry_minutes * 60:
                continue

            # Skip illiquid markets
            if market.liquidity < self.min_liquidity:
                continue

            for pred in preds:
                # Find token for this outcome
                token_id = None
                for t in market.tokens:
                    if t["outcome"] == pred.outcome:
                        token_id = t["token_id"]
                        break

                if not token_id:
                    continue

                market_price = market.prices.get(pred.outcome, 0.5)
                edge = pred.predicted_prob - market_price

                # Only trade if our model says YES but market is cheap
                # (positive edge = market underprices this outcome)
                if edge < self.min_edge:
                    continue

                if pred.confidence < self.min_confidence:
                    continue

                ev = edge * pred.confidence

                opportunities.append(Opportunity(
                    market_id=market_id,
                    question=market.question,
                    sport=market.sport,
                    bet_type=market.bet_type,
                    outcome=pred.outcome,
                    token_id=token_id,
                    predicted_prob=pred.predicted_prob,
                    market_price=market_price,
                    edge=edge,
                    confidence=pred.confidence,
                    expected_value=ev,
                    liquidity=market.liquidity,
                    end_date=market.end_date,
                ))

        # Sort by expected value (best first)
        opportunities.sort(key=lambda x: x.expected_value, reverse=True)
        
        if opportunities:
            logger.info(
                f"Top opportunity: {opportunities[0].question[:50]}... "
                f"edge={opportunities[0].edge:.2%} ev={opportunities[0].expected_value:.3f}"
            )

        return opportunities
