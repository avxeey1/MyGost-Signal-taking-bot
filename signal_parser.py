import re
from solana.publickey import PublicKey

def extract_token_address(text):
    pattern = r'\b([1-9A-HJ-NP-Za-km-z]{32,44})\b'
    matches = re.findall(pattern, text)
    for m in matches:
        try:
            PublicKey(m)
            return m
        except:
            continue
    return None