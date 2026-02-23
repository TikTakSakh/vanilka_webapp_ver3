"""Telegram message handlers."""
from __future__ import annotations

import json
import logging
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from beartype import beartype

from src.services.llm_service import LLMService
from src.services.transcribe_service import TranscribeService
from src.services.knowledge_base import KnowledgeBaseService
from src.services.history_logger import HistoryLogger
from src.storage.sqlite_history import SQLiteDialogHistory

logger = logging.getLogger(__name__)

router = Router(name="main")

# These will be injected at startup
llm_service: LLMService | None = None
transcribe_service: TranscribeService | None = None
dialog_history: SQLiteDialogHistory | None = None
history_logger: HistoryLogger | None = None
knowledge_base_service: KnowledgeBaseService | None = None
admin_user_ids: list[int] = []
_bot_start_time: datetime = datetime.now()
mini_app_url: str | None = None


@beartype
def setup_services(
    llm: LLMService,
    transcribe: TranscribeService,
    history: SQLiteDialogHistory,
    logger_service: HistoryLogger,
    kb_service: KnowledgeBaseService,
    admins: list[int] | None = None,
    webapp_url: str | None = None,
) -> None:
    """Setup services for handlers."""
    global llm_service, transcribe_service, dialog_history, history_logger
    global knowledge_base_service, admin_user_ids, _bot_start_time, mini_app_url
    llm_service = llm
    transcribe_service = transcribe
    dialog_history = history
    history_logger = logger_service
    knowledge_base_service = kb_service
    admin_user_ids = admins or []
    mini_app_url = webapp_url
    _bot_start_time = datetime.now()


WELCOME_MESSAGE = """Привет! 👋 Я администратор магазина "Ванилька". 

🎂 Я помогу вам с информацией о наших бенто-тортах, ценах, доставке и многом другом!

Просто напишите мне ваш вопрос или отправьте голосовое сообщение."""


# ── Helpers ──────────────────────────────────────────────────

def _is_admin(user_id: int) -> bool:
    """Check if a user is an admin."""
    return user_id in admin_user_ids


# ── /start ───────────────────────────────────────────────────

@router.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    """Handle /start command with welcome message and catalog button."""
    # Build reply keyboard with web app button
    if mini_app_url:
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [
                    KeyboardButton(
                        text="🍰 Сделать заказ",
                        web_app=WebAppInfo(url=mini_app_url),
                    ),
                    KeyboardButton(text="📞 Поддержка"),
                ]
            ],
            resize_keyboard=True,
        )
        await message.answer(WELCOME_MESSAGE, reply_markup=keyboard)
    else:
        await message.answer(WELCOME_MESSAGE)

    if message.from_user and dialog_history:
        await dialog_history.upsert_user(
            message.from_user.id, message.from_user.username
        )
        await dialog_history.clear(message.from_user.id)

    if history_logger and message.from_user:
        history_logger.log_message(
            message.from_user.id, "/start", message.from_user.username
        )

# ── Поддержка ────────────────────────────────────────────────

SUPPORT_MESSAGE = """📞 <b>Поддержка</b>

Свяжитесь с нами любым удобным способом:

📱 Телефон: +7 (343) 123-45-67
💬 WhatsApp / Telegram: +7 (912) 345-67-89
📧 Email: info@vanilka-cakes.ru

⏰ <i>Пн–Пт: 10:00–20:00 · Сб: 11:00–19:00</i>"""


@router.message(F.text == "📞 Поддержка")
async def support_handler(message: Message) -> None:
    """Handle Поддержка button press."""
    await message.answer(SUPPORT_MESSAGE)


# ── Admin: /stats ────────────────────────────────────────────

@router.message(Command("stats"))
async def command_stats_handler(message: Message) -> None:
    """Show bot statistics (admin only)."""
    if not message.from_user or not _is_admin(message.from_user.id):
        return

    if not dialog_history:
        await message.answer("Хранилище ещё не инициализировано.")
        return

    stats = await dialog_history.get_stats()
    uptime = datetime.now() - _bot_start_time
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)

    text = (
        "📊 <b>Статистика бота</b>\n\n"
        f"👥 Пользователей: <b>{stats['total_users']}</b>\n"
        f"💬 Сообщений всего: <b>{stats['total_messages']}</b>\n"
        f"📝 От пользователей: <b>{stats['user_messages']}</b>\n"
        f"🟢 Активных сегодня: <b>{stats['active_today']}</b>\n"
        f"⏱ Аптайм: <b>{hours}ч {minutes}м {seconds}с</b>"
    )
    await message.answer(text)


# ── Admin: /reload ───────────────────────────────────────────

@router.message(Command("reload"))
async def command_reload_handler(message: Message) -> None:
    """Reload knowledge base from Google Drive (admin only)."""
    if not message.from_user or not _is_admin(message.from_user.id):
        return

    if not knowledge_base_service or not llm_service:
        await message.answer("Сервисы ещё не инициализированы.")
        return

    await message.answer("🔄 Перезагружаю базу знаний...")

    content = await knowledge_base_service.load()
    if content:
        llm_service.update_knowledge_base(content)
        await message.answer(
            f"✅ База знаний обновлена ({len(content)} символов)"
        )
    else:
        await message.answer("⚠️ Не удалось загрузить базу знаний")


# ── Admin: /broadcast ────────────────────────────────────────

@router.message(Command("broadcast"))
async def command_broadcast_handler(message: Message, bot: Bot) -> None:
    """Broadcast a message to all known users (admin only)."""
    if not message.from_user or not _is_admin(message.from_user.id):
        return

    if not dialog_history:
        await message.answer("Хранилище ещё не инициализировано.")
        return

    # Extract broadcast text after "/broadcast "
    text = (message.text or "").partition(" ")[2].strip()
    if not text:
        await message.answer(
            "Использование: <code>/broadcast Текст сообщения</code>"
        )
        return

    user_ids = await dialog_history.get_all_user_ids()
    sent = 0
    failed = 0

    for uid in user_ids:
        try:
            await bot.send_message(uid, text)
            sent += 1
        except Exception:
            failed += 1

    await message.answer(
        f"📢 Рассылка завершена\n"
        f"✅ Доставлено: {sent}\n"
        f"❌ Ошибок: {failed}"
    )


# ── Text messages ────────────────────────────────────────────

@router.message(F.text)
async def text_message_handler(message: Message) -> None:
    """Handle text messages by sending to LLM."""
    if not message.text or not message.from_user:
        return

    if not llm_service or not dialog_history:
        await message.answer("Бот ещё не полностью загружен. Попробуйте позже.")
        return

    user_id = message.from_user.id

    # Register/update user
    await dialog_history.upsert_user(user_id, message.from_user.username)

    # Log user message
    if history_logger:
        history_logger.log_message(user_id, message.text, message.from_user.username)

    # Get conversation history
    history = await dialog_history.get_history(user_id)

    # Generate response
    response = await llm_service.generate_response(message.text, history)

    # Save messages to history
    await dialog_history.add_message(user_id, "user", message.text)
    await dialog_history.add_message(user_id, "assistant", response)

    await message.answer(response)


# ── Voice messages ───────────────────────────────────────────

@router.message(F.voice)
async def voice_message_handler(message: Message, bot: Bot) -> None:
    """Handle voice messages by transcribing and sending to LLM."""
    if not message.voice or not message.from_user:
        return

    if not llm_service or not transcribe_service or not dialog_history:
        await message.answer("Бот ещё не полностью загружен. Попробуйте позже.")
        return

    user_id = message.from_user.id
    await dialog_history.upsert_user(user_id, message.from_user.username)

    # Show typing indicator
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    try:
        file = await bot.get_file(message.voice.file_id)
        if not file.file_path:
            await message.answer("Не удалось получить голосовое сообщение.")
            return

        file_data = await bot.download_file(file.file_path)
        if not file_data:
            await message.answer("Не удалось скачать голосовое сообщение.")
            return

        audio_bytes = file_data.read()

        # Transcribe
        transcribed_text = await transcribe_service.transcribe(audio_bytes, "ogg")

        if not transcribed_text:
            await message.answer(
                "Не удалось распознать голосовое сообщение. "
                "Попробуйте отправить его ещё раз или напишите текстом."
            )
            return

        logger.info("Transcribed voice from user %d: %s", user_id, transcribed_text[:50])

        # Get conversation history
        history = await dialog_history.get_history(user_id)

        # Generate response
        response = await llm_service.generate_response(transcribed_text, history)

        # Save messages
        await dialog_history.add_message(user_id, "user", transcribed_text)
        await dialog_history.add_message(user_id, "assistant", response)

        await message.answer(response)

        if history_logger:
            history_logger.log_message(user_id, transcribed_text, message.from_user.username)

    except Exception as e:
        logger.error("Error processing voice message: %s", e)
        await message.answer(
            "Произошла ошибка при обработке голосового сообщения. Попробуйте позже."
        )


# ── Web App data ─────────────────────────────────────────────

@router.message(F.web_app_data)
async def web_app_data_handler(message: Message) -> None:
    """Handle data from Telegram Mini App (order submission)."""
    if not message.web_app_data:
        return

    logger.info("Received web_app_data: %s", message.web_app_data.data[:200])

    try:
        data = json.loads(message.web_app_data.data)

        if data.get("type") == "order":
            items = data.get("items", [])
            total_price = data.get("total", 0)

            text_lines = ["🛒 <b>Ваш заказ:</b>\n"]
            for idx, item in enumerate(items, 1):
                name = item.get("name", "Товар")
                qty = item.get("quantity", 1)
                text_lines.append(f"{idx}. {name} x {qty} шт.")

            text_lines.append(f"\nна сумму <b>{total_price} руб.</b>")

            pickup_date = data.get("pickup_date", "")
            pickup_time = data.get("pickup_time", "")
            if pickup_date and pickup_time:
                # Convert 2026-02-18 → 18.02.2026
                parts = pickup_date.split("-")
                if len(parts) == 3:
                    date_formatted = f"{parts[2]}.{parts[1]}.{parts[0]}"
                else:
                    date_formatted = pickup_date
                text_lines.append(f"будет ждать вас <b>{date_formatted}</b> к <b>{pickup_time}</b>")

            text_lines.append("\n🙏 <i>Спасибо за заказ!</i>")

            order_text = "\n".join(text_lines)
            await message.answer(order_text)

            # Save clean version to history (no emojis, no HTML)
            if history_logger and message.from_user:
                history_lines = ["Заказ:\n"]
                for idx, item in enumerate(items, 1):
                    name = item.get("name", "Товар")
                    qty = item.get("quantity", 1)
                    history_lines.append(f"{idx}. {name} x {qty} шт.")
                history_lines.append(f"\nна сумму {total_price} руб.")
                if pickup_date and pickup_time:
                    history_lines.append(f"будет ждать вас {date_formatted} к {pickup_time}")
                history_logger.log_message(
                    message.from_user.id,
                    "\n".join(history_lines),
                    message.from_user.username,
                )

    except json.JSONDecodeError:
        await message.answer("Ошибка при обработке заказа. Попробуйте ещё раз.")
    except Exception as e:
        logger.error("Error processing web_app_data: %s", e)
        await message.answer("Произошла ошибка при обработке заказа.")
