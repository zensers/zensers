# -*- coding: utf-8 -*-
"""I5 交付签名器（Delivery Signature，2026-10-17 整改设计 §I5）。

交付物由确定性签名器定级，签名是最终事实。保住既有体验原则：
任何情况都有交付物——但分级，且垃圾内容永不进入任何级别的文档。

级别：
- formal     全部章节 ready 且无 blocking → 正式 docx + html
- diagnostic 部分章节 failed/污染或 blocking → html + 诊断版 docx（横幅）
             + 失败章节占位符
- dossier    全部章节失败 → 研究资料包：数据点、来源、框架、各章素材清单
             ——一天的活儿永远有产出（直接对应 10-17 空报告事故）。
"""
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

# 组装口已判失败的章节内容为占位符；状态字段是第一事实来源，
# 内容判空是第二道（防御历史 checkpoint 无状态字段的情况）。
_TRIVIAL_CONTENT_RE = re.compile(r"^[\s.。_\-—…·]*$")
# 章节内容低于该长度视为未产出实质内容（与 content_contract 各 kind
# 下限独立：此处判定的是"有无正文"，非质量下限）。
_MIN_SECTION_CHARS = 50


def _section_failed(section: Any) -> bool:
    if not isinstance(section, dict):
        return True
    status = str(section.get("status") or "").strip().lower()
    if status and status != "ready":
        return True
    content = str(section.get("content") or "").strip()
    if not content or _TRIVIAL_CONTENT_RE.match(content):
        return True
    if len(content) < _MIN_SECTION_CHARS:
        return True
    return False


class DeliverySigner:
    """确定性交付签名器：签名为最终事实，任何路径不得改写已签级别。"""

    def sign(
        self,
        sections: Optional[List[Dict[str, Any]]],
        defense_audit: Optional[Dict[str, Any]] = None,
        quality_check: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        sections = [s for s in (sections or []) if isinstance(s, dict)]
        total = len(sections)
        failed = [s for s in sections if _section_failed(s)]
        failed_count = len(failed)

        audit = defense_audit if isinstance(defense_audit, dict) else {}
        layers = audit.get("layers") or {}
        l5_block = bool(layers.get("L5"))
        blocking = l5_block or audit.get("blocking") is True

        quality = quality_check if isinstance(quality_check, dict) else {}
        quality_ok = (
            quality.get("converged") is True
            if "converged" in quality
            else True
        )
        audit_passed = audit.get("passed") is True

        reasons: List[str] = []
        if total == 0:
            delivery_class = "dossier"
            reasons.append("无章节产出，交付研究资料包")
        elif failed_count == total:
            delivery_class = "dossier"
            reasons.append(f"全部 {total} 个章节未通过验收，交付研究资料包")
        elif failed_count > 0:
            delivery_class = "diagnostic"
            reasons.append(
                f"{failed_count}/{total} 个章节未通过验收"
            )
        elif blocking:
            delivery_class = "diagnostic"
            reasons.append("存在 blocking 级质量问题")
        else:
            delivery_class = "formal"

        if l5_block:
            quality_gate = "blocked"
        elif delivery_class == "formal" and audit_passed and quality_ok:
            quality_gate = "passed"
        else:
            quality_gate = "degraded"

        formal_complete = delivery_class == "formal" and quality_gate == "passed"

        if failed_count and total:
            banner = (
                f"诊断版报告：{failed_count}/{total} 个章节未通过质量验收，"
                "其内容以占位符呈现；已收集的数据与来源见文末资料清单。"
            )
        elif delivery_class == "diagnostic":
            banner = "诊断版报告：存在 blocking 级质量问题，内容供诊断参考。"
        else:
            banner = ""

        return {
            "delivery_class": delivery_class,
            "quality_gate": quality_gate,
            "formal_complete": formal_complete,
            "reasons": reasons,
            "banner": banner,
            "failed_section_ids": [
                str(s.get("section_id") or s.get("id") or "") for s in failed
            ],
            "signed_at": datetime.now().isoformat(),
        }

    @staticmethod
    def legacy_delivery_class(delivery_class: str) -> str:
        """I5 词汇统一（复审 P1-D）：新分级 → 旧产品词汇的唯一映射。

        formal→formal_ready、diagnostic→available_with_warnings、
        dossier→missing。所有会话/存储边界的旧字段写点必须经此派生，
        禁止旁路直写（ses_baf7a884 实证：旁路写点让 degraded 压过
        blocked，两套词汇打架）。
        """
        return {
            "formal": "formal_ready",
            "diagnostic": "available_with_warnings",
            "dossier": "missing",
        }.get(str(delivery_class or "").strip(), "unknown")

    @staticmethod
    def build_dossier(research_result: Dict[str, Any]) -> Dict[str, Any]:
        """构建研究资料包（dossier）内容载荷。

        全部章节失败时，一天的活儿仍然有产出：数据点主干、来源清单、
        框架结构与各章素材状态——垃圾内容永不进入任何级别的文档。
        """
        sections = [
            s for s in (research_result.get("sections") or [])
            if isinstance(s, dict)
        ]
        return {
            "topic": research_result.get("topic") or "",
            "title": research_result.get("title") or research_result.get("topic") or "研究资料包",
            "framework": [
                {"title": str(s.get("title") or ""), "status": str(s.get("status") or "unknown")}
                for s in sections
            ],
            "data_points": research_result.get("data_points") or [],
            "sources": research_result.get("sources") or [],
            "methodology_notes": research_result.get("methodology_notes") or [],
            "section_materials": [
                {
                    "title": str(s.get("title") or ""),
                    "status": str(s.get("status") or "unknown"),
                    "chars": len(str(s.get("content") or "")),
                    "data_points": len(s.get("data_points") or []),
                }
                for s in sections
            ],
        }
