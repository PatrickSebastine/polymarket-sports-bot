"""
Trade Executor - Places orders on Polymarket CLOB.
Handles order signing, placement, tracking, and cancellation.
"""

import time
import logging
import requests
from typing import Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class OrderResult:
    success: bool
    order_id: str = ""
    message: str = ""
    fill_price: float = 0.0
    timestamp: float = 0.0


class TradeExecutor:
    def __init__(self, config: dict, state):
        self.config = config
        self.state = state
        self.clob_host = config.get("clob_host", "https://clob.polymarket.com")
        self.chain_id = config.get("chain_id", 137)
        self.safe_address = config.get("safe_address", "")
        self.private_key = config.get("private_key", "")
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        self._api_creds = None
        self._init_api_creds()

    def _init_api_creds(self):
        """Derive API credentials from private key."""
        if not self.private_key:
            return
        try:
            # Try to derive L2 API key
            url = f"{self.clob_host}/derive-api-key"
            # Use eth-account for signing
            from eth_account import Account
            acct = Account.from_key(self.private_key)
            
            # Create API key via Polymarket's derive endpoint
            nonce = int(time.time())
            headers = {"POLY_ADDRESS": self.safe_address, "POLY_NONCE": str(nonce)}
            resp = self.session.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                self._api_creds = data
                logger.info("API credentials derived")
            else:
                logger.warning(f"API key derivation failed: {resp.status_code}")
        except Exception as e:
            logger.warning(f"Could not derive API creds: {e}")

    async def execute(self, opportunity: dict) -> OrderResult:
        """Execute a trade based on a value opportunity."""
        token_id = opportunity.get("token_id", "")
        price = opportunity.get("market_price", 0.5)
        size = opportunity.get("size", 1.0)

        if not token_id:
            return OrderResult(success=False, message="No token ID")

        try:
            # Place limit order slightly below market for better fill
            buy_price = min(price + 0.01, 0.99)

            order_payload = {
                "tokenID": token_id,
                "price": buy_price,
                "size": size,
                "side": "BUY",
                "feeRateBps": 0,
                "nonce": int(time.time() * 1000),
            }

            # Sign order (simplified — production needs EIP-712 signing)
            result = self._place_order(order_payload)

            if result.get("success"):
                order_id = result.get("orderID", result.get("orderId", ""))
                logger.info(
                    f"BUY {opportunity.get('outcome', '')} @ {buy_price:.4f} "
                    f"size={size:.2f} order={order_id[:8]}... "
                    f"edge={opportunity.get('edge', 0):.2%}"
                )
                return OrderResult(
                    success=True,
                    order_id=order_id,
                    fill_price=buy_price,
                    timestamp=time.time(),
                )
            else:
                msg = result.get("errorMsg", "Unknown error")
                logger.warning(f"Order failed: {msg}")
                return OrderResult(success=False, message=msg)

        except Exception as e:
            logger.error(f"Execution error: {e}")
            return OrderResult(success=False, message=str(e))

    def _place_order(self, payload: dict) -> dict:
        """Place order on Polymarket CLOB."""
        try:
            url = f"{self.clob_host}/order"
            resp = self.session.post(url, json=payload, timeout=15)
            return resp.json()
        except Exception as e:
            logger.error(f"Order POST failed: {e}")
            return {"success": False, "errorMsg": str(e)}

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        try:
            url = f"{self.clob_host}/order/{order_id}"
            resp = self.session.delete(url, timeout=10)
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"Cancel failed for {order_id}: {e}")
            return False

    def cancel_all(self) -> bool:
        """Cancel all open orders."""
        try:
            url = f"{self.clob_host}/cancel-all"
            resp = self.session.delete(url, timeout=15)
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"Cancel-all failed: {e}")
            return False

    def get_open_orders(self) -> list:
        """Get all open orders."""
        try:
            url = f"{self.clob_host}/orders"
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.error(f"Get orders failed: {e}")
        return []
