import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_USER_IDS = [int(uid.strip()) for uid in os.getenv("ADMIN_USER_IDS", "").split(",") if uid.strip()]
RPC_URL = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")

WALLET_FILE = "wallets.json"

# Default trading parameters (editable via commands)
DEFAULT_SLIPPAGE_BPS = 250          # 2.5%
DEFAULT_POSITION_SIZE_PERCENT = 5.0
DEFAULT_MAX_DAILY_TRADES = 20
DEFAULT_COOLDOWN_SECONDS = 30
DEFAULT_PROFIT_MULTIPLIER = 2.0
DEFAULT_TRAILING_STOP_PERCENT = 0.0  # 0 = off
DEFAULT_TRADING_WINDOW = {"start": "00:00", "end": "23:59"}
MAX_DAILY_LOSS_SOL = 2.0

HONEYPOT_SIM_AMOUNT_SOL = 0.01
MAX_RUNTIME_SECONDS = 4 * 3600 - 60