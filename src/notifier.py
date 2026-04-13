"""
Notifier - Push notifications via ntfy.sh.
No API key needed, just HTTP POST.
"""

import logging
import requests

logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self, config: dict):
        self.enabled = config.get("enabled", True)
        self.topic = config.get("ntfy_topic", "poly-sports-bot")
        self.url = f"https://ntfy.sh/{self.topic}"
        self.session = requests.Session()

    def notify(self, message: str):
        """Send a push notification."""
        if not self.enabled:
            return
        try:
            self.session.post(
                self.url,
                data=message.encode("utf-8"),
                headers={"Title": "Sports Bot", "Priority": "default"},
                timeout=5,
            )
        except Exception as e:
            logger.debug(f"Notification failed: {e}")

    def notify_trade(self, opportunity: dict, result: dict):
        """Send trade notification."""
        outcome = opportunity.get("outcome", "")
        edge = opportunity.get("edge", 0)
        sport = opportunity.get("sport", "")
        question = opportunity.get("question", "")[:60]
        size = result.get("size", opportunity.get("size", 1.0))

        msg = (
            f"📈 BUY {sport}: {outcome}\n"
            f"{question}...\n"
            f"Edge: {edge:.1%} | Size: ${size:.2f}"
        )
        self.notify(msg)

    def notify_error(self, error: str):
        """Send error notification."""
        self.notify(f"🔴 ERROR: {error}")
