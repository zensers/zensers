# -*- coding: utf-8 -*-
import pytest

from tools.batch_case_pipeline.config import BatchConfig, CaseConfig, load_config

TRADITIONAL = ["钢铁", "煤炭", "纺织", "建材", "水泥", "化工"]


def test_load_default_pool(tmp_path):
    cfg = load_config(None)  # None → 默认 config/batch_cases.yaml
    assert isinstance(cfg, BatchConfig)
    assert cfg.max_review_rounds == 3
    assert len(cfg.cases) >= 12
    ids = [c.case_id for c in cfg.cases]
    assert "humanoid_robot" in ids and len(ids) == len(set(ids))


def test_case_fields_valid(tmp_path):
    cfg = load_config(None)
    for c in cfg.cases:
        assert c.case_id and c.topic
        assert len(c.domain_keywords) >= 4, c.case_id
        for kw in TRADITIONAL:
            assert kw not in c.topic, f"默认池不得含传统行业: {c.case_id}"


def test_load_custom_yaml(tmp_path):
    p = tmp_path / "cases.yaml"
    p.write_text(
        "max_review_rounds: 2\n"
        "cases:\n"
        "  - case_id: test_case\n"
        "    topic: 中国脑机接口产业深度研究报告\n"
        "    domain_keywords: [脑机接口, 神经信号, 电极, BCI]\n",
        encoding="utf-8")
    cfg = load_config(str(p))
    assert cfg.max_review_rounds == 2
    assert cfg.cases[0].chapters is None  # 未配置则用默认章节


def test_missing_required_field(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("cases:\n  - topic: 无ID的报告\n", encoding="utf-8")
    with pytest.raises(ValueError, match="case_id"):
        load_config(str(p))


def test_chapters_override(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(
        "cases:\n"
        "  - case_id: x\n"
        "    topic: 中国量子计算产业深度研究报告\n"
        "    domain_keywords: [量子比特, 量子门, 退相干, 超导]\n"
        "    chapters: [章一, 章二]\n", encoding="utf-8")
    cfg = load_config(str(p))
    assert cfg.cases[0].chapters == ["章一", "章二"]
