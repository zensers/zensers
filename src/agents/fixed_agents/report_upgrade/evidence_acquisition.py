"""Evidence acquisition owned by the report workflow, not a repair Agent."""

import json
import re
from typing import Any, Dict, List

from .models import DataGap, DataRepairResult
from .prompt_manager import PromptManager
from src.core.llm_client import call_llm
from src.core.search import SearchRequest


class ReportEvidenceAcquirer:
    def __init__(self, search_gateway=None, prompt_manager: PromptManager = None):
        self._gateway = search_gateway
        self._prompts = prompt_manager or PromptManager()

    async def acquire(self, gap: DataGap, topic: str, scope: str = "report_generation") -> DataRepairResult:
        if self._gateway is None:
            return DataRepairResult(gap=gap, found=False)
        query = f"{topic} {gap.metric} {' '.join(gap.search_keywords[:3])}".strip()
        try:
            response = await self._gateway.search(
                SearchRequest(
                    query=query,
                    objective=scope,
                    max_results=8,
                ),
                scope=scope,
            )
        except Exception:
            return DataRepairResult(gap=gap, found=False)
        if not response.success or not response.results:
            return DataRepairResult(gap=gap, found=False)
        evidence = [
            {
                "title": item.title,
                "url": item.url,
                "snippet": item.snippet,
                "evidence_excerpt": item.excerpt or item.snippet,
                "source": item.source,
                "evidence_id": item.evidence_id,
                "provenance_id": item.provenance_id,
                "locator": item.locator,
                "task_id": item.task_id,
                "request_id": item.request_id,
                "retrieved_at": item.retrieved_at,
            }
            for item in response.results
        ]
        prompt = self._prompts.get(
            "data_extraction",
            metric=gap.metric,
            context=gap.context,
            topic=topic,
            search_results="\n\n".join(
                f"[{item['title']}]({item['url']}): {item['evidence_excerpt']}"
                for item in evidence
            ),
        )
        try:
            result = await call_llm(prompt=prompt, max_tokens=2048)
        except Exception:
            return DataRepairResult(gap=gap, found=False)
        if not result.get("success"):
            return DataRepairResult(gap=gap, found=False)
        return self._parse(result.get("content", ""), gap, evidence)

    @staticmethod
    def _parse(raw: str, gap: DataGap, evidence: List[Dict[str, Any]]) -> DataRepairResult:
        try:
            match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
            data = json.loads(match.group()) if match else {}
        except (json.JSONDecodeError, TypeError):
            data = {}
        if not data.get("found"):
            return DataRepairResult(gap=gap, found=False)
        title = str(data.get("source_title") or "").strip()
        url = str(data.get("source_url") or "").strip()
        selected = next(
            (
                item for item in evidence
                if (url and item["url"] == url)
                or (not url and title and item["title"] == title)
            ),
            None,
        )
        # The LLM may only select from the search candidates. Never allow an
        # untrusted URL to become self-authorized evidence or inherit the
        # identity of an unrelated candidate.
        if url and selected is None:
            return DataRepairResult(gap=gap, found=False)
        selected = selected or (evidence[0] if len(evidence) == 1 else {})
        if not selected:
            return DataRepairResult(gap=gap, found=False)
        return DataRepairResult(
            gap=gap, found=True, value=data.get("value"), unit=data.get("unit"),
            source=data.get("source") or selected.get("source"), source_title=title or selected.get("title"),
            confidence=float(data.get("confidence") or 0), source_url=url or selected.get("url", ""),
            evidence_id=selected.get("evidence_id", ""), provenance_id=selected.get("provenance_id", ""),
            evidence_excerpt=selected.get("evidence_excerpt", ""), locator=selected.get("locator", ""),
            task_id=selected.get("task_id", ""), request_id=selected.get("request_id", ""),
            retrieved_at=selected.get("retrieved_at"), geographic_scope=str(data.get("geographic_scope") or ""),
            period=str(data.get("period") or ""), population=str(data.get("population") or ""),
            epistemic_level=str(data.get("epistemic_level") or ""),
        )
