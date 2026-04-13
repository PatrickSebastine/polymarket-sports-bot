"""
Predictor - Generates probability predictions for sports outcomes.
Uses XGBoost when trained models exist, falls back to bookmaker odds.
"""

import os
import logging
import pickle
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MODELS_DIR = "models"


@dataclass
class Prediction:
    market_id: str
    outcome: str
    predicted_prob: float
    confidence: float  # 0-1
    source: str  # "model", "odds", "market"


class Predictor:
    def __init__(self, config: dict):
        self.config = config
        self.models: Dict[str, object] = {}
        self._load_models()

    def _load_models(self):
        """Load pre-trained XGBoost models from models/ directory."""
        if not os.path.exists(MODELS_DIR):
            return

        for fname in os.listdir(MODELS_DIR):
            if fname.endswith(".pkl"):
                try:
                    sport = fname.replace(".pkl", "").split("_")[0].upper()
                    with open(os.path.join(MODELS_DIR, fname), "rb") as f:
                        self.models[sport] = pickle.load(f)
                    logger.info(f"Loaded {sport} prediction model")
                except Exception as e:
                    logger.warning(f"Failed to load model {fname}: {e}")

    def predict(self, markets: list) -> Dict[str, List[Prediction]]:
        """Generate predictions for all markets. Returns {market_id: [Prediction]}."""
        predictions = {}

        for market in markets:
            preds = self._predict_market(market)
            if preds:
                predictions[market.market_id] = preds

        return predictions

    def _predict_market(self, market) -> Optional[List[Prediction]]:
        """Generate prediction for a single market."""
        sport = market.sport
        preds = []

        # Try model first
        if sport in self.models:
            preds = self._predict_with_model(market, self.models[sport])
        
        # Fallback: use external odds
        if not preds and hasattr(market, "external_odds") and market.external_odds:
            preds = self._predict_from_odds(market)

        # Last resort: use market prices as baseline
        if not preds:
            preds = self._predict_from_market(market)

        return preds if preds else None

    def _predict_with_model(self, market, model) -> List[Prediction]:
        """Use XGBoost model to predict outcome probabilities."""
        try:
            # TODO: Extract features from market data for model input
            # For now, this requires trained models in models/ dir
            # Feature extraction would mirror Sports-EV-Bot approach
            pass
        except Exception as e:
            logger.debug(f"Model prediction failed for {market.market_id}: {e}")
        return []

    def _predict_from_odds(self, market) -> List[Prediction]:
        """Use external bookmaker odds as predictions (vig already removed)."""
        odds = market.external_odds
        preds = []

        for outcome, prob in odds.outcomes.items():
            # Match outcome to market token
            for token in market.tokens:
                token_outcome = token["outcome"].lower()
                if outcome.lower() in token_outcome or token_outcome in outcome.lower():
                    preds.append(Prediction(
                        market_id=market.market_id,
                        outcome=token["outcome"],
                        predicted_prob=prob,
                        confidence=0.6,  # Medium confidence for odds-based
                        source="odds",
                    ))
                    break

        return preds

    def _predict_from_market(self, market) -> List[Prediction]:
        """Use Polymarket prices as baseline predictions."""
        preds = []
        for token in market.tokens:
            price = market.prices.get(token["outcome"], 0.5)
            preds.append(Prediction(
                market_id=market.market_id,
                outcome=token["outcome"],
                predicted_prob=price,
                confidence=0.3,  # Low confidence — market price IS the consensus
                source="market",
            ))
        return preds
