"""Deterministic claim ownership and cross-section duplication checks."""

import hashlib
import re
from typing import Any, Dict, List


class ReportIntegrityChecker:
    def check(self, report: Dict[str, Any]) -> Dict[str, Any]:
        claims: List[Dict[str, Any]] = []
        by_signature: Dict[str, Dict[str, Any]] = {}
        issues: List[Dict[str, Any]] = []
        for section in report.get("sections", []) or []:
            section_id = str(section.get("id", ""))
            subsection_id = str(section.get("sub_section_id", ""))
            for conclusion in section.get("key_conclusions", []) or []:
                text = str(conclusion or "").strip()
                if not text:
                    continue
                signature = self._normalize(text)
                claim_id = "claim_" + hashlib.sha256(signature.encode("utf-8")).hexdigest()[:16]
                claim = {
                    "claim_id": claim_id,
                    "section_id": section_id,
                    "sub_section_id": subsection_id,
                    "text": text,
                    "evidence_ids": sorted({
                        str(dp.get("evidence_id")) for dp in section.get("data_points", []) or []
                        if dp.get("evidence_id")
                    }),
                }
                previous = by_signature.get(signature)
                claim["primary_section_id"] = previous["primary_section_id"] if previous else section_id
                claims.append(claim)
                if previous and previous["section_id"] != section_id:
                    issues.append({
                        "layer": "L4",
                        "code": "duplicate_claim",
                        "chapter_id": section_id,
                        "section_id": section_id,
                        "sub_section_id": subsection_id,
                        "claim_id": claim_id,
                        "primary_section_id": previous["primary_section_id"],
                        "message": (
                            f"结论与章节 {previous['section_id']} 重复，主归属应明确，"
                            f"主归属章节为 {previous['primary_section_id']}，其他章节只能交叉引用。"
                        ),
                    })
                else:
                    by_signature[signature] = claim
        return {"passed": not issues, "claims": claims, "issues": issues}

    @staticmethod
    def _normalize(text: str) -> str:
        text = re.sub(r"[`*_#\s]+", "", text.lower())
        text = re.sub(r"[，。；：、,.!?！？()（）\[\]【】]", "", text)
        return text
