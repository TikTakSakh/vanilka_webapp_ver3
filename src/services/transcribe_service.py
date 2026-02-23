"""Voice transcription service using local OpenAI Whisper."""
from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

import whisper

logger = logging.getLogger(__name__)


class TranscribeService:
    """Service for transcribing voice messages using local Whisper model."""

    def __init__(self, model_name: str = "base") -> None:
        """Initialize the transcription service and load the Whisper model.

        Args:
            model_name: Whisper model to load (tiny, base, small, medium, turbo).
        """
        logger.info("Loading Whisper model '%s'...", model_name)
        self._model = whisper.load_model(model_name)
        logger.info("Whisper model '%s' loaded successfully", model_name)

    async def transcribe(self, audio_data: bytes, file_extension: str = "ogg") -> str:
        """Transcribe audio data to text.

        Args:
            audio_data: Raw audio bytes (OGG/OPUS from Telegram).
            file_extension: Audio file extension for the temp file.

        Returns:
            Transcribed text or empty string on failure.
        """
        try:
            # Write audio bytes to a temporary file (Whisper needs a file path)
            with tempfile.NamedTemporaryFile(
                suffix=f".{file_extension}", delete=False
            ) as tmp:
                tmp.write(audio_data)
                tmp_path = tmp.name

            # Run Whisper transcription in a thread to avoid blocking the event loop
            result = await asyncio.to_thread(
                self._model.transcribe,
                tmp_path,
                language="ru",
                fp16=False,  # CPU-safe; set True if GPU available
            )

            transcript = result.get("text", "").strip()

            # Cleanup temp file
            try:
                Path(tmp_path).unlink()
            except OSError:
                pass

            if not transcript:
                logger.warning("Whisper returned empty transcription")
                return ""

            logger.info("Transcription successful: %d chars", len(transcript))
            return transcript

        except Exception as e:
            logger.error("Error transcribing audio: %s", e, exc_info=True)
            return ""
