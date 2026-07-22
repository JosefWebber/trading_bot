"""
Position Manager
----------------
Tracks every open trade and enforces:
  • Trailing stop loss
  • Hard stop loss
  • Time-based stop
  • Tiered take profit
  • Per-coin cooldowns
  • Daily loss limit
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import config

logger = logging.getLogger(__name__)


@dataclass
class Position:
    symbol:        str
    entry_price:   float
    quantity:      float        # remaining units (decreases as take-profit fires)
    entry_time:    datetime
    peak_price:    float
    cost:          float        # original fiat spent
    trigger_post:  str
    trigger_author: str

    # Take-profit tracking
    tp_prices:     List[float]  = field(default_factory=list)
    tp_portions:   List[float]  = field(default_factory=list)
    tp_fired:      List[bool]   = field(default_factory=list)

    def __post_init__(self):
        # Build absolute TP price targets from config percentages
        if not self.tp_prices:
            self.tp_prices   = [self.entry_price * (1 + lvl)
                                 for lvl in config.TAKE_PROFIT_LEVELS]
            self.tp_portions = list(config.TAKE_PROFIT_PORTIONS)
            self.tp_fired    = [False] * len(config.TAKE_PROFIT_LEVELS)

    # ------------------------------------------------------------------
    def hours_open(self) -> float:
        return (datetime.now() - self.entry_time).total_seconds() / 3600

    def trailing_stop_price(self) -> float:
        return self.peak_price * (1 - config.TRAILING_STOP_PCT)

    def hard_stop_price(self) -> float:
        return self.entry_price * (1 - config.HARD_STOP_LOSS_PCT)

    def pnl_pct(self, current_price: float) -> float:
        return ((current_price - self.entry_price) / self.entry_price) * 100


class PositionManager:
    def __init__(self):
        self.positions:          Dict[str, Position] = {}
        self.cooldowns:          Dict[str, datetime] = {}
        self.daily_start_balance: Optional[float]   = None
        self.daily_pnl:           float             = 0.0

    # ----------------------------------------------------------------
    #  Open / close
    # ----------------------------------------------------------------
    def open_position(self, symbol: str, entry_price: float, quantity: float,
                      cost: float, trigger_post: str, trigger_author: str) -> Position:
        pos = Position(
            symbol=symbol,
            entry_price=entry_price,
            quantity=quantity,
            entry_time=datetime.now(),
            peak_price=entry_price,
            cost=cost,
            trigger_post=trigger_post,
            trigger_author=trigger_author,
        )
        self.positions[symbol] = pos
        logger.info(f"Position opened: {symbol} @ ${entry_price:.4f}  qty={quantity:.6f}")
        return pos

    def close_position(self, symbol: str, exit_price: float, reason: str) -> dict:
        """Close the full remaining position and return a summary dict."""
        pos = self.positions.pop(symbol, None)
        if pos is None:
            return {}

        pnl     = (exit_price - pos.entry_price) * pos.quantity
        pnl_pct = pos.pnl_pct(exit_price)

        self.daily_pnl += pnl
        self.cooldowns[symbol] = datetime.now()

        summary = {
            "symbol":        symbol,
            "entry_price":   pos.entry_price,
            "exit_price":    exit_price,
            "quantity":      pos.quantity,
            "pnl":           round(pnl, 4),
            "pnl_pct":       round(pnl_pct, 2),
            "duration_hours": round(pos.hours_open(), 2),
            "trigger_author": pos.trigger_author,
            "trigger_post":  pos.trigger_post,
            "reason":        reason,
        }
        logger.info(f"Position closed: {symbol} | {reason} | P&L: {pnl:+.4f} ({pnl_pct:+.1f}%)")
        return summary

    # ----------------------------------------------------------------
    #  Price updates
    # ----------------------------------------------------------------
    def update_peak(self, symbol: str, price: float):
        if symbol in self.positions and price > self.positions[symbol].peak_price:
            self.positions[symbol].peak_price = price

    # ----------------------------------------------------------------
    #  Stop-loss checks
    # ----------------------------------------------------------------
    def check_trailing_stop(self, symbol: str, price: float) -> bool:
        pos = self.positions.get(symbol)
        return pos is not None and price <= pos.trailing_stop_price()

    def check_hard_stop(self, symbol: str, price: float) -> bool:
        pos = self.positions.get(symbol)
        return pos is not None and price <= pos.hard_stop_price()

    def check_time_stop(self, symbol: str) -> bool:
        pos = self.positions.get(symbol)
        return pos is not None and pos.hours_open() >= config.TIME_LIMIT_HOURS

    def check_stop_reason(self, symbol: str, price: float) -> Optional[str]:
        """Returns the first triggered stop reason, or None."""
        if self.check_hard_stop(symbol, price):
            return "Hard Stop Loss"
        if self.check_trailing_stop(symbol, price):
            return "Trailing Stop Loss"
        if self.check_time_stop(symbol):
            return "Time Limit Reached"
        return None

    # ----------------------------------------------------------------
    #  Take-profit
    # ----------------------------------------------------------------
    def check_take_profit(self, symbol: str, price: float) -> Optional[Tuple[float, int]]:
        """
        Returns (quantity_to_sell, level_index) if a TP level has been hit,
        else None.
        """
        pos = self.positions.get(symbol)
        if pos is None:
            return None

        for i, (tp_price, fired) in enumerate(zip(pos.tp_prices, pos.tp_fired)):
            if not fired and price >= tp_price:
                qty = pos.quantity * pos.tp_portions[i]
                return (qty, i)
        return None

    def record_take_profit(self, symbol: str, level_index: int, qty_sold: float):
        pos = self.positions.get(symbol)
        if pos:
            pos.tp_fired[level_index] = True
            pos.quantity -= qty_sold
            logger.info(f"TP level {level_index+1} fired for {symbol}  qty sold={qty_sold:.6f}")

    # ----------------------------------------------------------------
    #  Cooldown
    # ----------------------------------------------------------------
    def is_cooling_down(self, symbol: str) -> bool:
        last = self.cooldowns.get(symbol)
        if last is None:
            return False
        elapsed_mins = (datetime.now() - last).total_seconds() / 60
        return elapsed_mins < config.COOLDOWN_MINUTES

    # ----------------------------------------------------------------
    #  Daily loss limit
    # ----------------------------------------------------------------
    def set_daily_start(self, balance: float):
        self.daily_start_balance = balance
        self.daily_pnl = 0.0
        logger.info(f"Daily start balance set: ${balance:.2f}")

    def daily_loss_limit_hit(self, current_balance: float) -> bool:
        if self.daily_start_balance is None or self.daily_start_balance == 0:
            return False
        drop = (self.daily_start_balance - current_balance) / self.daily_start_balance
        return drop >= config.DAILY_LOSS_LIMIT_PCT

    # ----------------------------------------------------------------
    #  Status snapshot (for /status command and dashboard)
    # ----------------------------------------------------------------
    def snapshot(self, prices: Dict[str, float]) -> List[dict]:
        result = []
        for symbol, pos in self.positions.items():
            price = prices.get(symbol, pos.entry_price)
            result.append({
                "symbol":      symbol,
                "entry_price": pos.entry_price,
                "current_price": price,
                "pnl_pct":     round(pos.pnl_pct(price), 2),
                "peak_price":  pos.peak_price,
                "hours_open":  round(pos.hours_open(), 1),
                "author":      pos.trigger_author,
            })
        return result
