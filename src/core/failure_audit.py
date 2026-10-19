# src/core/failure_audit.py
# -*- coding: utf-8 -*-
"""I2 失败留痕：任何放弃/降级/跳过必须结构化留痕（I2 不变量执行器）。"""
from __future__ import annotations
import json, logging, os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class FailureAudit:
    @staticmethod
    def record(stage: str, subject_id: str, action: str, reason: str, *,
               detail: str = "", severity: str = "warn",
               delivery_impact: str = "none", task_id = None) -> None:
        try:
            tid = str(task_id or "unknown")
            row = {
                "timestamp": datetime.now().isoformat(),
                "task_id": tid, "stage": stage, "subject_id": str(subject_id),
                "action": action, "reason": reason, "detail": detail[:500],
                "severity": severity, "delivery_impact": delivery_impact,
            }
            base = Path(os.environ.get("FAILURE_AUDIT_DIR", "data/failure_audit"))
            base.mkdir(parents=True, exist_ok=True)
            with open(base / f"{tid}.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception as audit_error:
            logger.debug("FailureAudit write failed: %s", audit_error)
        logger.warning("[FAILURE_AUDIT] %s/%s %s: %s (%s)",
                       stage, subject_id, action, reason, delivery_impact)
