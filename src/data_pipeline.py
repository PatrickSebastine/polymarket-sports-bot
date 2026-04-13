"""
Data Pipeline - Fetches external odds and data for value comparison.
Sources: the-odds-api, PrizePicks, ESPN injuries.
"""

import time
import logging
import requests
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# American odds to implied probability
def american_to_probability(odds: int) -> float:
    if odds > 0:
        return 100 / (odds + 100)
    elif odds < 0:
        return abs(odds) / (abs(odds) + 100)
    return 0.5

# Remove vig from two-way market
def remove_vig(prob_a: float, prob_b: float) -> tuple:
    total = prob_a + prob_b
    if total == 0:
        return 0.5, 0.5
    return prob_a / total, prob_b / total


@dataclass
class ExternalOdds:
    sport: str
    event: str
    outcomes: Dict[str, float]  # outcome -> true probability (vig removed)
    source: str
    timestamp: float


class DataPipeline:
    def __init__(self, config: dict):
        self.config = config
        self.odds_api_key = config.get("odds_api_key", "")
        self.cache_ttl = config.get("cache_ttl_seconds", 30)
        self.session = requests.Session()
        self._odds_cache: List[ExternalOdds] = []
        self._cache_time: float = 0

    def enrich(self, markets: list) -> list:
        """Enrich Polymarket markets with external odds data."""
        odds = self._fetch_external_odds()
        for market in markets:
            market.external_odds = self._match_odds(market, odds)
        return markets

    def _fetch_external_odds(self) -> List[ExternalOdds]:
        now = time.time()
        if self._odds_cache and now - self._cache_time < self.cache_ttl:
            return self._odds_cache

        odds = []
        if self.odds_api_key:
            odds.extend(self._fetch_the_odds_api())
        
        if not odds:
            logger.debug("No external odds available — using market prices only")

        self._odds_cache = odds
        self._cache_time = now
        return odds

    def _fetch_the_odds_api(self) -> List[ExternalOdds]:
        """Fetch odds from the-odds-api.com (free tier: 500 requests/month)."""
        odds = []
        sport_map = {
            "NBA": "basketball_nba",
            "NFL": "americanfootball_nfl",
            "NHL": "icehockey_nhl",
            "MLB": "baseball_mlb",
            "SOCCER": "soccer_epl",
            "TENNIS": "tennis_atp",
        }

        for sport, api_sport in sport_map.items():
            try:
                url = f"https://api.the-odds-api.com/v4/sports/{api_sport}/odds"
                params = {
                    "apiKey": self.odds_api_key,
                    "regions": "us",
                    "markets": "h2h,spreads,totals",
                    "oddsFormat": "american",
                }
                resp = self.session.get(url, params=params, timeout=10)
                if resp.status_code == 429:
                    logger.warning("the-odds-api rate limited")
                    continue
                resp.raise_for_status()

                for event in resp.json():
                    for bookmaker in event.get("bookmakers", []):
                        for market in bookmaker.get("markets", []):
                            outcomes = {}
                            prices = market.get("outcomes", [])
                            if len(prices) >= 2:
                                probs = []
                                for p in prices:
                                    amer_odds = p.get("price", 0)
                                    probs.append(american_to_probability(amer_odds))
                                
                                if len(probs) == 2:
                                    true_a, true_b = remove_vig(probs[0], probs[1])
                                    outcomes[prices[0].get("name", "A")] = true_a
                                    outcomes[prices[1].get("name", "B")] = true_b

                            if outcomes:
                                odds.append(ExternalOdds(
                                    sport=sport,
                                    event=event.get("home_team", ""),
                                    outcomes=outcomes,
                                    source=f"the-odds-api:{bookmaker.get('key', '')}",
                                    timestamp=time.time(),
                                ))
                logger.debug(f"Fetched {sport} odds from the-odds-api")

            except Exception as e:
                logger.debug(f"Failed to fetch {sport} odds: {e}")

        return odds

    def _match_odds(self, market, odds_list: List[ExternalOdds]) -> Optional[ExternalOdds]:
        """Match Polymarket market to external odds by sport and event keywords."""
        question = market.question.lower()
        best_match = None
        best_score = 0

        for odds in odds_list:
            if odds.sport != market.sport:
                continue

            event_lower = odds.event.lower()
            score = 0
            for word in event_lower.split():
                if len(word) > 3 and word in question:
                    score += 1

            if score > best_score:
                best_score = score
                best_match = odds

        return best_match if best_score >= 1 else None
