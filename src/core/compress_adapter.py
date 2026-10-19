"""
Session History Compressor
==========================

Adapts HistoryCompressor to the global SessionManager for compressing
conversation_history in-flight.

Design:
- Append-only: compression appends a summary entry, never replaces original records
- conversation_history is never truncated — all original messages are preserved
- LLM context is built separately (summary + recent N messages), not from compressed history
- Lightweight: no new persistence, reads/writes directly through SessionManager
- Safe: failures are logged, never raise
- Thread-safe: uses Lock for compressor cache access
- Memory-safe: LRU eviction of compressor cache (max 100 entries)
"""

import logging
import os
import threading
from collections import OrderedDict
from datetime import datetime
from typing import Optional, Dict as TypedDict

logger = logging.getLogger(__name__)


class SessionHistoryCompressor:
    """
    Wraps HistoryCompressor for the global SessionManager.

    Attach to SessionManager; on each write, if conversation_history exceeds
    threshold, a context_summary entry is APPENDED (original records are never deleted).
    """

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
        self._last_compressed_len: dict = {}

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
        Check and append a context_summary if conversation_history exceeds thresholds.

        Original records are NEVER deleted. A summary entry is appended to
        conversation_history with type="context_summary". LLM context builders
        should filter out context_summary entries and use only recent messages.
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

        last_len = self._last_compressed_len.get(session_id, 0)
        if history_len <= last_len:
            return

        non_summary_count = sum(1 for m in history if m.get("type") != "context_summary")
        existing_summaries = [m for m in history if m.get("type") == "context_summary"]
        if existing_summaries:
            latest_summary = existing_summaries[-1]
            last_covered = latest_summary.get("steps_covered", 0)
            if non_summary_count <= last_covered + 5:
                return

        try:
            user_id = session.get("user_id", "default")
            compressor = self._get_compressor(session_id, user_id)
            result = compressor.compress(history)

            summary_entry = {
                "type": "context_summary",
                "role": "system",
                "content": result["history"][0].get("content", "") if result["history"] else "",
                "steps_covered": non_summary_count,
                "step_range": {
                    "start": 1,
                    "end": non_summary_count,
                },
                "created_at": datetime.now().isoformat(),
            }

            history.append(summary_entry)
            dict.__setitem__(session, "conversation_history", history)

            self._last_compressed_len[session_id] = history_len

            logger.info(
                f"History summary appended: {session_id} "
                f"({history_len} original messages + 1 summary), "
                f"compression_ratio={result['compression_ratio']:.1%}"
            )
        except Exception as e:
            logger.warning(f"History compression failed for {session_id}: {e}")
