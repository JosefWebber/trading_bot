"""
Trading Bot — Main
------------------
Run with:  python main.py

This is the entry point that ties every component together
and runs the main async event loop.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Optional

import config
from coinbase_client    import CoinbaseClient
from sentiment_analyzer import SentimentAnalyzer
from social_monitor     import SocialMonitor
from position_manager   import PositionManager
from telegram_handler   import TelegramHandler
import trade_logger

# ----------------------------------------------------------------
#  Logging — prints to console so you can see what's happening
# ----------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class TradingBot:
    def __init__(self):
        logger.info("Initialising trading bot...")

        self.coinbase  = CoinbaseClient(config.COINBASE_API_KEY_NAME,
                                        config.COINBASE_PRIVATE_KEY)
        self.sentiment = SentimentAnalyzer()
        self.monitor   = SocialMonitor()
        self.positions = PositionManager()
        self.telegram  = TelegramHandler(config.TELEGRAM_BOT_TOKEN,
                                         config.TELEGRAM_CHAT_ID,
                                         bot_ref=self)

        self.mode:    str  = config.MODE
        self.running: bool = True

        # Approval-mode state
        self._pending_trade: Optional[dict] = None
        self._approval_event = asyncio.Event()

        # Timestamps for interval tracking
        self._last_post_check:  float = 0.0
        self._last_price_check: float = 0.0
        self._morning_sent_hour: int  = -1

    # ----------------------------------------------------------------
    #  Startup
    # ----------------------------------------------------------------
    async def initialise(self):
        logger.info("Loading Coinbase products...")
        self.coinbase.load_available_symbols()

        balance = self.coinbase.get_fiat_balance()
        self.positions.set_daily_start(balance)

        await self.telegram.start_polling()
        await self.telegram.notify_startup(balance, self.mode)
        logger.info(f"Bot ready — balance: ${balance:.2f}  mode: {self.mode}")

    # ----------------------------------------------------------------
    #  Process a single post
    # ----------------------------------------------------------------
    async def _process_post(self, post: dict):
        text   = post["text"]
        author = post["author"]

        # Quick pre-filter — does it even mention crypto?
        if not self.sentiment.quick_check(text):
            return

        result = self.sentiment.analyze(text)

        # Only act on clearly positive mentions
        if not result["is_positive"]:
            return

        coins = result["coins"]
        # Fall back to BTC if only generic crypto terms detected
        if not coins and result["has_generic"]:
            coins = ["BTC"]

        if not coins:
            return

        logger.info(
            f"✅ Positive signal from {author}  coins={coins}  "
            f"score={result['sentiment']}"
        )

        for symbol in coins:
            await self._try_trade(symbol, post, result)

    # ----------------------------------------------------------------
    #  Attempt a trade
    # ----------------------------------------------------------------
    async def _try_trade(self, symbol: str, post: dict, sentiment_result: dict):
        # Already holding this coin?
        if symbol in self.positions.positions:
            logger.info(f"Already in {symbol} — skipping")
            return

        # Coin on cooldown?
        if self.positions.is_cooling_down(symbol):
            logger.info(f"{symbol} in cooldown — skipping")
            return

        # Available on Coinbase?
        if not self.coinbase.is_available(symbol):
            logger.info(f"{symbol} not listed on Coinbase — skipping")
            return

        balance = self.coinbase.get_fiat_balance()

        # Daily loss limit?
        if self.positions.daily_loss_limit_hit(balance):
            logger.warning("Daily loss limit hit — pausing trading")
            self.running = False
            await self.telegram.notify_daily_loss_limit(
                config.DAILY_LOSS_LIMIT_PCT * 100
            )
            return

        # Position sizing
        trade_amount = balance * config.MAX_POSITION_SIZE_PCT
        if trade_amount < 1.0:
            logger.warning(f"Balance too low for a trade (${balance:.2f})")
            return

        # Approval mode — wait for user confirmation
        if self.mode == "approval":
            await self.telegram.notify_approval_needed(
                symbol, post["author"],
                sentiment_result["sentiment"], post["text"]
            )
            self._pending_trade = {
                "symbol": symbol,
                "post":   post,
                "amount": trade_amount,
            }
            self._approval_event.clear()
            try:
                await asyncio.wait_for(self._approval_event.wait(), timeout=60)
                if not self._pending_trade:   # user typed /skip
                    return
            except asyncio.TimeoutError:
                logger.info("Approval timeout — skipping trade")
                self._pending_trade = None
                return

        # Get current price
        price = self.coinbase.get_price(symbol)
        if price is None:
            logger.error(f"Couldn't fetch price for {symbol}")
            return

        # Notify signal detected (auto mode only — approval already sent above)
        if self.mode == "auto":
            await self.telegram.notify_signal(
                symbol, post["author"],
                sentiment_result["sentiment"], post["text"]
            )

        # Execute buy
        order = self.coinbase.buy_market(symbol, trade_amount)
        if order is None:
            logger.error(f"Buy order failed for {symbol}")
            return

        quantity = trade_amount / price   # approximate

        self.positions.open_position(
            symbol=symbol,
            entry_price=price,
            quantity=quantity,
            cost=trade_amount,
            trigger_post=post["text"],
            trigger_author=post["author"],
        )

        trade_logger.log_buy(
            symbol, price, quantity, trade_amount,
            post["author"], post["text"]
        )

        await self.telegram.notify_buy(
            symbol, price, quantity, trade_amount, post["author"]
        )

    # ----------------------------------------------------------------
    #  Monitor open positions every PRICE_CHECK_INTERVAL_SECONDS
    # ----------------------------------------------------------------
    async def _monitor_positions(self):
        symbols = list(self.positions.positions.keys())
        if not symbols:
            return

        prices = self.coinbase.get_prices(symbols)

        for symbol in symbols:
            price = prices.get(symbol)
            if price is None:
                continue

            self.positions.update_peak(symbol, price)

            # --- Take profit? ---
            tp = self.positions.check_take_profit(symbol, price)
            if tp:
                qty_to_sell, level_idx = tp
                order = self.coinbase.sell_market(symbol, qty_to_sell)
                if order:
                    pos = self.positions.positions[symbol]
                    pnl = (price - pos.entry_price) * qty_to_sell
                    self.positions.record_take_profit(symbol, level_idx, qty_to_sell)
                    await self.telegram.notify_take_profit(
                        symbol, price, level_idx + 1, qty_to_sell, pnl
                    )
                continue   # don't also check stops this tick

            # --- Stop losses? ---
            reason = self.positions.check_stop_reason(symbol, price)
            if reason:
                pos   = self.positions.positions[symbol]
                order = self.coinbase.sell_market(symbol, pos.quantity)
                if order:
                    trade = self.positions.close_position(symbol, price, reason)
                    trade_logger.log_sell(trade, reason)
                    await self.telegram.notify_sell(
                        symbol, price,
                        trade["pnl"], trade["pnl_pct"], reason
                    )

    # ----------------------------------------------------------------
    #  Morning summary
    # ----------------------------------------------------------------
    async def _maybe_send_morning_summary(self):
        now = datetime.now()
        if (
            now.hour == config.MORNING_SUMMARY_HOUR
            and now.minute == 0
            and self._morning_sent_hour != now.hour
        ):
            balance = self.coinbase.get_fiat_balance()
            await self.telegram.send_morning_summary(balance)
            self.positions.set_daily_start(balance)   # reset daily tracking
            self._morning_sent_hour = now.hour

    # ----------------------------------------------------------------
    #  Main loop
    # ----------------------------------------------------------------
    async def run(self):
        await self.initialise()

        logger.info("Main loop running — Ctrl+C to stop")

        while True:
            now = time.monotonic()

            # Only trade if running flag is set
            if self.running:
                # Check social media feeds
                if now - self._last_post_check >= config.CHECK_INTERVAL_SECONDS:
                    try:
                        logger.info("Checking social feeds...")
                        posts = self.monitor.get_all_new_posts()
                        for post in posts:
                            await self._process_post(post)
                    except Exception as e:
                        logger.error(f"Post check error: {e}")
                    self._last_post_check = now

                # Monitor open positions
                if now - self._last_price_check >= config.PRICE_CHECK_INTERVAL_SECONDS:
                    try:
                        await self._monitor_positions()
                    except Exception as e:
                        logger.error(f"Position monitor error: {e}")
                    self._last_price_check = now

            # Morning summary (runs regardless of trading pause)
            await self._maybe_send_morning_summary()

            await asyncio.sleep(10)

    # ----------------------------------------------------------------
    #  Graceful shutdown
    # ----------------------------------------------------------------
    async def shutdown(self):
        logger.info("Shutting down...")
        await self.telegram.stop_polling()


# ----------------------------------------------------------------
#  Entry point
# ----------------------------------------------------------------
async def _main():
    bot = TradingBot()
    try:
        await bot.run()
    except (KeyboardInterrupt, SystemExit):
        await bot.shutdown()


if __name__ == "__main__":
    asyncio.run(_main())
