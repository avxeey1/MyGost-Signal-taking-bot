import aiohttp
from solana.rpc.async_api import AsyncClient
from solana.publickey import PublicKey
from audit_logger import logger

async def check_token_safety(mint_address: str, rpc_client: AsyncClient):
    mint_pubkey = PublicKey(mint_address)

    # 1. Mint & Freeze authority
    try:
        resp = await rpc_client.get_account_info(mint_pubkey, encoding="jsonParsed")
        data = resp['result']['value']['data']['parsed']['info']
    except Exception:
        return False, "Invalid mint address"

    if data.get("mintAuthority") is not None:
        return False, "Mint authority not revoked"
    if data.get("freezeAuthority") is not None:
        return False, "Freeze authority is set"

    # 2. Liquidity pool (DexScreener)
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{mint_address}"
            async with session.get(url) as resp:
                if resp.status != 200:
                    return False, "DexScreener unavailable"
                data = await resp.json()
                pairs = data.get("pairs", [])
                if not pairs:
                    return False, "No liquidity pools"
                sol_pool = None
                for p in pairs:
                    if p["quoteToken"]["symbol"] in ("SOL", "USDC") and float(p.get("liquidity", {}).get("usd", 0)) > 500:
                        sol_pool = p
                        break
                if not sol_pool:
                    return False, "No pool with >$500 liquidity against SOL/USDC"
    except Exception as e:
        return False, f"Liquidity check error: {str(e)}"

    # Honeypot simulation will be done at trade time
    return True, "Safety checks passed"