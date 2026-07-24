"""Точка входа для Bothost (автодетект: main.py → bot.py)."""
from bot import main
import asyncio
import logging
import sys

logger = logging.getLogger("void-bot")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Остановка по Ctrl+C")
    except Exception:
        logger.exception("Бот упал")
        raise
