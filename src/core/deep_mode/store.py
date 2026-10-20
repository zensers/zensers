from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


def _jsonable(value: Any) -> Any:
    if hasattr(value, "to_data_point"):
        return _jsonable(value.to_data_point())
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    return value


class DeepModeStore:
    def __init__(self, base_dir: str | Path = "data/deep_mode") -> None:
        self.base_dir = Path(base_dir)

    def save(
        self,
        *,
        task_id: str,
        plan: Any,
        queries: Any,
        records: Any,
        validation: Any,
        tables: Any,
        summary: Any,
    ) -> None:
        if not task_id:
            return
        target = self.base_dir / str(task_id)
        target.mkdir(parents=True, exist_ok=True)
        payloads = {
            "plan.json": plan,
            "queries.json": queries,
            "records.json": records,
            "validation.json": validation,
            "tables.md": tables,
            "summary.json": summary,
        }
        for name, payload in payloads.items():
            path = target / name
            if name == "tables.md" and isinstance(payload, str):
                text = payload
            else:
                text = json.dumps(_jsonable(payload), ensure_ascii=False, indent=2)
            path.write_text(text, encoding="utf-8")
