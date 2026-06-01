# -*- coding: utf-8 -*-
"""
质检版本快照管理器

设计文档: docs/2026-06-01-quality-feedback-revision-design.md
"""

import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional


class QualitySnapshotManager:

    def __init__(self, base_dir: str = "data/snapshots"):
        self.base_dir = Path(base_dir)

    async def create_snapshot(
        self,
        session_id: str,
        html_path: str,
        md_path: str,
        quality_state: dict,
    ) -> str:
        version_n = len(quality_state.get("version_stack", []))
        version_id = f"v{version_n}"
        snap_dir = self.base_dir / session_id
        snap_dir.mkdir(parents=True, exist_ok=True)

        html_src = Path(html_path)
        if html_src.exists():
            shutil.copy2(str(html_src), str(snap_dir / f"{version_id}.html"))

        md_src = Path(md_path)
        if md_src.exists():
            shutil.copy2(str(md_src), str(snap_dir / f"{version_id}.md"))

        (snap_dir / f"{version_id}_quality.json").write_text(
            json.dumps(quality_state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return version_id

    async def restore_snapshot(self, session_id: str, version_id: str) -> Optional[dict]:
        snap_dir = self.base_dir / session_id
        quality_json = snap_dir / f"{version_id}_quality.json"
        if not quality_json.exists():
            return None
        quality_state = json.loads(quality_json.read_text(encoding="utf-8"))
        result: Dict[str, object] = {"quality_state": quality_state}
        html_snap = snap_dir / f"{version_id}.html"
        if html_snap.exists():
            result["html_path"] = str(html_snap)
        md_snap = snap_dir / f"{version_id}.md"
        if md_snap.exists():
            result["md_path"] = str(md_snap)
        return result

    async def list_snapshots(self, session_id: str) -> List[dict]:
        snap_dir = self.base_dir / session_id
        if not snap_dir.exists():
            return []
        versions: List[dict] = []
        for qf in sorted(snap_dir.glob("v*_quality.json")):
            stem = qf.stem.replace("_quality", "")
            quality_data = json.loads(qf.read_text(encoding="utf-8"))
            versions.append({
                "version_id": stem,
                "overall_score": quality_data.get("overall_score", 0.0),
                "phase": quality_data.get("phase", ""),
            })
        return versions

    async def cleanup_old(self, session_id: str, keep: int = 10):
        snap_dir = self.base_dir / session_id
        if not snap_dir.exists():
            return
        versions = sorted(snap_dir.glob("v*_quality.json"))
        if len(versions) > keep:
            for qf in versions[:-keep]:
                stem = qf.stem.replace("_quality", "")
                qf.unlink(missing_ok=True)
                (snap_dir / f"{stem}.html").unlink(missing_ok=True)
                (snap_dir / f"{stem}.md").unlink(missing_ok=True)
