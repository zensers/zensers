# -*- coding: utf-8 -*-
"""每案例阶段状态机：state.json 落盘，支持断点续跑与 --from-stage 重置。"""
import copy
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

STAGES: List[str] = ["research", "charts", "render", "review", "finalize"]


class CaseState:
    def __init__(self, path: Path, case_id: str):
        self.path = path
        self.case_id = case_id
        self.data: Dict[str, Any] = {
            "case_id": case_id, "stages": {}, "case_status": "pending",
        }

    @classmethod
    def load(cls, path: Path, case_id: str) -> "CaseState":
        cs = cls(path, case_id)
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and isinstance(raw.get("stages"), dict):
                    cs.data = raw
            except (json.JSONDecodeError, OSError):
                logger.warning("状态文件损坏，重置: %s", path)
        return cs

    def mark_running(self, stage: str) -> None:
        self._check_stage(stage)
        self.data["stages"][stage] = {"status": "running"}

    def mark_done(self, stage: str, meta: Optional[Dict[str, Any]] = None) -> None:
        self._check_stage(stage)
        self.data["stages"][stage] = {"status": "done", "meta": copy.deepcopy(meta or {})}

    def mark_failed(self, stage: str, error: str) -> None:
        self._check_stage(stage)
        self.data["stages"][stage] = {"status": "failed", "error": error}

    def _check_stage(self, stage: str) -> None:
        if stage not in STAGES:
            raise ValueError(f"未知阶段: {stage}")

    def is_done(self, stage: str) -> bool:
        return self.data["stages"].get(stage, {}).get("status") == "done"

    def meta(self, stage: str) -> Dict[str, Any]:
        return copy.deepcopy(self.data["stages"].get(stage, {}).get("meta", {}))

    def current_stage(self) -> Optional[str]:
        for s in STAGES:
            if not self.is_done(s):
                return s
        return None

    def reset_from(self, stage: str) -> None:
        self._check_stage(stage)
        for s in STAGES[STAGES.index(stage):]:
            self.data["stages"].pop(s, None)
        self.data["case_status"] = "pending"

    def set_case_status(self, status: str) -> None:
        self.data["case_status"] = status

    @property
    def case_status(self) -> str:
        return self.data.get("case_status", "pending")

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
