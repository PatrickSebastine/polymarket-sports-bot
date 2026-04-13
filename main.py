"""
Polymarket Sports Betting Bot - Main Entry Point
Fully autonomous sports trading on Polymarket prediction markets.
"""

import asyncio
import os
import sys
import signal
import logging
import yaml
import time
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()

from src.market_scanner import MarketScanner
from src.data_pipeline import DataPipeline
from src.predictor import Predictor
from src.value_detector import ValueDetector
from src.executor import TradeExecutor
from src.risk_manager import RiskManager
from src.notifier import Notifier
from src.state import StateManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("sports_bot")


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


class SportsBot:
    def __init__(self, config: dict):
        self.config = config
        self.running = False

        # Components
        self.state = StateManager("data/state.json")
        self.notifier = Notifier(config.get("notifications", {}))
        self.risk = RiskManager(config.get("risk", {}), self.state)
        self.scanner = MarketScanner(config)
        self.pipeline = DataPipeline(config.get("data", {}))
        self.predictor = Predictor(config)
        self.detector = ValueDetector(config.get("sports", {}))
        self.executor = TradeExecutor(config.get("polymarket", {}), self.state)

        self.scan_interval = config.get("scan_interval", 60)
        self.notifier.notify("🟢 Sports bot started")

    async def run(self):
        self.running = True
        logger.info("Sports bot starting...")

        while self.running:
            try:
                # Check circuit breaker
                if self.risk.circuit_breaker_tripped:
                    logger.warning("Circuit breaker active — skipping scan")
                    await asyncio.sleep(60)
                    continue

                # 1. Discover sports markets
                markets = await asyncio.to_thread(self.scanner.scan)
                if not markets:
                    logger.debug("No sports markets found")
                    await asyncio.sleep(self.scan_interval)
                    continue

                logger.info(f"Found {len(markets)} sports markets")

                # 2. Enrich with external data
                enriched = await asyncio.to_thread(self.pipeline.enrich, markets)

                # 3. Generate predictions
                predictions = await asyncio.to_thread(self.predictor.predict, enriched)

                # 4. Find value bets
                opportunities = self.detector.find_value(predictions, enriched)

                if not opportunities:
                    logger.debug("No value opportunities found")
                    await asyncio.sleep(self.scan_interval)
                    continue

                logger.info(f"Found {len(opportunities)} value opportunities")

                # 5. Execute trades (risk-checked)
                for opp in opportunities:
                    if not self.risk.can_trade(opp):
                        continue

                    if not self.risk.check_cooldown(opp["market_id"]):
                        continue

                    result = await self.executor.execute(opp)
                    if result.get("success"):
                        self.risk.record_trade(opp, result)
                        self.state.save()
                        self.notifier.notify_trade(opp, result)

                await asyncio.sleep(self.scan_interval)

            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Main loop error: {e}", exc_info=True)
                self.notifier.notify(f"🔴 Error: {e}")
                await asyncio.sleep(30)

        await self.shutdown()

    async def shutdown(self):
        self.running = False
        self.state.save()
        summary = self.risk.daily_summary()
        self.notifier.notify(f"🔴 Sports bot stopped\n{summary}")
        logger.info("Bot shut down cleanly")


def main():
    config = load_config()

    # Override with env vars
    private_key = os.environ.get("POLY_PRIVATE_KEY")
    safe_address = os.environ.get("POLY_SAFE_ADDRESS")
    odds_key = os.environ.get("ODDS_API_KEY")

    if not private_key or not safe_address:
        print("ERROR: Set POLY_PRIVATE_KEY and POLY_SAFE_ADDRESS env vars")
        sys.exit(1)

    config.setdefault("polymarket", {})
    config["polymarket"]["private_key"] = private_key
    config["polymarket"]["safe_address"] = safe_address
    if odds_key:
        config.setdefault("data", {})["odds_api_key"] = odds_key

    Path("logs").mkdir(exist_ok=True)
    Path("data").mkdir(exist_ok=True)
    Path("models").mkdir(exist_ok=True)

    bot = SportsBot(config)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.ensure_future(bot.shutdown()))

    try:
        loop.run_until_complete(bot.run())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
