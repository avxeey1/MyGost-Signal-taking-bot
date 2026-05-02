import logging
import os

os.makedirs("logs", exist_ok=True)

logger = logging.getLogger("tgbot")
logger.setLevel(logging.INFO)

# File handler
fh = logging.FileHandler("logs/bot.log")
fh.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
logger.addHandler(fh)

# Console handler
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(formatter)
logger.addHandler(ch)