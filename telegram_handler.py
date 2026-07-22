"""
Telegram Handler
----------------
Sends real-time trade notifications and handles bot commands:

  /status   — current balance, open positions, mode
  /mode     — switch between auto and approval mode
  /resume   — restart trading after daily loss limit pause
  /stats    — all-time trade statistics
  /help     — command list
"""

import logging
import asyncio
from typing import TYPE_CHECKING

from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.error import TelegramError

import config
import trade_logger

if TYPE_CHECKING:
    from main import TradingBot

logger = logging.getLogger(__name__)


class TelegramHandler:
    def __init__(self, token: str, chat_id: str, bot_ref=None):
        self.token   = token
        self.chat_id = chat_id
        self.bot     = Bot(token=token)
        self.bot_ref = bot_ref          # reference to TradingBot for commands
        self._app: Application | None = None

    # ----------------------------------------------------------------
    #  Low-level send
    # ----------------------------------------------------------------
    async def send(self, text: str):
        if not self.chat_id:
            logger.warning("No TELEGRAM_CHAT_ID set — cannot send message")
            return
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode="HTML",
            )
        except TelegramError as e:
            logger.error(f"Telegram send failed: {e}")

    # ----------------------------------------------------------------
    #  Notification helpers
    # ----------------------------------------------------------------
    async def notify_startup(self, balance: float, mode: str):
        await self.send(
            f"🤖 <b>Trading Bot Online</b>\n\n"
            f"💰 Balance: ${balance:.2f}\n"
            f"⚡ Mode: {mode.upper()}\n"
            f"👥 Watching: Trump · Elon Musk · Michael Saylor · Cathie Wood\n\n"
            f"Type /help to see available commands ✅"
        )

    async def notify_signal(self, symbol: str, author: str,
                            sentiment: float, post: str):
        await self.send(
            f"🔍 <b>SIGNAL DETECTED</b>\n\n"
            f"👤 {author} mentioned <b>{symbol}</b>\n"
            f"📊 Sentiment score: {sentiment:.2f}\n"
            f'📝 "{post[:160]}"\n\n'
            f"⚡ Executing trade..."
        )

    async def notify_buy(self, symbol: str, price: float, quantity: float,
                         cost: float, author: str):
        await self.send(
            f"🟢 <b>BUY EXECUTED</b>\n\n"
            f"🪙 {symbol}\n"
            f"💰 Price:    ${price:,.6f}\n"
            f"📦 Quantity: {quantity:.6f}\n"
            f"💵 Spent:    ${cost:.2f}\n"
            f"👤 Signal:   {author}\n\n"
            f"Stop losses active ✅"
        )

    async def notify_sell(self, symbol: str, price: float,
                          pnl: float, pnl_pct: float, reason: str):
        arrow = "📈" if pnl >= 0 else "📉"
        emoji = "🟢" if pnl >= 0 else "🔴"
        await self.send(
            f"{emoji} <b>SELL EXECUTED</b>\n\n"
            f"🪙 {symbol}\n"
            f"💰 Exit:   ${price:,.6f}\n"
            f"{arrow} P&L:    ${pnl:+.4f}  ({pnl_pct:+.1f}%)\n"
            f"⚡ Reason: {reason}"
        )

    async def notify_take_profit(self, symbol: str, price: float,
                                 level: int, qty_sold: float, pnl: float):
        await self.send(
            f"💰 <b>TAKE PROFIT — Level {level}</b>\n\n"
            f"🪙 {symbol} @ ${price:,.6f}\n"
            f"📦 Sold: {qty_sold:.6f}\n"
            f"📈 P&L on this portion: ${pnl:+.4f}\n\n"
            f"Remaining position still running ✅"
        )

    async def notify_daily_loss_limit(self, loss_pct: float):
        await self.send(
            f"🛑 <b>DAILY LOSS LIMIT HIT</b>\n\n"
            f"📉 Lost {loss_pct:.1f}% today\n"
            f"🔒 Trading paused for the rest of today\n\n"
            f"Type /resume to restart manually"
        )

    async def notify_approval_needed(self, symbol: str, author: str,
                                     sentiment: float, post: str):
        await self.send(
            f"⏳ <b>APPROVAL NEEDED</b>\n\n"
            f"🪙 Signal: {symbol}  |  {author}\n"
            f"📊 Sentiment: {sentiment:.2f}\n"
            f'📝 "{post[:160]}"\n\n'
            f"Reply /approve to execute or /skip to ignore\n"
            f"<i>(60 seconds or trade is skipped)</i>"
        )

    async def send_morning_summary(self, balance: float):
        stats = trade_logger.get_today_stats()
        arrow = "📈" if stats["pnl"] >= 0 else "📉"
        await self.send(
            f"🌅 <b>MORNING SUMMARY</b>\n\n"
            f"💰 Balance:       ${balance:.2f}\n"
            f"{arrow} Yesterday P&L: ${stats['pnl']:+.2f}\n"
            f"📊 Trades:        {stats['trades']}\n"
            f"🎯 Win Rate:      {stats['win_rate']:.0f}%\n\n"
            f"Bot is running ✅"
        )

    # ----------------------------------------------------------------
    #  Command handlers (registered with Application)
    # ----------------------------------------------------------------
    async def _cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🤖 <b>Available Commands</b>\n\n"
            "/status  — balance & open positions\n"
            "/mode    — toggle auto / approval mode\n"
            "/resume  — restart after daily loss limit\n"
            "/stats   — all-time trade statistics\n"
            "/help    — this message",
            parse_mode="HTML",
        )

    async def _cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self.bot_ref:
            return
        b = self.bot_ref
        balance = b.coinbase.get_fiat_balance()
        prices  = b.coinbase.get_prices(list(b.positions.positions.keys()))
        snap    = b.positions.snapshot(prices)

        pos_lines = (
            "\n".join(
                f"  • {p['symbol']}: {p['pnl_pct']:+.1f}%  "
                f"(open {p['hours_open']}h)"
                for p in snap
            )
            or "  None"
        )

        today = trade_logger.get_today_stats()
        await update.message.reply_text(
            f"📊 <b>BOT STATUS</b>\n\n"
            f"💰 Balance:    ${balance:.2f}\n"
            f"⚡ Mode:       {b.mode.upper()}\n"
            f"▶ Running:    {'Yes ✅' if b.running else 'Paused 🔴'}\n\n"
            f"<b>Open Positions:</b>\n{pos_lines}\n\n"
            f"<b>Today:</b>  {today['trades']} trades  |  "
            f"${today['pnl']:+.2f}  |  {today['win_rate']:.0f}% win rate",
            parse_mode="HTML",
        )

    async def _cmd_mode(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self.bot_ref:
            return
        b = self.bot_ref
        b.mode = "approval" if b.mode == "auto" else "auto"
        await update.message.reply_text(
            f"⚡ Mode switched to <b>{b.mode.upper()}</b>",
            parse_mode="HTML",
        )

    async def _cmd_resume(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self.bot_ref:
            return
        self.bot_ref.running = True
        await update.message.reply_text("▶ Trading resumed ✅")

    async def _cmd_stats(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        s = trade_logger.get_all_time_stats()
        await update.message.reply_text(
            f"📈 <b>All-Time Stats</b>\n\n"
            f"📊 Total trades:  {s['trades']}\n"
            f"🎯 Win rate:      {s['win_rate']:.1f}%\n"
            f"💰 Total P&L:     ${s['pnl']:+.2f}",
            parse_mode="HTML",
        )

    # ----------------------------------------------------------------
    #  Start Telegram polling (runs alongside the main async loop)
    # ----------------------------------------------------------------
    async def start_polling(self):
        self._app = Application.builder().token(self.token).build()

        self._app.add_handler(CommandHandler("help",   self._cmd_help))
        self._app.add_handler(CommandHandler("status", self._cmd_status))
        self._app.add_handler(CommandHandler("mode",   self._cmd_mode))
        self._app.add_handler(CommandHandler("resume", self._cmd_resume))
        self._app.add_handler(CommandHandler("stats",  self._cmd_stats))

        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram polling started")

    async def stop_polling(self):
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
