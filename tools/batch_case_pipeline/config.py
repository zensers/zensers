# -*- coding: utf-8 -*-
"""批量案例配置加载：config/batch_cases.yaml → BatchConfig/CaseConfig。"""
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union

import yaml

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CHAPTERS = [
    "行业概览与研究范围界定", "市场规模与增长预测", "产业链全景",
    "核心零部件与降本路径", "竞争格局", "技术发展趋势",
    "应用场景与商业化", "政策环境与监管", "投融资格局与资本市场",
    "风险分析", "投资建议与策略", "结论与展望",
]
_TRADITIONAL_HINTS = ["钢铁", "煤炭", "纺织", "建材", "水泥"]


@dataclass
class CaseConfig:
    case_id: str
    topic: str
    domain_keywords: List[str] = field(default_factory=list)
    chapters: Optional[List[str]] = None
    max_total_searches: int = 60

    @property
    def effective_chapters(self) -> List[str]:
        return self.chapters or DEFAULT_CHAPTERS


@dataclass
class BatchConfig:
    max_review_rounds: int = 3
    framework: str = "standard"
    cases: List[CaseConfig] = field(default_factory=list)


def _parse_int(value: object, field_name: str,
               case_index: Union[int, None] = None) -> int:
    where = f"cases[{case_index}]" if case_index is not None else "配置根节点"
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ValueError(f"{where} 字段 {field_name} 必须是整数，实际为 {value!r}")


def load_config(path: Optional[str] = None) -> BatchConfig:
    yaml_path = Path(path) if path else ROOT / "config" / "batch_cases.yaml"
    if not yaml_path.is_file():
        raise FileNotFoundError(f"案例池配置不存在: {yaml_path}")
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(
            f"配置根节点必须是映射，实际为 {type(raw).__name__}: {yaml_path}")
    cfg = BatchConfig(
        max_review_rounds=_parse_int(raw.get("max_review_rounds", 3),
                                     "max_review_rounds"),
        framework=str(raw.get("framework") or "standard"),
        cases=[],
    )
    seen_ids = set()
    for i, item in enumerate(raw.get("cases") or []):
        if not isinstance(item, dict):
            raise ValueError(f"cases[{i}] 必须是映射，实际为 {type(item).__name__}")
        case_id = str(item.get("case_id", "")).strip()
        if not case_id:
            raise ValueError(f"cases[{i}] 缺少必填字段: case_id")
        if case_id in seen_ids:
            raise ValueError(f"cases[{i}] case_id 重复: {case_id}")
        seen_ids.add(case_id)
        if not str(item.get("topic", "")).strip():
            raise ValueError(f"cases[{i}] 缺少必填字段: topic")
        keywords = item.get("domain_keywords") or []
        if not isinstance(keywords, list):
            raise ValueError(f"cases[{i}] domain_keywords 必须是列表")
        chapters = item.get("chapters")
        if chapters is not None and not isinstance(chapters, list):
            raise ValueError(f"cases[{i}] chapters 必须是列表")
        cfg.cases.append(CaseConfig(
            case_id=case_id,
            topic=str(item["topic"]).strip(),
            domain_keywords=[str(k) for k in keywords],
            chapters=[str(c) for c in chapters] if chapters else None,
            max_total_searches=_parse_int(item.get("max_total_searches", 60),
                                          "max_total_searches", i),
        ))
    for c in cfg.cases:
        for kw in _TRADITIONAL_HINTS:
            if kw in c.topic:
                logger.warning(
                    "案例 %s 主题含传统行业关键词 %r，请确认是否应进入默认池",
                    c.case_id, kw)
    return cfg
