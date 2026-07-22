"""
Trade Logger
------------
Writes every buy and sell to trades.csv.
Provides daily stats for the morning summary.
"""

import csv
import os
import logging
from datetime import datetime
from typing import Dict

logger = logging.getLogger(__name__)

LOG_FILE = "trades.csv"

HEADERS = [
    "date", "time", "symbol", "action",
    "entry_price", "exit_price",
    "quantity", "cost_fiat", "pnl", "pnl_pct",
    "duration_hours", "reason",
    "trigger_author", "trigger_post",
]


def _ensure_file():
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", newline="") as f:
            csv.writer(f).writerow(HEADERS)


def log_buy(symbol: str, price: float, quantity: float,
            cost: float, author: str, post: str):
    _ensure_file()
    now = datetime.now()
    with open(LOG_FILE, "a", newline="") as f:
        csv.writer(f).writerow([
            now.strftime("%Y-%m-%d"),
            now.strftime("%H:%M:%S"),
            symbol, "BUY",
            f"{price:.6f}", "",
            f"{quantity:.8f}", f"{cost:.2f}",
            "", "", "", "",
            author, post[:120],
        ])


def log_sell(trade: dict, reason: str):
    _ensure_file()
    now = datetime.now()
    with open(LOG_FILE, "a", newline="") as f:
        csv.writer(f).writerow([
            now.strftime("%Y-%m-%d"),
            now.strftime("%H:%M:%S"),
            trade["symbol"], "SELL",
            f"{trade['entry_price']:.6f}",
            f"{trade['exit_price']:.6f}",
            f"{trade['quantity']:.8f}", "",
            f"{trade['pnl']:.4f}",
            f"{trade['pnl_pct']:.2f}",
            f"{trade['duration_hours']:.2f}",
            reason,
            trade.get("trigger_author", ""),
            str(trade.get("trigger_post", ""))[:120],
        ])


def get_today_stats() -> dict:
    """Reads trades.csv and returns stats for today's SELL rows."""
    today  = datetime.now().strftime("%Y-%m-%d")
    trades = wins = 0
    total_pnl = 0.0

    if not os.path.exists(LOG_FILE):
        return {"trades": 0, "wins": 0, "win_rate": 0.0, "pnl": 0.0}

    with open(LOG_FILE, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("date") == today and row.get("action") == "SELL":
                trades += 1
                try:
                    pnl = float(row["pnl"])
                    total_pnl += pnl
                    if pnl > 0:
                        wins += 1
                except ValueError:
                    pass

    return {
        "trades":   trades,
        "wins":     wins,
        "win_rate": round((wins / trades * 100) if trades else 0.0, 1),
        "pnl":      round(total_pnl, 2),
    }


def get_all_time_stats() -> dict:
    """Overall stats since the log file was created."""
    trades = wins = 0
    total_pnl = 0.0

    if not os.path.exists(LOG_FILE):
        return {"trades": 0, "wins": 0, "win_rate": 0.0, "pnl": 0.0}

    with open(LOG_FILE, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("action") == "SELL":
                trades += 1
                try:
                    pnl = float(row["pnl"])
                    total_pnl += pnl
                    if pnl > 0:
                        wins += 1
                except ValueError:
                    pass

    return {
        "trades":   trades,
        "wins":     wins,
        "win_rate": round((wins / trades * 100) if trades else 0.0, 1),
        "pnl":      round(total_pnl, 2),
    }
