"""Knowledge base service for loading data from Google Drive."""
from __future__ import annotations

import asyncio
import io
import logging
from pathlib import Path

from beartype import beartype
from docx import Document
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


@beartype
class KnowledgeBaseService:
    """Service for loading and caching knowledge base from Google Drive."""

    def __init__(
        self,
        file_id: str,
        service_account_path: Path,
        cache_path: Path,
    ) -> None:
        """Initialize the knowledge base service.
        
        Args:
            file_id: Google Drive file ID to load.
            service_account_path: Path to service account JSON file.
            cache_path: Path to local cache file.
        """
        self._file_id = file_id
        self._service_account_path = service_account_path
        self._cache_path = cache_path
        self._content: str = ""
        self._service = None

    def _get_drive_service(self):
        """Get or create Google Drive API service."""
        if self._service is None:
            credentials = service_account.Credentials.from_service_account_file(
                str(self._service_account_path),
                scopes=SCOPES,
            )
            self._service = build("drive", "v3", credentials=credentials)
        return self._service

    async def load(self) -> str:
        """Load knowledge base from Google Drive.
        
        Downloads the file and caches it locally.
        
        Returns:
            Knowledge base content as text.
        """
        try:
            service = self._get_drive_service()
            
            def download_file(request) -> bytes:
                file_buffer = io.BytesIO()
                downloader = MediaIoBaseDownload(file_buffer, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
                return file_buffer.getvalue()

            file_bytes = b""
            
            # 1. Try to export (assuming it's a Google Doc)
            try:
                request = service.files().export_media(
                    fileId=self._file_id,
                    mimeType="text/plain",
                )
                logger.info("Attempting to export Google Drive file...")
                # Export returns bytes content directly
                file_bytes = await asyncio.to_thread(download_file, request)
                
            except Exception as e:
                # If export fails (e.g. it's not a Google Doc), try direct download
                logger.info("Export failed (%s), trying direct download...", e)
                
                request = service.files().get_media(fileId=self._file_id)
                file_bytes = await asyncio.to_thread(download_file, request)

            # Process downloaded bytes
            try:
                # Try to decode as UTF-8 (text files)
                self._content = file_bytes.decode("utf-8")
            except UnicodeDecodeError:
                # Try to parse as .docx
                try:
                    logger.info("UTF-8 decode failed, attempting to parse as .docx...")
                    # docx.Document expects a file-like object
                    doc = Document(io.BytesIO(file_bytes))
                    self._content = "\n".join([paragraph.text for paragraph in doc.paragraphs])
                except Exception as e:
                    logger.error("Failed to parse as .docx: %s", e)
                    # Fallback
                    self._content = ""
                    raise ValueError("Could not decode file content (not UTF-8 and not valid .docx)")

            # Cache locally
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(self._content, encoding="utf-8")
            
            logger.info(
                "Knowledge base loaded from Google Drive, %d chars",
                len(self._content),
            )
            return self._content
            
        except Exception as e:
            logger.error("Error loading knowledge base from Google Drive: %s", e)
            return self._load_from_cache()

    def _load_from_cache(self) -> str:
        """Load knowledge base from local cache.
        
        Returns:
            Cached content or empty string if cache doesn't exist.
        """
        if self._cache_path.exists():
            self._content = self._cache_path.read_text(encoding="utf-8")
            logger.info(
                "Knowledge base loaded from cache, %d chars",
                len(self._content),
            )
            return self._content
        
        logger.warning("No cached knowledge base found")
        return ""

    @property
    def content(self) -> str:
        """Get current knowledge base content."""
        return self._content
