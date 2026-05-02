import json, os, base58
from solana.keypair import Keypair
from solana.publickey import PublicKey
from solana.rpc.async_api import AsyncClient
from config import RPC_URL, WALLET_FILE
from audit_logger import logger

class WalletManager:
    def __init__(self):
        self.file = WALLET_FILE
        self.rpc = AsyncClient(RPC_URL)
        self._ensure_file()

    async def close(self):
        await self.rpc.close()

    def _ensure_file(self):
        if not os.path.exists(self.file):
            with open(self.file, "w") as f:
                json.dump([], f)

    def load_wallets(self):
        try:
            with open(self.file, "r") as f:
                return json.load(f)
        except:
            return []

    def save_wallets(self, wallets):
        with open(self.file, "w") as f:
            json.dump(wallets, f, indent=2)

    def create_wallet(self, label=""):
        kp = Keypair.generate()
        wallets = self.load_wallets()
        wallet = {
            "label": label or f"wallet_{len(wallets)+1}",
            "public_key": str(kp.public_key),
            "private_key": base58.b58encode(kp.secret_key).decode(),
            "active": True
        }
        wallets.append(wallet)
        self.save_wallets(wallets)
        logger.info(f"Created wallet {wallet['label']} : {wallet['public_key']}")
        return wallet

    def import_wallet(self, private_key_b58, label=""):
        try:
            secret = base58.b58decode(private_key_b58)
            kp = Keypair.from_secret_key(secret)
        except Exception:
            raise ValueError("Invalid private key")
        wallets = self.load_wallets()
        if any(w["public_key"] == str(kp.public_key) for w in wallets):
            raise ValueError("Wallet already exists")
        wallet = {
            "label": label or f"wallet_{len(wallets)+1}",
            "public_key": str(kp.public_key),
            "private_key": private_key_b58,
            "active": True
        }
        wallets.append(wallet)
        self.save_wallets(wallets)
        logger.info(f"Imported wallet {wallet['label']} : {wallet['public_key']}")
        return wallet

    async def get_balance(self, public_key: str):
        try:
            resp = await self.rpc.get_balance(PublicKey(public_key))
            return resp['result']['value'] / 1e9
        except Exception as e:
            logger.error(f"Balance fetch failed: {e}")
            return 0.0

    async def send_sol(self, from_private_key_b58, to_public_key, amount_sol):
        """Simple SOL transfer. Requires solana SystemProgram."""
        from solana.transaction import Transaction
        from solana.system_program import TransferParams, transfer
        secret = base58.b58decode(from_private_key_b58)
        sender = Keypair.from_secret_key(secret)
        to_pub = PublicKey(to_public_key)
        lamports = int(amount_sol * 1e9)
        txn = Transaction().add(transfer(TransferParams(
            from_pubkey=sender.public_key,
            to_pubkey=to_pub,
            lamports=lamports
        )))
        resp = await self.rpc.send_transaction(txn, sender)
        return str(resp['result'])

    def get_active_wallets(self):
        return [w for w in self.load_wallets() if w.get("active", True)]