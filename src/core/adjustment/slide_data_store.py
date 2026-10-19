import json
import hashlib
import os
import shutil
from typing import Any, Dict, List, Optional


class SlideDataStore:

    def __init__(self, data_dir: str, task_id: str = ""):
        self._data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self._task_id = task_id
        self._meta: Dict[str, Dict[str, Any]] = {}
        if task_id:
            self._load_persisted_meta(task_id)

    def _load_persisted_meta(self, task_id: str) -> None:
        path = os.path.join(self._data_dir, f"{task_id}.json")
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            self._meta[task_id] = {
                "version": payload.get("version", 0),
                "hash": payload.get("hash"),
            }
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid slide data state for task {task_id}: {exc}") from exc

    @property
    def pptx_path(self) -> Optional[str]:
        if self._task_id:
            return self.get_pptx_path(self._task_id)
        return None

    @pptx_path.setter
    def pptx_path(self, value: str) -> None:
        if self._task_id:
            self.set_pptx_path(self._task_id, value)

    def persist(self, task_id: str, slide_data_list: List[Dict]) -> None:
        path = os.path.join(self._data_dir, f"{task_id}.json")
        if os.path.exists(path):
            bak_path = os.path.join(self._data_dir, f"{task_id}.json.bak")
            shutil.copy2(path, bak_path)
        pptx_path = self._meta.get(task_id, {}).get("pptx_path")
        version = self._meta.get(task_id, {}).get("version", 0) + 1
        content_hash = self._compute_hash(slide_data_list)
        payload = {
            "slides": slide_data_list,
            "version": version,
            "hash": content_hash,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        self._meta[task_id] = {
            "version": version,
            "hash": content_hash,
        }
        if pptx_path:
            self._meta[task_id]["pptx_path"] = pptx_path

    def load(self, task_id: str) -> List[Dict]:
        path = os.path.join(self._data_dir, f"{task_id}.json")
        if not os.path.exists(path):
            raise FileNotFoundError(f"No slide data for task {task_id}")
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload["slides"]

    def get_version(self, task_id: str) -> int:
        return self._meta.get(task_id, {}).get("version", 0)

    def get_hash(self, task_id: str) -> Optional[str]:
        return self._meta.get(task_id, {}).get("hash")

    def check_version(self, task_id: str, expected_version: int) -> bool:
        return self.get_version(task_id) == expected_version

    def set_pptx_path(self, task_id: str, pptx_path: str) -> None:
        meta = self._meta.setdefault(task_id, {})
        meta["pptx_path"] = pptx_path

    def get_pptx_path(self, task_id: str) -> Optional[str]:
        return self._meta.get(task_id, {}).get("pptx_path")

    def restore_backup(self, task_id: str) -> None:
        bak_path = os.path.join(self._data_dir, f"{task_id}.json.bak")
        if not os.path.exists(bak_path):
            raise FileNotFoundError(f"No backup for task {task_id}")
        path = os.path.join(self._data_dir, f"{task_id}.json")
        pptx_path = self._meta.get(task_id, {}).get("pptx_path")
        shutil.copy2(bak_path, path)
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        self._meta[task_id] = {
            "version": payload.get("version", 0),
            "hash": payload.get("hash"),
        }
        if pptx_path:
            self._meta[task_id]["pptx_path"] = pptx_path

    def capture_state(self, task_id: str) -> Dict[str, Any]:
        """Capture logical state without changing the persisted version."""
        path = os.path.join(self._data_dir, f"{task_id}.json")
        if not os.path.exists(path):
            raise FileNotFoundError(f"No slide data for task {task_id}")
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return {
            "slides": payload.get("slides", []),
            "version": payload.get("version", 0),
            "hash": payload.get("hash"),
            "pptx_path": self._meta.get(task_id, {}).get("pptx_path"),
        }

    def restore_state(self, task_id: str, state: Dict[str, Any]) -> None:
        """Restore a captured state without creating a new logical version."""
        path = os.path.join(self._data_dir, f"{task_id}.json")
        payload = {
            "slides": state.get("slides", []),
            "version": state.get("version", 0),
            "hash": state.get("hash") or self._compute_hash(state.get("slides", [])),
        }
        temp_path = f"{path}.restore.tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(temp_path, path)
        self._meta[task_id] = {
            "version": payload["version"],
            "hash": payload["hash"],
        }
        if state.get("pptx_path"):
            self._meta[task_id]["pptx_path"] = state["pptx_path"]

    @staticmethod
    def _compute_hash(slide_data_list: List[Dict]) -> str:
        canonical = json.dumps(slide_data_list, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
