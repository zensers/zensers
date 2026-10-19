# -*- coding: utf-8 -*-
import asyncio
import time
import json
import logging
from typing import Any, Dict, List, Optional

from httpx import ASGITransport, AsyncClient

logger = logging.getLogger(__name__)


class ZensersClient:
    def __init__(self, app, base_url: str = "http://testserver"):
        transport = ASGITransport(app=app)
        self._client = AsyncClient(transport=transport, base_url=base_url, timeout=30.0)
        self._long_client = AsyncClient(transport=transport, base_url=base_url, timeout=700.0)

    async def aclose(self):
        await self._client.aclose()
        await self._long_client.aclose()

    async def start_research(
        self,
        user_input: str,
        user_id: Optional[str] = None,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        llm_api_key: Optional[str] = None,
        llm_api_endpoint: Optional[str] = None,
    ) -> Dict[str, Any]:
        data: Dict[str, Any] = {"user_input": user_input}
        if user_id:
            data["user_id"] = user_id
        if llm_provider:
            data["llm_provider"] = llm_provider
        if llm_model:
            data["llm_model"] = llm_model
        if llm_api_key:
            data["llm_api_key"] = llm_api_key
        if llm_api_endpoint:
            data["llm_api_endpoint"] = llm_api_endpoint
        resp = await self._long_client.post("/api/v1/research/start", data=data)
        return resp.json()

    async def quick_start(
        self,
        user_input: str,
        template_id: str,
        user_id: Optional[str] = None,
        auto_confirm: bool = True,
        region: Optional[str] = None,
        time_range: Optional[str] = None,
        depth: Optional[str] = None,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        llm_api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "user_input": user_input,
            "template_id": template_id,
            "auto_confirm": str(auto_confirm).lower(),
        }
        if user_id:
            data["user_id"] = user_id
        if region:
            data["region"] = region
        if time_range:
            data["time_range"] = time_range
        if depth:
            data["depth"] = depth
        if llm_provider:
            data["llm_provider"] = llm_provider
        if llm_model:
            data["llm_model"] = llm_model
        if llm_api_key:
            data["llm_api_key"] = llm_api_key
        resp = await self._long_client.post("/api/v1/research/quick-start", data=data)
        return resp.json()

    async def interact(
        self,
        session_id: str,
        step: int,
        response: Dict[str, Any],
        llm_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "session_id": session_id,
            "step": str(step),
            "response": json.dumps(response, ensure_ascii=False),
        }
        if llm_config:
            for k, v in llm_config.items():
                if v is not None:
                    data[f"llm_{k}"] = str(v)
        resp = await self._long_client.post("/api/v1/research/interact", data=data)
        return resp.json()

    async def pause_research(self, task_id: str) -> Dict[str, Any]:
        resp = await self._client.post(f"/api/v1/research/{task_id}/pause")
        return resp.json()

    async def resume_research(self, task_id: str) -> Dict[str, Any]:
        resp = await self._client.post(f"/api/v1/research/{task_id}/resume")
        return resp.json()

    async def cancel_research(self, task_id: str) -> Dict[str, Any]:
        resp = await self._client.post(f"/api/v1/research/{task_id}/cancel")
        return resp.json()

    async def get_status(self, task_id: str) -> Dict[str, Any]:
        resp = await self._client.get(f"/api/v1/research/{task_id}/status")
        return resp.json()

    async def get_preview(self, task_id: str, format: str = "html") -> Dict[str, Any]:
        resp = await self._client.get(f"/api/v1/research/preview/{task_id}", params={"format": format})
        return resp.json()

    async def get_sections(self, task_id: str) -> Dict[str, Any]:
        resp = await self._client.get(f"/api/v1/research/sections/{task_id}")
        return resp.json()

    async def quality_action(
        self,
        session_id: str,
        action: str,
        data: Optional[Dict[str, Any]] = None,
        issue_id: Optional[str] = None,
        version_id: Optional[str] = None,
        section_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"session_id": session_id, "action": action}
        if data:
            payload["data"] = data
        if issue_id:
            payload["issue_id"] = issue_id
        if version_id:
            payload["version_id"] = version_id
        if section_name:
            payload["section_name"] = section_name
        resp = await self._long_client.post("/api/v1/research/quality/action", json=payload)
        return resp.json()

    async def quality_state(self, session_id: str) -> Dict[str, Any]:
        resp = await self._client.get(f"/api/v1/research/quality/{session_id}")
        return resp.json()

    async def feedback(
        self,
        session_id: str,
        action: str,
        section: Optional[str] = None,
        adjustment: Optional[str] = None,
    ) -> Dict[str, Any]:
        data: Dict[str, Any] = {"session_id": session_id, "action": action}
        if section:
            data["section"] = section
        if adjustment:
            data["adjustment"] = adjustment
        resp = await self._client.post("/api/v1/research/feedback", data=data)
        return resp.json()

    async def revise_sections(
        self,
        task_id: str,
        aspects: Optional[List[str]] = None,
        adjustment: Optional[str] = None,
    ) -> Dict[str, Any]:
        data: Dict[str, Any] = {"task_id": task_id}
        if aspects:
            data["aspects"] = json.dumps(aspects, ensure_ascii=False)
        if adjustment:
            data["adjustment"] = adjustment
        resp = await self._long_client.post("/api/v1/research/revise", data=data)
        return resp.json()

    async def download(self, task_id: str):
        resp = await self._long_client.get(f"/api/v1/download/{task_id}")
        return resp

    async def get_research_detail(self, task_id: str) -> Dict[str, Any]:
        resp = await self._client.get(f"/api/v1/research/{task_id}")
        return resp.json()

    async def wait_for_completion(
        self,
        task_id: str,
        timeout: float = 600,
        poll_interval: float = 5,
    ) -> Dict[str, Any]:
        started = time.monotonic()
        elapsed = 0.0
        deadline = started + timeout
        while (remaining := deadline - time.monotonic()) > 0:
            try:
                status = await asyncio.wait_for(self.get_status(task_id), timeout=remaining)
            except asyncio.TimeoutError:
                break
            cur = status.get("status", "unknown")
            if cur in ("completed", "completed_with_warnings"):
                return status
            if cur in ("failed", "error", "cancelled"):
                return status
            await asyncio.sleep(min(poll_interval, max(0.0, deadline - time.monotonic())))
            elapsed = time.monotonic() - started
        return {"status": "timeout", "task_id": task_id, "elapsed": elapsed}

    async def wait_for_research_result(
        self,
        task_id: str,
        timeout: float = 1800,
        poll_interval: float = 30,
    ) -> Dict[str, Any]:
        from src.core.session_manager import SessionManager
        started = time.monotonic()
        elapsed = 0.0
        deadline = started + timeout
        last_progress = -1.0
        stall_count = 0
        while (remaining := deadline - time.monotonic()) > 0:
            try:
                status = await asyncio.wait_for(self.get_status(task_id), timeout=remaining)
            except asyncio.TimeoutError:
                break
            except Exception:
                await asyncio.sleep(min(poll_interval, max(0.0, deadline - time.monotonic())))
                elapsed = time.monotonic() - started
                continue
            cur = status.get("status", "unknown")
            prog = status.get("progress", 0)
            if cur in ("completed", "completed_with_warnings"):
                return await self.get_research_detail(task_id)
            if cur in ("failed", "error", "cancelled"):
                return await self.get_research_detail(task_id)
            if prog == last_progress:
                stall_count += 1
            else:
                stall_count = 0
                last_progress = prog
            if stall_count >= 10:
                sm = SessionManager.get_instance()
                session = sm.get(task_id)
                if session:
                    rr = session.get("research_result", {})
                    if rr.get("status") in ("completed", "completed_with_warnings"):
                        return await self.get_research_detail(task_id)
                    if rr.get("report", {}).get("sections"):
                        rr["status"] = rr.get("status") or "completed_with_warnings"
                        session["research_result"] = rr
                        return await self.get_research_detail(task_id)
            if cur == "paused" and stall_count >= 3:
                sm = SessionManager.get_instance()
                session = sm.get(task_id)
                if session:
                    rr = session.get("research_result", {})
                    if rr.get("status") in ("completed", "completed_with_warnings"):
                        return await self.get_research_detail(task_id)
                    session_status = session.get("status", "")
                    if session_status in ("completed", "completed_with_warnings"):
                        return await self.get_research_detail(task_id)
            await asyncio.sleep(min(poll_interval, max(0.0, deadline - time.monotonic())))
            elapsed = time.monotonic() - started
        sm = SessionManager.get_instance()
        session = sm.get(task_id)
        if session:
            rr = session.get("research_result", {})
            if rr.get("status") in ("completed", "completed_with_warnings") or rr.get("report", {}).get("sections"):
                return await self.get_research_detail(task_id)
        return {"status": "timeout", "task_id": task_id, "elapsed": elapsed}
