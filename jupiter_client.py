import aiohttp, base58, base64
from solana.transaction import Transaction
from solana.keypair import Keypair
from solana.rpc.async_api import AsyncClient
from audit_logger import logger
from config import RPC_URL, DEFAULT_SLIPPAGE_BPS

JUPITER_QUOTE = "https://quote-api.jup.ag/v6/quote"
JUPITER_SWAP = "https://quote-api.jup.ag/v6/swap"

class JupiterClient:
    def __init__(self):
        self.rpc = AsyncClient(RPC_URL)

    async def close(self):
        await self.rpc.close()

    async def _quote(self, input_mint, output_mint, amount, slippage):
        async with aiohttp.ClientSession() as sess:
            params = {
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": amount,
                "slippageBps": slippage
            }
            async with sess.get(JUPITER_QUOTE, params=params) as resp:
                if resp.status != 200:
                    raise Exception(f"Quote failed: {await resp.text()}")
                return await resp.json()

    async def _swap_tx(self, quote, user_pubkey):
        async with aiohttp.ClientSession() as sess:
            payload = {
                "quoteResponse": quote,
                "userPublicKey": user_pubkey,
                "wrapAndUnwrapSol": True
            }
            async with sess.post(JUPITER_SWAP, json=payload) as resp:
                if resp.status != 200:
                    raise Exception(f"Swap tx failed: {await resp.text()}")
                return await resp.json()

    async def simulate(self, tx_b64):
        try:
            tx = Transaction.deserialize(base64.b64decode(tx_b64))
            sim = await self.rpc.simulate_transaction(tx, sig_verify=False)
            err = sim['result']['value']['err']
            return err is None, sim['result']['value']['logs'] or [], str(err or "")
        except Exception as e:
            return False, [], str(e)

    async def execute_swap(self, wallet_private_b58, input_mint, output_mint, amount, slippage=DEFAULT_SLIPPAGE_BPS):
        secret = base58.b58decode(wallet_private_b58)
        wallet = Keypair.from_secret_key(secret)

        quote = await self._quote(input_mint, output_mint, amount, slippage)
        swap_data = await self._swap_tx(quote, str(wallet.public_key))
        tx_b64 = swap_data['swapTransaction']

        success, _, err = await self.simulate(tx_b64)
        if not success:
            raise Exception(f"Simulation failed: {err}")

        tx = Transaction.deserialize(base64.b64decode(tx_b64))
        tx.sign(wallet)
        resp = await self.rpc.send_transaction(tx, opts={"skip_preflight": True})
        return str(resp['result'])