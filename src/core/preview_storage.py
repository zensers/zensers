"""Centralized preview/report HTML storage manager."""

import shutil
from pathlib import Path


class PreviewStorage:
    NEW_DIR = Path("data/html_reports")
    OLD_DIR = Path("data/previews")

    @classmethod
    def ensure_dirs(cls):
        cls.NEW_DIR.mkdir(parents=True, exist_ok=True)
        cls.OLD_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def write(cls, task_id: str, html: str):
        cls.ensure_dirs()
        cls._write_html(task_id, html, cls.NEW_DIR)
        cls._write_html(task_id, html, cls.OLD_DIR)

    @classmethod
    def _write_html(cls, task_id: str, html: str, target_dir: Path):
        """Write HTML file and ensure charts directory exists."""
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / f"{task_id}.html").write_text(html, encoding="utf-8")
        # Ensure charts subdirectory exists for external chart images
        (target_dir / "charts").mkdir(parents=True, exist_ok=True)

    @classmethod
    def copy_file(cls, task_id: str, source_path: Path):
        cls.ensure_dirs()
        for d in [cls.NEW_DIR, cls.OLD_DIR]:
            shutil.copy2(str(source_path), str(d / f"{task_id}.html"))
            # Also copy charts subdirectory if it exists alongside source
            src_charts = source_path.parent / "charts"
            if src_charts.exists():
                dst_charts = d / "charts"
                dst_charts.mkdir(parents=True, exist_ok=True)
                for chart_file in src_charts.iterdir():
                    if chart_file.is_file():
                        shutil.copy2(str(chart_file), str(dst_charts / chart_file.name))

    @classmethod
    def path(cls, task_id: str) -> Path:
        return cls.NEW_DIR / f"{task_id}.html"

    @classmethod
    def url(cls, task_id: str) -> str:
        return f"/api/v1/html-reports/{task_id}.html"
