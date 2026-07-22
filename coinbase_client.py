"""
Coinbase Client
---------------
Wraps the Coinbase Advanced Trade API.
Prefers GBP trading pairs since the account holds GBP.
Falls back to USD pairs if no GBP pair exists for a coin.
"""

import time
import logging
from typing import Optional, Set, Dict

from coinbase.rest import RESTClient

logger = logging.getLogger(__name__)


class CoinbaseClient:
    def __init__(self, api_key_name: str, private_key: str):
        self.client = RESTClient(
            api_key=api_key_name,
            api_secret=private_key,
        )
        self._gbp_symbols: Set[str] = set()
        self._usd_symbols: Set[str] = set()

    # ----------------------------------------------------------------
    #  Products
    # ----------------------------------------------------------------
    def load_available_symbols(self) -> Set[str]:
        """Load available GBP and USD trading pairs."""
        try:
            resp = self.client.get_products(product_type="SPOT")
            for p in resp.products:
                pid    = p.product_id
                status = p.status
                if status == "online":
                    if pid.endswith("-GBP"):
                        self._gbp_symbols.add(pid.replace("-GBP", ""))
                    elif pid.endswith("-USD"):
                        self._usd_symbols.add(pid.replace("-USD", ""))

            logger.info(
                f"Loaded {len(self._gbp_symbols)} GBP pairs "
                f"and {len(self._usd_symbols)} USD pairs"
            )
            return self._gbp_symbols | self._usd_symbols
        except Exception as e:
            logger.error(f"Error loading products: {e}")
            return set()

    def is_available(self, symbol: str) -> bool:
        return symbol in self._gbp_symbols or symbol in self._usd_symbols

    def _get_pair(self, symbol: str) -> str:
        """Return the best trading pair for a symbol — GBP preferred."""
        if symbol in self._gbp_symbols:
            return f"{symbol}-GBP"
        return f"{symbol}-USD"

    # ----------------------------------------------------------------
    #  Balance helpers
    # ----------------------------------------------------------------
    def _parse_balance(self, balance_obj) -> float:
        if balance_obj is None:
            return 0.0
        if isinstance(balance_obj, dict):
            return float(balance_obj.get("value", 0))
        if hasattr(balance_obj, "value"):
            return float(balance_obj.value)
        return float(balance_obj)

    def _get_acc_field(self, acc, field: str):
        if isinstance(acc, dict):
            return acc.get(field, "")
        return getattr(acc, field, "")

    def _get_accounts_list(self):
        accounts = self.client.get_accounts()
        if isinstance(accounts, list):
            return accounts
        if isinstance(accounts, dict):
            return accounts.get("accounts", [])
        return getattr(accounts, "accounts", [])

    def get_fiat_balance(self) -> float:
        """Returns available GBP balance (falls back to USD)."""
        try:
            gbp = usd = 0.0
            for acc in self._get_accounts_list():
                currency = self._get_acc_field(acc, "currency")
                bal      = self._parse_balance(
                    self._get_acc_field(acc, "available_balance")
                )
                if currency == "GBP":
                    gbp += bal
                elif currency == "USD":
                    usd += bal
            result = gbp if gbp > 0 else usd
            logger.info(f"Balance: GBP={gbp:.2f}  USD={usd:.2f}  using={result:.2f}")
            return result
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return 0.0

    def get_coin_balance(self, symbol: str) -> float:
        try:
            for acc in self._get_accounts_list():
                if self._get_acc_field(acc, "currency") == symbol:
                    return self._parse_balance(
                        self._get_acc_field(acc, "available_balance")
                    )
        except Exception as e:
            logger.error(f"Error getting {symbol} balance: {e}")
        return 0.0

    # ----------------------------------------------------------------
    #  Prices
    # ----------------------------------------------------------------
    def get_price(self, symbol: str) -> Optional[float]:
        """Mid-market price — uses GBP pair if available."""
        try:
            product_id = self._get_pair(symbol)
            resp = self.client.get_best_bid_ask(product_ids=[product_id])
            if resp.pricebooks:
                pb = resp.pricebooks[0]
                if pb.bids and pb.asks:
                    return (float(pb.bids[0].price) + float(pb.asks[0].price)) / 2
        except Exception as e:
            logger.error(f"Error getting price for {symbol}: {e}")
        return None

    def get_prices(self, symbols: list) -> Dict[str, float]:
        prices = {}
        for symbol in symbols:
            price = self.get_price(symbol)
            if price:
                prices[symbol] = price
        return prices

    # ----------------------------------------------------------------
    #  Orders
    # ----------------------------------------------------------------
    def buy_market(self, symbol: str, quote_size: float) -> Optional[dict]:
        """Market buy — uses GBP pair if available."""
        try:
            product_id      = self._get_pair(symbol)
            client_order_id = f"buy_{symbol}_{int(time.time())}"
            order = self.client.market_order_buy(
                client_order_id=client_order_id,
                product_id=product_id,
                quote_size=str(round(quote_size, 2)),
            )
            # Handle different response formats across library versions
            order_id = (
                getattr(order, "order_id", None)
                or getattr(getattr(order, "success_response", None), "order_id", None)
                or "placed"
            )
            logger.info(
                f"BUY order placed: {product_id}  "
                f"£/{quote_size:.2f}  id={order_id}"
            )
            return {
                "order_id":   order_id,
                "product_id": product_id,
                "status":     getattr(order, "status", "unknown"),
            }
        except Exception as e:
            logger.error(f"Buy failed for {symbol}: {e}")
            return None

    def sell_market(self, symbol: str, base_size: float) -> Optional[dict]:
        """Market sell — uses same pair as buy."""
        try:
            product_id      = self._get_pair(symbol)
            client_order_id = f"sell_{symbol}_{int(time.time())}"
            order = self.client.market_order_sell(
                client_order_id=client_order_id,
                product_id=product_id,
                base_size=str(round(base_size, 8)),
            )
            order_id = (
                getattr(order, "order_id", None)
                or getattr(getattr(order, "success_response", None), "order_id", None)
                or "placed"
            )
            logger.info(
                f"SELL order placed: {product_id}  "
                f"qty={base_size:.8f}  id={order_id}"
            )
            return {
                "order_id":   order_id,
                "product_id": product_id,
                "status":     getattr(order, "status", "unknown"),
            }
        except Exception as e:
            logger.error(f"Sell failed for {symbol}: {e}")
            return None
