import logging
from string import Template
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)


class PromptManager:

    def __init__(self, prompts_dir: Path = None) -> None:
        if prompts_dir is None:
            prompts_dir = Path(__file__).parent / "prompts"
        self._prompts_dir = prompts_dir
        self._cache: Dict[str, Template] = {}

    def get(self, name: str, **kwargs: Any) -> str:
        template = self._load_template(name)
        # New report-evidence fields are optional for legacy callers and old
        # checkpoint-driven tests.  Writers always provide them explicitly.
        kwargs.setdefault("global_evidence_pool_json", "无可用原始搜索证据")
        kwargs.setdefault("chapter_requirements_json", "无明确章节需求")
        kwargs.setdefault("used_evidence_ids_json", "[]")
        kwargs.setdefault("raw_data_location", "未提供（请使用当前任务上下文中的原始数据）")
        # Tool guidance placeholders are always provided by ChapterWriter;
        # legacy callers and old tests that render the template directly
        # fall back to tool-free wording (no read_json instructions).
        kwargs.setdefault("data_read_step", "通读下方提供的章节数据与证据，了解报告涉及的全部数据。")
        kwargs.setdefault("raw_data_guidance", "")
        try:
            return template.substitute(**kwargs)
        except KeyError as e:
            logger.error(f"Prompt template '{name}' missing variable: {e}")
            raise

    def _load_template(self, name: str) -> Template:
        if name not in self._cache:
            path = self._prompts_dir / f"{name}.tmpl"
            if not path.exists():
                raise FileNotFoundError(f"Prompt template not found: {path}")
            content = path.read_text(encoding="utf-8")
            self._cache[name] = Template(content)
            logger.debug(f"Loaded prompt template: {name}")
        return self._cache[name]

    def reload(self, name: str = None) -> None:
        if name:
            self._cache.pop(name, None)
        else:
            self._cache.clear()
