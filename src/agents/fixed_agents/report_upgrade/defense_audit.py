"""Deterministic L1-L5 audit for the final report representation.

The cognitive layers upstream are useful guidance, but a final report needs a
non-LLM gate.  This module deliberately checks only facts that can be proved
from the report payload: evidence ownership, scope, provenance, epistemic
labels and conflicts.  It never invents a source or silently repairs a claim.
"""

import re
from datetime import datetime
from typing import Any, Dict, List


_VAGUE = re.compile(r"^(行业综合数据|综合数据|公开数据|市场数据|统计数据|研究报告|行业报告|公开信息|行业信息|行业动态报告)$", re.I)
_NUM = re.compile(r"(?P<value>-?\d+(?:\.\d+)?)")
_QUANTIFIED_NUMBER = re.compile(
    r"(?P<value>-?\d+(?:\.\d+)?)\s*"
    r"(?P<unit>%|％|百分比|亿元|亿美元|万元|万亿美元|万辆|万台|吨|万人|万人次|人|家|个|件|台)"
)
_SCOPE_DISCLAIMER = re.compile(
    r"不同口径|不直接比较|不可直接合并|分别估算|仅作参考|统计范围不同|非同一指标|口径不同"
)
_SCOPE_COMPARISON = re.compile(
    r"相比|相较|对比|比较|其中|而中国|中国.*高于|中国.*低于|全球.*高于|全球.*低于"
)


def _norm_value(value: Any) -> str:
    text = str(value or "").strip().replace(",", "")
    text = text.replace("下滑", "-").replace("下降", "-")
    text = re.sub(r"^(接近|约|超过|达到|约为)", "", text)
    m = _NUM.search(text)
    return m.group("value") if m else text


def _is_quantitative_dp(dp: Dict[str, Any]) -> bool:
    """P0-B：定量数据点判定——值含数字，或单位为计量单位（非"—"/定性）。"""
    value = str(dp.get("value") or "")
    if _NUM.search(value):
        return True
    unit = str(dp.get("unit") or "").strip()
    return bool(unit) and unit not in {"—", "-", "定性", "无", "n/a", "N/A"}


class ReportDefenseAudit:
    """Run blocking checks corresponding to the L1-L5 evidence contract."""

    def audit(self, report: Dict[str, Any], registry_conflicts: str = "") -> Dict[str, Any]:
        issues: List[Dict[str, Any]] = []
        sections = report.get("sections", []) if isinstance(report, dict) else []

        # L1: every structured claim belongs to a chapter and has a level.
        for section in sections:
            chapter_id = str(section.get("id", ""))
            content = str(section.get("content", "") or "")
            for dp in section.get("data_points", []) or []:
                if not dp.get("chapter_id") or dp.get("chapter_id") != chapter_id:
                    issues.append(self._issue("L1", "missing_chapter_binding", chapter_id, dp))
                if dp.get("epistemic_level") not in {"factual", "inferential", "speculative"}:
                    issues.append(self._issue("L1", "invalid_epistemic_level", chapter_id, dp))

                # L2: a metric must carry a scope and period when the claim is
                # quantitative.  Missing metadata is unsafe, not a reason to
                # guess a default.
                # P0-B（复审修订，ses_baf7a884）：注释声明的本意是"仅定量
                # 断言"，但实现无条件检查所有数据点——定性条目（值无数值，
                # 如"大模型技术路线：AGI探索与应用落地并行"）被迫满足地理/
                # 期间元数据，制造了本会话 249 条 L2 噪声。按数据点性质
                # 分流：定量断言缺口径仍 blocking（证据合同不放松），定性
                # 条目缺失元数据不构成证据风险。
                if _is_quantitative_dp(dp):
                    if not dp.get("geographic_scope"):
                        issues.append(self._issue("L2", "missing_geographic_scope", chapter_id, dp))
                    if not dp.get("period"):
                        issues.append(self._issue("L2", "missing_period", chapter_id, dp))
                    if not dp.get("population"):
                        issues.append(self._issue("L2", "missing_population", chapter_id, dp))

                # L3: source and URL must be directly attached to the point.
                if not dp.get("source") or _VAGUE.match(str(dp.get("source", "")).strip()):
                    issues.append(self._issue("L3", "missing_source", chapter_id, dp))
                if not dp.get("source_url"):
                    issues.append(self._issue("L3", "missing_source_url", chapter_id, dp))
                if dp.get("evidence_status") != "verified":
                    issues.append(self._issue("L3", "unverified_evidence", chapter_id, dp))
                elif not dp.get("evidence_id") or not dp.get("provenance_id"):
                    issues.append(self._issue("L3", "incomplete_evidence_identity", chapter_id, dp))

            # Every quantified assertion in prose must be represented by at
            # least one structured data point.  Years and unquantified IDs are
            # intentionally excluded; this catches claims such as
            # “市场规模达到100亿元” without rejecting ordinary headings.
            structured_values = {
                (_norm_value(dp.get("value")), str(dp.get("unit", "")).strip())
                for dp in section.get("data_points", []) or []
            }
            for match in _QUANTIFIED_NUMBER.finditer(content):
                value = _norm_value(match.group("value"))
                unit = match.group("unit")
                if not any(
                    value == point_value and (
                        unit == point_unit or unit in point_unit or point_unit in unit
                    )
                    for point_value, point_unit in structured_values
                ):
                    issues.append({
                        "layer": "L3",
                        "code": "unbound_numeric_claim",
                        "chapter_id": chapter_id,
                        "message": f"正文定量断言 {match.group(0)} 未绑定结构化数据点。",
                    })

            # L4: reject a known scope collision in one analytical paragraph.
            # This is intentionally conservative and catches the observed
            # global-number-used-for-domestic-conclusion failure.
            for paragraph in re.split(r"\n\s*\n", content):
                if (re.search(r"全球|世界", paragraph) and
                        re.search(r"国内|中国", paragraph) and
                        re.search(r"销量|市场|增速|增长|渗透率", paragraph)
                        and not _SCOPE_DISCLAIMER.search(paragraph)
                        and not _SCOPE_COMPARISON.search(paragraph)):
                    issues.append({
                        "layer": "L4", "code": "scope_collision",
                        "chapter_id": chapter_id,
                        "message": "同一分析段同时混用全球/世界与国内/中国口径，需拆分或明确比较关系。",
                    })

            # L4: future-year numbers must be explicitly marked as forecasts.
            for year in re.findall(r"20\d{2}", content):
                if int(year) > datetime.now().year:
                    window = content[max(0, content.find(year) - 35):content.find(year) + 70]
                    if not re.search(r"预测|预计|目标|规划|展望", window):
                        issues.append({
                            "layer": "L4", "code": "unlabeled_future_value",
                            "chapter_id": chapter_id,
                            "message": f"未来年份 {year} 未明确标注预测/目标属性。",
                        })

        # L5: conflict input must not be silently ignored.
        if registry_conflicts and registry_conflicts != "无已知数据冲突。":
            issues.append({
                "layer": "L5", "code": "unresolved_registry_conflict",
                "chapter_id": "", "message": "数据注册器存在未解决冲突，禁止将报告标记为正式完成。",
            })

        blocking = [
            self._normalize_issue(i)
            for i in issues
            if i.get("layer") in {"L1", "L2", "L3", "L4", "L5"}
        ]
        score = max(0.0, 100.0 - min(100.0, len(blocking) * 5.0))
        return {
            "passed": not blocking,
            "score": round(score, 1),
            "issues": blocking,
            "layers": {f"L{i}": any(x.get("layer") == f"L{i}" for x in blocking) for i in range(1, 6)},
            # These are presentation-level statuses, not delivery blockers.
            # A warning report may still be rendered, but it must not be
            # mistaken for a formally complete report.
            "formal_status": "passed" if not blocking else "failed",
            "diagnostic_status": "clean" if not issues else "warning",
        }

    @staticmethod
    def _issue(layer: str, code: str, chapter_id: str, dp: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "layer": layer,
            "code": code,
            "chapter_id": chapter_id,
            "section_id": chapter_id,
            "sub_section_id": dp.get("sub_section_id", ""),
            "metric": dp.get("metric", ""),
            "message": f"{layer}: 数据点 {dp.get('metric', '')} 未满足 {code}。",
        }

    @staticmethod
    def _normalize_issue(issue: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(issue)
        normalized.setdefault("section_id", normalized.get("chapter_id", ""))
        normalized.setdefault("sub_section_id", "")
        normalized.setdefault("metric", "")
        normalized.setdefault("required_action", "review_by_report_agent")
        return normalized
