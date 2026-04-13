"""
Market Scanner - Discovers live sports markets on Polymarket via Gamma API.
Parses market questions to extract sport, teams, bet type, and lines.
"""

import re
import time
import logging
import requests
from typing import List, Dict, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

SPORT_KEYWORDS = {
    "NBA": ["nba", "basketball", "lakers", "celtics", "warriors", "nets", "bulls", "heat",
            "knicks", "bucks", "nuggets", "sixers", "clippers", "suns", "mavericks",
            "timberwolves", "thunder", "cavaliers", "celtics", "raptors", "hawks",
            "pelicans", "trail blazers", "kings", "spurs", "rockets", "pistons",
            "pacers", "magic", "hornets", "wizards", "jazz", "grizzlies"],
    "NFL": ["nfl", "football", "chiefs", "49ers", "ravens", "bills", "cowboys",
            "eagles", "packers", "rams", "bengals", "dolphins", "lions", "browns",
            "texans", "seahawks", "saints", "bears", "falcons", "jets", "giants",
            "steelers", "broncos", "colts", "chargers", "raiders", "patriots",
            "titans", "cardinals", "panthers", "commanders", "buccaneers", "vikings", "jaguars"],
    "NHL": ["nhl", "hockey", "oilers", "avalanche", "panthers", "rangers", "maple leafs",
            "bruins", "stars", "hurricanes", "devils", "kraken", "jets", "lightning",
            "flames", "wild", "predators", "blues", "canucks", "kings", "flyers",
            "penguins", "sabres", "red wings", "senators", "canadiens", "islanders",
            "capitals", "coyotes", "sharks", "ducks", "blackhawks", "blue jackets"],
    "MLB": ["mlb", "baseball", "yankees", "dodgers", "astros", "braves", "phillies",
            "padres", "guardians", "mariners", "twins", "orioles", "rays", "rangers",
            "brewers", "cubs", "diamondbacks", "mets", "cardinals", "giants", "red sox",
            "blue jays", "white sox", "angels", "nationals", "tigers", "pirates",
            "reds", "rockies", "royals", "athletics", "marlins"],
    "TENNIS": ["tennis", "atp", "wta", "djokovic", "alcaraz", "sinner", "medvedev",
               "swiatek", "sabalenka", "gauff", "rybakina", "grand slam", "australian open",
               "french open", "wimbledon", "us open tennis"],
    "SOCCER": ["soccer", "football", "premier league", "la liga", "champions league",
               "manchester", "liverpool", "arsenal", "chelsea", "barcelona", "real madrid",
               "bayern", "psg", "mls", "world cup", "euro"],
    "UFC": ["ufc", "mma", "fight", "bellator", "boxing"],
}

BET_TYPE_PATTERNS = {
    "moneyline": r"(?:win|beat|defeat|moneyline|ml)",
    "spread": r"(?:spread|points?\s*[+-]\s*\d+|-\d+\.?\d*|plus\s+\d+)",
    "total_over": r"(?:over\s+\d+\.?\d*|total.*over|o\s*\d+\.?\d*)",
    "total_under": r"(?:under\s+\d+\.?\d*|total.*under|u\s*\d+\.?\d*)",
    "player_props": r"(?:points|rebounds|assists|yards|touchdowns|goals|hits|strikeouts"
                    r"|passing|rushing|receiving|3-pointers|blocks|steals|turnovers)",
}


@dataclass
class SportsMarket:
    """Parsed sports market from Polymarket."""
    market_id: str
    question: str
    slug: str
    sport: str
    bet_type: str
    tokens: List[Dict[str, str]]  # [{token_id, outcome}]
    end_date: str
    liquidity: float = 0.0
    prices: Dict[str, float] = field(default_factory=dict)
    accepting_orders: bool = True
    raw_data: Dict = field(default_factory=dict)

    @property
    def token_ids(self) -> List[str]:
        return [t["token_id"] for t in self.tokens]

    @property
    def is_live(self) -> bool:
        return self.accepting_orders and self.liquidity >= 100

    def time_remaining_seconds(self) -> float:
        if not self.end_date:
            return float("inf")
        try:
            end_str = self.end_date.replace("Z", "+00:00")
            end_time = datetime.fromisoformat(end_str)
            remaining = (end_time - datetime.now(timezone.utc)).total_seconds()
            return max(0, remaining)
        except Exception:
            return float("inf")


class MarketScanner:
    def __init__(self, config: dict):
        self.config = config
        self.gamma_url = config.get("polymarket", {}).get(
            "gamma_url", "https://gamma-api.polymarket.com"
        )
        self.enabled_sports = [s.upper() for s in config.get("sports", {}).get("enabled", ["NBA", "NFL", "NHL", "TENNIS"])]
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        self._cache: List[SportsMarket] = []
        self._cache_time: float = 0
        self._cache_ttl: float = config.get("sports", {}).get("scan_cache_ttl", 30)

    def scan(self) -> List[SportsMarket]:
        """Scan for live sports markets. Returns cached results if fresh."""
        now = time.time()
        if self._cache and now - self._cache_time < self._cache_ttl:
            return self._cache

        markets = self._fetch_sports_markets()
        self._cache = markets
        self._cache_time = now
        logger.info(f"Scanned {len(markets)} live sports markets")
        return markets

    def _fetch_sports_markets(self) -> List[SportsMarket]:
        """Fetch and parse sports markets from Gamma API."""
        all_markets = []

        try:
            # Fetch active markets
            url = f"{self.gamma_url}/markets"
            params = {
                "closed": "false",
                "active": "true",
                "limit": 200,
                "order": "volume",
                "ascending": "false",
            }
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            if isinstance(data, dict):
                data = data.get("data", data.get("markets", []))
            if not isinstance(data, list):
                data = []

        except Exception as e:
            logger.error(f"Gamma API fetch failed: {e}")
            return self._cache  # Return stale cache on error

        for m in data:
            market = self._parse_market(m)
            if market and market.sport in self.enabled_sports and market.is_live:
                all_markets.append(market)

        return all_markets

    def _parse_market(self, raw: dict) -> Optional[SportsMarket]:
        """Parse raw Gamma API market into SportsMarket."""
        question = raw.get("question", "")
        slug = raw.get("slug", "")
        condition_id = raw.get("conditionId", raw.get("condition_id", ""))

        if not question or not condition_id:
            return None

        # Detect sport
        sport = self._detect_sport(question)
        if not sport:
            return None

        # Detect bet type
        bet_type = self._detect_bet_type(question)

        # Parse tokens
        tokens = []
        outcomes = raw.get("outcomes", [])
        prices = raw.get("outcomePrices", "")
        token_data = raw.get("clobTokenIds", "")

        if isinstance(outcomes, str):
            try:
                import json
                outcomes = json.loads(outcomes)
            except Exception:
                outcomes = []
        if isinstance(prices, str):
            try:
                import json
                prices = json.loads(prices)
            except Exception:
                prices = []
        if isinstance(token_data, str):
            try:
                import json
                token_data = json.loads(token_data)
            except Exception:
                token_data = []

        price_list = prices if isinstance(prices, list) else []
        token_list = token_data if isinstance(token_data, list) else []
        outcome_list = outcomes if isinstance(outcomes, list) else []

        for i, outcome in enumerate(outcome_list):
            token_id = token_list[i] if i < len(token_list) else ""
            price = float(price_list[i]) if i < len(price_list) else 0.5
            tokens.append({"token_id": token_id, "outcome": str(outcome)})
            if token_id:
                # prices keyed by outcome name for easy lookup

        prices_dict = {}
        for i, t in enumerate(tokens):
            if i < len(price_list):
                prices_dict[t["outcome"]] = float(price_list[i])

        # Calculate total liquidity (volume as proxy)
        volume = float(raw.get("volume", 0) or 0)
        liquidity = float(raw.get("liquidity", 0) or 0)
        if liquidity == 0:
            liquidity = volume  # fallback to volume

        return SportsMarket(
            market_id=condition_id,
            question=question,
            slug=slug,
            sport=sport,
            bet_type=bet_type,
            tokens=tokens,
            end_date=raw.get("endDate", raw.get("end_date", "")),
            liquidity=liquidity,
            prices=prices_dict,
            accepting_orders=raw.get("acceptingOrders", True),
            raw_data=raw,
        )

    def _detect_sport(self, text: str) -> Optional[str]:
        text_lower = text.lower()
        for sport, keywords in SPORT_KEYWORDS.items():
            for kw in keywords:
                if kw in text_lower:
                    return sport
        return None

    def _detect_bet_type(self, text: str) -> str:
        text_lower = text.lower()
        for bet_type, pattern in BET_TYPE_PATTERNS.items():
            if re.search(pattern, text_lower):
                return bet_type
        return "unknown"
