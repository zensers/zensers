"""
Session History Compressor
==========================

Adapts HistoryCompressor to the global SessionManager for compressing
conversation_history in-flight.

Design:
- Lightweight: no new persistence, reads/writes directly through SessionManager
- Safe: compresses only when size exceeds threshold, keeps full backup in gzip
- Non-blocking: failures are logged, never raise
- Thread-safe: uses Lock for compressor cache access
- Memory-safe: LRU eviction of compressor cache (max 100 entries)
"""

import logging
import os
import threading
from collections import OrderedDict
from typing import Optional, Dict as TypedDict

logger = logging.getLogger(__name__)


class SessionHistoryCompressor:
    """
    Wraps HistoryCompressor for the global SessionManager.

    Attach to SessionManager; on each write, if conversation_history exceeds
    threshold, it is compressed in-place.
    """

    # Size thresholds (same as HistoryCompressor defaults)
    DEFAULT_STEP_LIMIT = 20
    DEFAULT_SIZE_LIMIT_KB = 50
    MAX_COMPRESSOR_CACHE = 100

    def __init__(
        self,
        step_limit: int = DEFAULT_STEP_LIMIT,
        size_limit_kb: int = DEFAULT_SIZE_LIMIT_KB,
        archive_base: Optional[str] = None,
    ):
        self._step_limit = step_limit
        self._size_limit_kb = size_limit_kb
        self._archive_base = archive_base or "data/sessions/archives"
        self._lock = threading.Lock()
        self._compressors: "OrderedDict[str, object]" = OrderedDict()

    def _get_compressor(self, session_id: str, user_id: str = "default"):
        with self._lock:
            if session_id in self._compressors:
                self._compressors.move_to_end(session_id)
                return self._compressors[session_id]

            from src.core.memory.compressor.history_compressor import HistoryCompressor
            safe_user_id = user_id if user_id else "default"
            archive_path = f"{self._archive_base}/{safe_user_id}"
            os.makedirs(archive_path, exist_ok=True)

            compressor = HistoryCompressor(
                user_id=user_id,
                session_id=session_id,
                max_full_steps=5,
                max_summary_steps=self._step_limit,
                size_limit_kb=self._size_limit_kb,
                archive_path=archive_path,
            )
            self._compressors[session_id] = compressor

            if len(self._compressors) > self.MAX_COMPRESSOR_CACHE:
                self._compressors.popitem(last=False)

            return compressor

    def compress_if_needed(self, session_id: str, session: dict) -> None:
        """
        Check and compress conversation_history if it exceeds thresholds.

        Triggers when EITHER step count or size exceeds limit.
        display_history is always preserved (never compressed).
        """
        history = session.get("conversation_history")
        if not history or not isinstance(history, list):
            return

        import json
        history_len = len(history)
        size_kb = len(json.dumps(history, ensure_ascii=False).encode("utf-8")) / 1024

        needs_compress = history_len > self._step_limit or size_kb > self._size_limit_kb
        if not needs_compress:
            return

        try:
            user_id = session.get("user_id", "default")
            compressor = self._get_compressor(session_id, user_id)
            result = compressor.compress(history)
            # Save full history to display_history BEFORE compression
            dict.__setitem__(session, "display_history", list(history))
            # Compress conversation_history (for LLM context only)
            dict.__setitem__(session, "conversation_history", result["history"])
            dict.__setitem__(session, "_compressed", True)
            logger.info(
                f"History compressed: {session_id} "
                f"({len(history)} -> {len(result['history'])} steps, "
                f"ratio={result['compression_ratio']:.1%}), "
                f"display_history preserved ({len(history)} items)"
            )
        except Exception as e:
            logger.warning(f"History compression failed for {session_id}: {e}")
