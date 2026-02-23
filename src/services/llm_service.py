"""LLM service for GPT-4o-mini integration."""
from __future__ import annotations

import logging

from beartype import beartype
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """Ты — дружелюбный AI-администратор магазина бенто-тортов "Ванилька". 
Твоя задача — помогать клиентам с информацией о продукции, ценах, графике работы и условиях заказа.

Правила общения:
- Будь вежливым, дружелюбным и профессиональным
- Отвечай только на вопросы, связанные с магазином и его продукцией
- Если вопрос не касается магазина, вежливо перенаправь разговор на тему тортов
- Используй эмодзи для создания дружелюбной атмосферы 🎂
- Если не знаешь ответа, предложи связаться с магазином напрямую

Информация о магазине:
{knowledge_base}
"""


@beartype
class LLMService:
    """Service for generating responses using GPT-4o-mini."""

    def __init__(self, api_key: str, base_url: str | None = None, knowledge_base: str = "") -> None:
        """Initialize the LLM service.
        
        Args:
            api_key: OpenAI API key.
            base_url: Optional base URL for API (e.g. for OpenRouter).
            knowledge_base: Knowledge base content to include in system prompt.
        """
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._knowledge_base = knowledge_base
        self._model = "gpt-4o-mini"

    def update_knowledge_base(self, knowledge_base: str) -> None:
        """Update the knowledge base content.
        
        Args:
            knowledge_base: New knowledge base content.
        """
        self._knowledge_base = knowledge_base
        logger.info("Knowledge base updated, length: %d chars", len(knowledge_base))

    def _get_system_prompt(self) -> str:
        """Get the system prompt with current knowledge base."""
        return SYSTEM_PROMPT_TEMPLATE.format(
            knowledge_base=self._knowledge_base or "Информация о магазине пока не загружена."
        )

    async def generate_response(
        self,
        user_message: str,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        """Generate a response to the user's message.
        
        Args:
            user_message: The user's message text.
            history: Optional conversation history in OpenAI format.
            
        Returns:
            Generated response text.
        """
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self._get_system_prompt()}
        ]
        
        if history:
            messages.extend(history)
        
        messages.append({"role": "user", "content": user_message})
        
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,  # type: ignore[arg-type]
                temperature=0.7,
                max_tokens=1000,
            )
            
            content = response.choices[0].message.content
            if content is None:
                return "Извините, не удалось сгенерировать ответ. Попробуйте ещё раз."
            return content
            
        except Exception as e:
            logger.error("Error generating LLM response: %s", e)
            return "Извините, произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте позже."
