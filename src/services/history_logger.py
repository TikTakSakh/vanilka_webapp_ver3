"""Service for logging user messages to file system."""
from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

from beartype import beartype

logger = logging.getLogger(__name__)


@beartype
class HistoryLogger:
    """Service to log user messages to text files."""

    def __init__(self, base_dir: str | Path = "history") -> None:
        """Initialize the history logger.
        
        Args:
            base_dir: Directory where log files will be stored.
        """
        self.base_dir = Path(base_dir)
        try:
            self.base_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error("Failed to create history directory: %s", e)

    def log_message(self, user_id: int, text: str, username: str | None = None) -> None:
        """Log a message to the user's history file.
        
        Args:
            user_id: Telegram user ID.
            text: Message content.
            username: Optional username.
        """
        try:
            # Ensure safe text (remove newlines for one-line format)
            safe_text = text.replace("\n", " ").replace("\r", " ")
            
            timestamp = datetime.now().strftime("%Y-%m-%d, %H:%M:%S")
            log_entry = f"{timestamp}, {safe_text}\n"
            
            # Use "username - user_id" format if username is available
            filename = f"{username} - {user_id}.txt" if username else f"{user_id}.txt"
            file_path = self.base_dir / filename
            
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(log_entry)
                
            logger.debug("Logged message for user %d", user_id)
            
        except Exception as e:
            logger.error("Failed to log message for user %d: %s", user_id, e)
