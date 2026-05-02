import asyncio, json, os, time
from datetime import datetime, timezone
from config import *
from wallet_manager import WalletManager
from jupiter_client import JupiterClient
from safety_checks import check_token_safety
from signal_parser import extract_token_address
from audit_logger import logger

SOL_MINT = "So11111111111111111111111111111111111111112"

class TradeManager:
    def __init__(self, bot):
        self.bot = bot
        self.wm = WalletManager()
        self.jup = JupiterClient()
        self.active_trades = {}
        self.last_trade_time = 0
        self.daily_trade_count = 0
        self.daily_loss_sol = 0.0
        self.kill_switch = False
        self.paper_mode = False
        self.runtime_start = time.time()
        self.trailing_stop_percent = DEFAULT_TRAILING_STOP_PERCENT
        self._load_state()
        self._check_day_reset()

        # Override defaults from config files if exist
        self.slippage = DEFAULT_SLIPPAGE_BPS
        self.position_pct = DEFAULT_POSITION_SIZE_PERCENT
        self.max_daily_trades = DEFAULT_MAX_DAILY_TRADES
        self.cooldown = DEFAULT_COOLDOWN_SECONDS
        self.profit_mult = DEFAULT_PROFIT_MULTIPLIER

    def _load_state(self):
        try:
            with open("trade_state.json","r") as f:
                s = json.load(f)
                self.active_trades = s.get("active_trades", {})
                self.daily_trade_count = s.get("daily_trade_count", 0)
                self.daily_loss_sol = s.get("daily_loss_sol", 0.0)
                self.last_trade_time = s.get("last_trade_time", 0)
        except: pass
        if os.path.exists("kill_switch.flag"):
            self.kill_switch = True

    def _save_state(self):
        with open("trade_state.json","w") as f:
            json.dump({
                "active_trades": self.active_trades,
                "daily_trade_count": self.daily_trade_count,
                "daily_loss_sol": self.daily_loss_sol,
                "last_trade_time": self.last_trade_time
            }, f, indent=2)

    def _check_day_reset(self):
        now = datetime.now(timezone.utc)
        if now.hour == 0 and now.minute == 0 and self.daily_trade_count > 0:
            self.daily_trade_count = 0
            self.daily_loss_sol = 0.0
            self._save_state()

    def _load_list(self, filename):
        if os.path.exists(filename):
            with open(filename) as f:
                return json.load(f)
        return []

    async def process_signal(self, message_text, chat_id):
        token = extract_token_address(message_text)
        if not token:
            return
        logger.info(f"Signal: {token}")

        # Duplicate prevention
        if token in self.active_trades:
            return

        # Blacklist / Whitelist
        bl = self._load_list("blacklist.json")
        wl = self._load_list("whitelist.json")
        if token in bl:
            return
        if wl and token not in wl:
            return

        if self.kill_switch:
            return

        # Trading window
        window = DEFAULT_TRADING_WINDOW
        if os.path.exists("trading_window.json"):
            with open("trading_window.json") as f:
                window = json.load(f)
        now_t = datetime.now(timezone.utc).time()
        start = list(map(int, window["start"].split(":")))
        end = list(map(int, window["end"].split(":")))
        start_min = start[0]*60+start[1]
        end_min = end[0]*60+end[1]
        curr_min = now_t.hour*60+now_t.minute
        if not (start_min <= curr_min < end_min):
            return

        # Daily cap
        if self.daily_trade_count >= self.max_daily_trades:
            return

        # Cooldown
        if time.time() - self.last_trade_time < self.cooldown:
            return

        # Safety checks
        safe, reason = await check_token_safety(token, self.jup.rpc)
        if not safe:
            logger.warning(f"Safety failed: {reason}")
            await self.bot.send_message(chat_id, f"❌ {token} rejected: {reason}")
            return

        # Execute on all active wallets
        wallets = self.wm.get_active_wallets()
        if not wallets:
            await self.bot.send_message(chat_id, "No active wallets.")
            return

        for w in wallets:
            try:
                await self._execute_buy(token, w)
            except Exception as e:
                logger.error(f"Buy error {w['label']}: {e}")

        self.daily_trade_count += 1
        self.last_trade_time = time.time()
        self._save_state()

    async def _execute_buy(self, token_mint, wallet):
        bal = await self.wm.get_balance(wallet["public_key"])
        if bal < 0.001:
            logger.warning(f"Low balance in {wallet['label']}")
            return
        sol_amount = bal * (self.position_pct / 100.0)
        lamports = int(sol_amount * 1e9)

        if self.paper_mode:
            quote = await self.jup._quote(SOL_MINT, token_mint, lamports, self.slippage)
            out_amount = int(quote['outAmount'])
            price = lamports / out_amount if out_amount else 0
            self.active_trades[token_mint] = {
                "wallet_label": wallet["label"],
                "entry_price_sol": price,
                "amount_tokens": out_amount,
                "buy_time": time.time(),
                "highest_price_sol": price
            }
            self._save_state()
            logger.info(f"PAPER BUY {token_mint} {sol_amount} SOL")
            return

        txid = await self.jup.execute_swap(wallet["private_key"], SOL_MINT, token_mint, lamports, self.slippage)
        quote = await self.jup._quote(SOL_MINT, token_mint, lamports, self.slippage)
        out_amount = int(quote['outAmount'])
        price = lamports / out_amount if out_amount else 0
        self.active_trades[token_mint] = {
            "wallet_label": wallet["label"],
            "entry_price_sol": price,
            "amount_tokens": out_amount,
            "buy_time": time.time(),
            "highest_price_sol": price,
            "txid": txid
        }
        self._save_state()
        logger.info(f"Bought {token_mint} tx {txid}")

    async def monitor_positions(self):
        logger.info("Monitor started")
        while True:
            if self.kill_switch:
                await asyncio.sleep(10)
                continue
            for token, trade in list(self.active_trades.items()):
                try:
                    amount = trade["amount_tokens"]
                    if amount == 0: continue
                    quote = await self.jup._quote(token, SOL_MINT, amount, self.slippage)
                    out_lamports = int(quote['outAmount'])
                    current_price = out_lamports / amount if amount else 0
                    # update highest for trailing stop
                    if current_price > trade.get("highest_price_sol", 0):
                        trade["highest_price_sol"] = current_price

                    # sell condition: 2x profit or trailing stop
                    sell = False
                    if current_price >= trade["entry_price_sol"] * self.profit_mult:
                        sell = True
                    elif self.trailing_stop_percent > 0:
                        peak = trade["highest_price_sol"]
                        stop_price = peak * (1 - self.trailing_stop_percent/100)
                        if current_price <= stop_price:
                            sell = True

                    if sell:
                        wallet = self._find_wallet(trade["wallet_label"])
                        if wallet and not self.paper_mode:
                            txid = await self.jup.execute_swap(
                                wallet["private_key"], token, SOL_MINT,
                                amount, self.slippage
                            )
                            logger.info(f"Sold {token} tx {txid}")
                            # compute profit/loss
                            profit_sol = (current_price - trade["entry_price_sol"]) * amount
                            self.daily_loss_sol -= profit_sol  # negative if loss
                        else:
                            logger.info(f"PAPER SELL {token}")
                            profit_sol = (current_price - trade["entry_price_sol"]) * amount / 1e9  # in SOL? careful
                        del self.active_trades[token]
                        self._save_state()
                except Exception as e:
                    logger.error(f"Monitor error {token}: {e}")
            await asyncio.sleep(5)

    def _find_wallet(self, label):
        for w in self.wm.get_active_wallets():
            if w["label"] == label:
                return w
        return None