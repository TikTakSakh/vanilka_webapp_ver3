"""In-memory dialog history storage."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Literal

from beartype import beartype


@dataclass
class Message:
    """A single message in the dialog history."""

    role: Literal["user", "assistant"]
    content: str


@beartype
@dataclass
class DialogHistory:
    """In-memory storage for dialog histories by user ID.
    
    Stores the last N messages for each user to provide context
    for LLM conversations.
    """

    max_messages: int = 20
    _history: dict[int, list[Message]] = field(
        default_factory=lambda: defaultdict(list)
    )

    def add_message(self, user_id: int, role: Literal["user", "assistant"], content: str) -> None:
        """Add a message to the user's dialog history.
        
        Args:
            user_id: Telegram user ID.
            role: Message role - 'user' or 'assistant'.
            content: Message content.
        """
        messages = self._history[user_id]
        messages.append(Message(role=role, content=content))
        
        # Keep only the last max_messages
        if len(messages) > self.max_messages:
            self._history[user_id] = messages[-self.max_messages:]

    def get_history(self, user_id: int) -> list[dict[str, str]]:
        """Get dialog history for a user in OpenAI message format.
        
        Args:
            user_id: Telegram user ID.
            
        Returns:
            List of message dicts with 'role' and 'content' keys.
        """
        return [
            {"role": msg.role, "content": msg.content}
            for msg in self._history[user_id]
        ]

    def clear(self, user_id: int) -> None:
        """Clear dialog history for a user.
        
        Args:
            user_id: Telegram user ID.
        """
        self._history[user_id] = []

    def get_message_count(self, user_id: int) -> int:
        """Get the number of messages in user's history.
        
        Args:
            user_id: Telegram user ID.
            
        Returns:
            Number of messages stored.
        """
        return len(self._history[user_id])
