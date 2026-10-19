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
        report: Optional[dict] = None,
        artifacts: Optional[dict] = None,
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

        snapshot_state = dict(quality_state or {})
        if isinstance(report, dict):
            # Keep the legacy quality-state file shape for callers that do
            # not need report restoration, while carrying the complete report
            # payload required by a lossless quality rollback when requested.
            snapshot_state["_snapshot_report"] = report
        if isinstance(artifacts, dict):
            # Keep the pointers alongside the snapshot so rollback can restore
            # the report payload and the artifacts that represent it as one
            # consistent version.
            snapshot_state["_snapshot_artifacts"] = dict(artifacts)
            artifact_files = {}
            for key in ("document_path", "output_path"):
                original = artifacts.get(key)
                if original and Path(str(original)).is_file():
                    target = snap_dir / f"{version_id}_artifact_{Path(str(original)).name}"
                    shutil.copy2(str(original), str(target))
                    artifact_files[str(original)] = str(target)
            for item in artifacts.get("artifact_manifest", []) or []:
                if not isinstance(item, dict):
                    continue
                original = item.get("path")
                if original and Path(str(original)).is_file() and str(original) not in artifact_files:
                    target = snap_dir / f"{version_id}_artifact_{Path(str(original)).name}"
                    shutil.copy2(str(original), str(target))
                    artifact_files[str(original)] = str(target)
            snapshot_state["_snapshot_artifact_files"] = artifact_files
        (snap_dir / f"{version_id}_quality.json").write_text(
            json.dumps(snapshot_state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return version_id

    async def restore_snapshot(self, session_id: str, version_id: str) -> Optional[dict]:
        snap_dir = self.base_dir / session_id
        quality_json = snap_dir / f"{version_id}_quality.json"
        if not quality_json.exists():
            return None
        quality_state = json.loads(quality_json.read_text(encoding="utf-8"))
        snapshot_report = quality_state.pop("_snapshot_report", None)
        snapshot_artifacts = quality_state.pop("_snapshot_artifacts", None)
        artifact_files = quality_state.pop("_snapshot_artifact_files", {})
        result: Dict[str, object] = {"quality_state": quality_state}
        if isinstance(snapshot_report, dict):
            result["report"] = snapshot_report
        if isinstance(snapshot_artifacts, dict):
            for original, archived in artifact_files.items():
                if Path(str(archived)).is_file():
                    Path(str(original)).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(archived), str(original))
            result["artifacts"] = snapshot_artifacts
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
                for artifact in snap_dir.glob(f"{stem}_artifact_*"):
                    artifact.unlink(missing_ok=True)
