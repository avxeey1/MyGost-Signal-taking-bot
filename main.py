import asyncio, os, time
from telegram.ext import Application, MessageHandler, filters
from config import BOT_TOKEN, MAX_RUNTIME_SECONDS
from trade_manager import TradeManager
from commands import BotCommands
from audit_logger import logger

async def main():
    app = Application.builder().token(BOT_TOKEN).build()
    tm = TradeManager(app.bot)

    # Register commands
    BotCommands(app, tm)

    # Signal handler
    async def signal_listener(update, context):
        if not update.message or not update.message.text:
            return
        chat_id = update.effective_chat.id
        monitored = []
        if os.path.exists("channels.json"):
            import json
            with open("channels.json") as f:
                monitored = json.load(f)
        if chat_id in monitored:
            await tm.process_signal(update.message.text, chat_id)

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, signal_listener))

    # Start monitor task
    asyncio.create_task(tm.monitor_positions())

    # Graceful shutdown after runtime limit
    async def shutdown():
        logger.info("Shutting down...")
        await tm.jup.close()
        await tm.wm.close()
        await app.stop()
        await app.shutdown()

    start_time = time.time()
    await app.initialize()
    await app.start()
    # Start polling (does not block, but we need to keep the event loop alive)
    await app.updater.start_polling()
    logger.info("Bot started polling")

    # Keep alive until time limit
    while True:
        elapsed = time.time() - start_time
        if elapsed >= MAX_RUNTIME_SECONDS:
            await shutdown()
            break
        await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())