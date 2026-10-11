# -*- coding: utf-8 -*-
"""批量案例配置加载：config/batch_cases.yaml → BatchConfig/CaseConfig。"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml

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


def load_config(path: Optional[str] = None) -> BatchConfig:
    yaml_path = Path(path) if path else ROOT / "config" / "batch_cases.yaml"
    if not yaml_path.is_file():
        raise FileNotFoundError(f"案例池配置不存在: {yaml_path}")
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    cfg = BatchConfig(
        max_review_rounds=int(raw.get("max_review_rounds", 3)),
        framework=str(raw.get("framework", "standard")),
        cases=[],
    )
    for item in raw.get("cases", []):
        case_id = str(item.get("case_id", "")).strip()
        if not case_id:
            raise ValueError("案例缺少必填字段: case_id")
        if not str(item.get("topic", "")).strip():
            raise ValueError(f"案例 {case_id} 缺少必填字段: topic")
        cfg.cases.append(CaseConfig(
            case_id=case_id,
            topic=str(item["topic"]).strip(),
            domain_keywords=[str(k) for k in item.get("domain_keywords", [])],
            chapters=[str(c) for c in item["chapters"]] if item.get("chapters") else None,
            max_total_searches=int(item.get("max_total_searches", 60)),
        ))
    import logging
    for c in cfg.cases:
        for kw in _TRADITIONAL_HINTS:
            if kw in c.topic:
                logging.getLogger(__name__).warning(
                    "案例 %s 主题含传统行业关键词 %r，请确认是否应进入默认池", c.case_id, kw)
    return cfg
