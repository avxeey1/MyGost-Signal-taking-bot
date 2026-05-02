import os, json
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from config import ADMIN_USER_IDS, DEFAULT_SLIPPAGE_BPS, DEFAULT_POSITION_SIZE_PERCENT, DEFAULT_MAX_DAILY_TRADES, DEFAULT_COOLDOWN_SECONDS, DEFAULT_PROFIT_MULTIPLIER, DEFAULT_TRAILING_STOP_PERCENT, DEFAULT_TRADING_WINDOW
from wallet_manager import WalletManager
from trade_manager import TradeManager

class BotCommands:
    def __init__(self, app, tm: TradeManager):
        self.app = app
        self.tm = tm
        self.wm = WalletManager()
        self._register()

    def _admin_only(self, func):
        async def wrapper(update, context):
            if update.effective_user.id not in ADMIN_USER_IDS:
                await update.message.reply_text("⛔️ Unauthorized")
                return
            return await func(update, context)
        return wrapper

    def _register(self):
        handlers = [
            ("start", self.start),
            ("run", self.run_bot),
            ("stop", self.stop_bot),
            ("balance", self.balance),
            ("createwallet", self.create_wallet),
            ("importwallet", self.import_wallet),
            ("send", self.send_sol),
            ("addchannel", self.add_channel),
            ("setwindow", self.set_window),
            ("setdailytrades", self.set_daily_trades),
            ("setcooldown", self.set_cooldown),
            ("setposition", self.set_position),
            ("setprofit", self.set_profit),
            ("settrailing", self.set_trailing),
            ("blacklist", self.manage_blacklist),
            ("whitelist", self.manage_whitelist),
            ("kill", self.kill),
            ("revive", self.revive),
            ("paper", self.toggle_paper),
            ("trade", self.manual_trade),
        ]
        for cmd, handler in handlers:
            self.app.add_handler(CommandHandler(cmd, self._admin_only(handler)))

    async def start(self, update, context):
        await update.message.reply_text("🤖 Bot ready. Use /run to start trading.")

    async def run_bot(self, update, context):
        self.tm.kill_switch = False
        if os.path.exists("kill_switch.flag"): os.remove("kill_switch.flag")
        await update.message.reply_text("✅ Trading ACTIVE")

    async def stop_bot(self, update, context):
        self.tm.kill_switch = True
        with open("kill_switch.flag","w") as f: f.write("1")
        await update.message.reply_text("🛑 Trading PAUSED")

    async def balance(self, update, context):
        wallets = self.wm.get_active_wallets()
        msg = "💰 Balances:\n"
        for w in wallets:
            bal = await self.wm.get_balance(w["public_key"])
            msg += f"{w['label']} ({w['public_key'][:6]}...): {bal:.4f} SOL\n"
        await update.message.reply_text(msg)

    async def create_wallet(self, update, context):
        label = ' '.join(context.args) if context.args else ""
        w = self.wm.create_wallet(label)
        await update.message.reply_text(
            f"🆕 Wallet {w['label']}\nPublic: `{w['public_key']}`\nPrivate: `{w['private_key']}`",
            parse_mode="Markdown"
        )

    async def import_wallet(self, update, context):
        if len(context.args) < 1:
            await update.message.reply_text("Usage: /importwallet <private_key> [label]")
            return
        pk = context.args[0]
        label = ' '.join(context.args[1:]) if len(context.args)>1 else ""
        try:
            w = self.wm.import_wallet(pk, label)
            await update.message.reply_text(f"✅ Imported {w['label']}: {w['public_key']}")
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")

    async def send_sol(self, update, context):
        if len(context.args) != 3:
            await update.message.reply_text("Usage: /send <from_wallet_label> <to_address> <amount_sol>")
            return
        from_label, to_addr, amount = context.args[0], context.args[1], float(context.args[2])
        wallets = self.wm.load_wallets()
        sender = next((w for w in wallets if w["label"] == from_label), None)
        if not sender:
            await update.message.reply_text("Sender wallet not found.")
            return
        try:
            txid = await self.wm.send_sol(sender["private_key"], to_addr, amount)
            await update.message.reply_text(f"✅ Sent {amount} SOL\ntx: `{txid}`", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"Send failed: {e}")

    async def add_channel(self, update, context):
        if len(context.args) < 1:
            await update.message.reply_text("Usage: /addchannel <chat_id>")
            return
        try:
            chat_id = int(context.args[0])
            chans = []
            if os.path.exists("channels.json"):
                with open("channels.json") as f: chans = json.load(f)
            if chat_id not in chans:
                chans.append(chat_id)
                with open("channels.json","w") as f: json.dump(chans, f)
                await update.message.reply_text(f"✅ Monitoring chat {chat_id}")
            else:
                await update.message.reply_text("Already monitoring.")
        except:
            await update.message.reply_text("Invalid chat ID.")

    async def set_window(self, update, context):
        if len(context.args) != 2:
            await update.message.reply_text("Usage: /setwindow HH:MM HH:MM")
            return
        window = {"start": context.args[0], "end": context.args[1]}
        with open("trading_window.json","w") as f: json.dump(window, f)
        await update.message.reply_text(f"Trading window: {window['start']} - {window['end']} UTC")

    async def set_daily_trades(self, update, context):
        if context.args:
            self.tm.max_daily_trades = int(context.args[0])
            await update.message.reply_text(f"Max daily trades: {self.tm.max_daily_trades}")

    async def set_cooldown(self, update, context):
        if context.args:
            self.tm.cooldown = int(context.args[0])
            await update.message.reply_text(f"Cooldown: {self.tm.cooldown}s")

    async def set_position(self, update, context):
        if context.args:
            self.tm.position_pct = float(context.args[0])
            await update.message.reply_text(f"Position size: {self.tm.position_pct}%")

    async def set_profit(self, update, context):
        if context.args:
            self.tm.profit_mult = float(context.args[0])
            await update.message.reply_text(f"Profit target: {self.tm.profit_mult}x")

    async def set_trailing(self, update, context):
        if context.args:
            self.tm.trailing_stop_percent = float(context.args[0])
            await update.message.reply_text(f"Trailing stop: {self.tm.trailing_stop_percent}%")

    async def manage_blacklist(self, update, context):
        if len(context.args) < 2:
            await update.message.reply_text("Usage: /blacklist add|remove <token>")
            return
        action, addr = context.args[0], context.args[1]
        bl = self.tm._load_list("blacklist.json")
        if action == "add" and addr not in bl:
            bl.append(addr)
        elif action == "remove" and addr in bl:
            bl.remove(addr)
        with open("blacklist.json","w") as f: json.dump(bl, f)
        await update.message.reply_text(f"Blacklist: {len(bl)} entries")

    async def manage_whitelist(self, update, context):
        if len(context.args) < 2:
            await update.message.reply_text("Usage: /whitelist add|remove <token>")
            return
        action, addr = context.args[0], context.args[1]
        wl = self.tm._load_list("whitelist.json")
        if action == "add" and addr not in wl:
            wl.append(addr)
        elif action == "remove" and addr in wl:
            wl.remove(addr)
        with open("whitelist.json","w") as f: json.dump(wl, f)
        await update.message.reply_text(f"Whitelist: {len(wl)} entries")

    async def kill(self, update, context):
        self.tm.kill_switch = True
        with open("kill_switch.flag","w") as f: f.write("1")
        await update.message.reply_text("⚡️ EMERGENCY STOP activated")

    async def revive(self, update, context):
        self.tm.kill_switch = False
        if os.path.exists("kill_switch.flag"): os.remove("kill_switch.flag")
        await update.message.reply_text("✅ Bot revived")

    async def toggle_paper(self, update, context):
        self.tm.paper_mode = not self.tm.paper_mode
        state = "ON" if self.tm.paper_mode else "OFF"
        await update.message.reply_text(f"📝 Paper trading {state}")

    async def manual_trade(self, update, context):
        if len(context.args) != 1:
            await update.message.reply_text("Usage: /trade <token_address>")
            return
        await update.message.reply_text("🚀 Manual trade triggered")
        await self.tm.process_signal(context.args[0], update.effective_chat.id)