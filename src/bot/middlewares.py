"""Middleware for logging and error handling."""
from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseMiddleware):
    """Middleware for logging incoming messages with timing."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Log incoming events, measure handling time, and call the handler."""
        start = time.perf_counter()

        if isinstance(event, Message):
            user = event.from_user
            user_info = f"{user.id} ({user.username})" if user else "unknown"

            if event.text:
                logger.info("Text message from %s: %s", user_info, event.text[:50])
            elif event.voice:
                logger.info("Voice message from %s, duration: %ds", user_info, event.voice.duration)
            elif event.web_app_data:
                logger.info("WebApp data from %s", user_info)
            else:
                logger.info("Other message from %s", user_info)

        result = await handler(event, data)

        elapsed = time.perf_counter() - start
        logger.info("Handled in %.2fs", elapsed)

        return result


class ErrorHandlingMiddleware(BaseMiddleware):
    """Middleware for handling errors gracefully."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Handle errors and send user-friendly messages."""
        try:
            return await handler(event, data)
        except Exception as e:
            logger.exception("Error in handler: %s", e)

            if isinstance(event, Message):
                await event.answer(
                    "Произошла непредвиденная ошибка. Пожалуйста, попробуйте позже."
                )

            return None
