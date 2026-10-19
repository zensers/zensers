# -*- coding: utf-8 -*-
"""I5 交付签名器合同测试（设计 §I5 验收标准）。

三级别各一个端到端合同测试，含"全部占位符 → dossier 而非空壳 docx"
用例（直接对应 10-17 空报告事故）。
"""
from src.core.delivery_signer import DeliverySigner


def _ready_section(sid, title="市场规模"):
    return {
        "section_id": sid, "title": title, "status": "ready",
        "content": "全球AI市场高速增长，核心产业规模持续扩大。" * 10,
        "data_points": [{"metric": "规模", "value": "1.2万亿", "source": "新华社"}],
    }


def _failed_section(sid, title="前沿方向"):
    return {
        "section_id": sid, "title": title, "status": "failed",
        "content": "生成失败，输出格式不规范",
        "data_points": [],
    }


_AUDIT_PASSED = {"passed": True, "score": 95.0, "layers": {}}
_QUALITY_OK = {"converged": True, "overall_score": 90.0}


class TestDeliverySignerFormal:
    def test_all_ready_no_blocking_signs_formal(self):
        verdict = DeliverySigner().sign(
            [_ready_section(f"s{i}") for i in range(7)],
            defense_audit=_AUDIT_PASSED,
            quality_check=_QUALITY_OK,
        )
        assert verdict["delivery_class"] == "formal"
        assert verdict["quality_gate"] == "passed"
        assert verdict["formal_complete"] is True
        assert verdict["banner"] == ""


class TestDeliverySignerDiagnostic:
    def test_partial_failure_signs_diagnostic_with_banner(self):
        sections = [_ready_section(f"s{i}") for i in range(5)] + [
            _failed_section("s5"), _failed_section("s6"),
        ]
        verdict = DeliverySigner().sign(
            sections, defense_audit=_AUDIT_PASSED, quality_check=_QUALITY_OK,
        )
        assert verdict["delivery_class"] == "diagnostic"
        assert verdict["formal_complete"] is False
        assert "2/7" in verdict["banner"]
        assert verdict["failed_section_ids"] == ["s5", "s6"]

    def test_l5_block_forces_blocked_gate(self):
        audit = {"passed": False, "score": 40.0, "layers": {"L5": True}}
        verdict = DeliverySigner().sign(
            [_ready_section(f"s{i}") for i in range(7)],
            defense_audit=audit, quality_check=_QUALITY_OK,
        )
        assert verdict["delivery_class"] == "diagnostic"
        assert verdict["quality_gate"] == "blocked"


class TestDeliverySignerDossier:
    def test_all_placeholders_sign_dossier_with_full_dossier_payload(self):
        """10-17 空报告事故合同：全部占位符 → dossier（资料包），非空壳。"""
        sections = [_failed_section(f"s{i}") for i in range(7)]
        result = {
            "topic": "人工智能行业",
            "title": "人工智能行业研究报告",
            "sections": sections,
            # 研究阶段照常收集到了数据与来源（一天的活儿有产出）
            "data_points": [
                {"metric": "全球AI市场规模", "value": "3759.3亿美元", "source": "Fortune BI"},
                {"metric": "中国AI核心产业规模", "value": "1.2万亿元", "source": "新华社"},
            ],
            "sources": [{"title": "Stanford HAI", "url": "https://hai.stanford.edu"}],
            "methodology_notes": ["全球与中国市场统计口径不同，不合并比较。"],
        }
        verdict = DeliverySigner().sign(
            sections, defense_audit=_AUDIT_PASSED, quality_check=_QUALITY_OK,
        )
        assert verdict["delivery_class"] == "dossier"
        assert verdict["formal_complete"] is False

        dossier = DeliverySigner.build_dossier(result)
        assert dossier["topic"] == "人工智能行业"
        assert len(dossier["data_points"]) == 2, "资料包必须携带已收集数据点"
        assert len(dossier["sources"]) == 1, "资料包必须携带来源清单"
        assert len(dossier["section_materials"]) == 7
        assert all(m["status"] == "failed" for m in dossier["section_materials"])
        assert dossier["methodology_notes"], "资料包必须携带口径说明"

    def test_empty_sections_sign_dossier(self):
        verdict = DeliverySigner().sign([], defense_audit=None, quality_check=None)
        assert verdict["delivery_class"] == "dossier"
        assert verdict["formal_complete"] is False
