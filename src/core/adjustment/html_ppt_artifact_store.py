"""Persistent HTML-first artifact state for PPT preview and revision."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Optional


class HtmlPptArtifactStore:
    """Store the HTML draft as the source of truth before final export."""

    def __init__(self, data_dir: str, task_id: str):
        self.root = Path(data_dir) / "ppt_html" / task_id
        self.root.mkdir(parents=True, exist_ok=True)
        self.html_path = self.root / "draft.html"
        self.state_path = self.root / "state.json"
        self.revisions_dir = self.root / "revisions"
        self.revisions_dir.mkdir(exist_ok=True)

    def initialize(self, html: str, content_model: Optional[Dict[str, Any]] = None,
                   *, replace: bool = False) -> Dict[str, Any]:
        if not isinstance(html, str) or not html.strip():
            raise ValueError("HTML draft must not be empty")
        if self.html_path.exists() and not replace:
            return self.state()
        version = int(self.state().get("version", 0)) + 1 if replace and self.state_path.exists() else 1
        self._write_html(html)
        state = {
            "task_id": self.html_path.parent.name,
            "version": version,
            "status": "HTML_DRAFT",
            "html_path": str(self.html_path),
            "html_hash": self._hash(html),
            "content_model": content_model or {},
            "audit": None,
            "pptx_path": None,
        }
        self._write_state(state)
        self._snapshot(state, html)
        return state

    def load_html(self) -> str:
        if not self.html_path.exists():
            raise FileNotFoundError(f"HTML draft not found: {self.html_path}")
        return self.html_path.read_text(encoding="utf-8")

    def state(self) -> Dict[str, Any]:
        if not self.state_path.exists():
            raise FileNotFoundError(f"HTML artifact state not found: {self.state_path}")
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def commit(self, html: str, *, audit: Optional[Dict[str, Any]] = None,
               content_model: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        current = self.state()
        version = int(current.get("version", 0)) + 1
        self._write_html(html)
        current.update({
            "version": version,
            "status": "HTML_AUDITED" if audit and audit.get("passed") else "HTML_DRAFT",
            "html_hash": self._hash(html),
            "audit": audit,
        })
        if content_model is not None:
            current["content_model"] = content_model
        self._write_state(current)
        self._snapshot(current, html)
        return current

    def restore(self, version: int) -> Dict[str, Any]:
        snapshot = self.revisions_dir / f"v{int(version)}.html"
        state_path = self.revisions_dir / f"v{int(version)}.json"
        if not snapshot.exists() or not state_path.exists():
            raise ValueError(f"HTML revision {version} not found")
        shutil.copy2(snapshot, self.html_path)
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["status"] = "HTML_ROLLED_BACK"
        self._write_state(state)
        return state

    def set_audit(self, audit: Dict[str, Any]) -> Dict[str, Any]:
        state = self.state()
        state["audit"] = audit
        state["status"] = "HTML_AUDITED" if audit.get("passed") else "HTML_AUDIT_FAILED"
        self._write_state(state)
        return state

    def confirm(self) -> Dict[str, Any]:
        state = self.state()
        if not state.get("audit", {}).get("passed"):
            raise ValueError("HTML must pass audit before confirmation")
        state["status"] = "HTML_CONFIRMED"
        self._write_state(state)
        return state

    def mark_exported(self, pptx_path: str) -> Dict[str, Any]:
        state = self.state()
        if state.get("status") != "HTML_CONFIRMED":
            raise ValueError("Only HTML_CONFIRMED artifacts can be exported")
        state["status"] = "PPTX_EXPORTED"
        state["pptx_path"] = pptx_path
        self._write_state(state)
        return state

    def _snapshot(self, state: Dict[str, Any], html: str) -> None:
        version = state["version"]
        (self.revisions_dir / f"v{version}.html").write_text(html, encoding="utf-8")
        snapshot_state = dict(state)
        (self.revisions_dir / f"v{version}.json").write_text(
            json.dumps(snapshot_state, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _write_html(self, html: str) -> None:
        temp = self.html_path.with_suffix(".tmp")
        temp.write_text(html, encoding="utf-8")
        os.replace(temp, self.html_path)

    def _write_state(self, state: Dict[str, Any]) -> None:
        temp = self.state_path.with_suffix(".tmp")
        temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self.state_path)

    @staticmethod
    def _hash(html: str) -> str:
        return hashlib.sha256(html.encode("utf-8")).hexdigest()
