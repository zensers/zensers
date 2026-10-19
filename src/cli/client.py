"""Unified HTTP API client for Zensers CLI."""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import httpx
from src.cli.utils import get_api_base_url


class ZensersError(Exception):
    """Base exception for Zensers CLI errors."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ZensersConnectionError(ZensersError):
    """Server unreachable."""
    pass


class ZensersNotFoundError(ZensersError):
    """Resource not found (404)."""
    pass


class ZensersServerError(ZensersError):
    """Server-side error (5xx)."""
    pass


class ZensersClient:
    """HTTP client wrapping all Zensers REST API endpoints."""

    def __init__(self, base_url: Optional[str] = None):
        self._base_url = (base_url or get_api_base_url()).rstrip("/")
        self._http = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        await self._http.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def _request(self, method: str, url: str, *, raise_on_404: bool = True, **kwargs) -> httpx.Response:
        try:
            r = await self._http.request(method, url, **kwargs)
        except httpx.ConnectError:
            raise ZensersConnectionError("Connection refused: server not running")
        except httpx.TimeoutException:
            raise ZensersConnectionError("Request timed out")
        if r.status_code == 404 and raise_on_404:
            raise ZensersNotFoundError(f"Resource not found: {url}", status_code=404)
        if r.status_code >= 500:
            raise ZensersServerError(f"Server error: HTTP {r.status_code}", status_code=r.status_code)
        r.raise_for_status()
        return r

    # ---- Research API ----

    async def research_start(
        self,
        user_input: str,
        user_id: Optional[str] = None,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        llm_api_key: Optional[str] = None,
        llm_api_endpoint: Optional[str] = None,
        llm_temperature: float = 0.7,
        llm_max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        data: Dict[str, str] = {"user_input": user_input}
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
        data["llm_temperature"] = str(llm_temperature)
        data["llm_max_tokens"] = str(llm_max_tokens)
        r = await self._request("POST", f"{self._base_url}/api/v1/research/start", data=data)
        return r.json()

    async def research_quick_start(
        self,
        user_input: str,
        template_id: str,
        user_id: Optional[str] = None,
        auto_confirm: bool = False,
        custom_params: Optional[Dict[str, Any]] = None,
        template_context: Optional[str] = None,
        llm_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        data: Dict[str, str] = {
            "user_input": user_input,
            "template_id": template_id,
            "auto_confirm": "true" if auto_confirm else "false",
        }
        if user_id:
            data["user_id"] = user_id
        if custom_params:
            data["parameters"] = json.dumps(custom_params, ensure_ascii=False)
        if template_context:
            data["template_context"] = template_context
        if llm_config:
            for k, v in llm_config.items():
                data[f"llm_{k}"] = v
        r = await self._request("POST", f"{self._base_url}/api/v1/research/quick-start", data=data)
        return r.json()

    async def research_pause(self, task_id: str) -> Dict[str, Any]:
        r = await self._request("POST", f"{self._base_url}/api/v1/research/{task_id}/pause")
        return r.json()

    async def research_resume(self, task_id: str) -> Dict[str, Any]:
        r = await self._request("POST", f"{self._base_url}/api/v1/research/{task_id}/resume")
        return r.json()

    async def research_cancel(self, task_id: str) -> Dict[str, Any]:
        r = await self._request("POST", f"{self._base_url}/api/v1/research/{task_id}/cancel")
        return r.json()

    async def research_status(self, task_id: str) -> Dict[str, Any]:
        r = await self._request("GET", f"{self._base_url}/api/v1/research/{task_id}/status")
        return r.json()

    async def research_detail(self, task_id: str) -> Dict[str, Any]:
        r = await self._request("GET", f"{self._base_url}/api/v1/research/{task_id}")
        return r.json()

    async def research_modify(self, task_id: str, aspects: List[str], topic: Optional[str] = None) -> Dict[str, Any]:
        data: Dict[str, str] = {"aspects": json.dumps(aspects, ensure_ascii=False)}
        if topic:
            data["topic"] = topic
        r = await self._request("POST", f"{self._base_url}/api/v1/research/{task_id}/modify", data=data)
        return r.json()

    async def research_revise(self, task_id: str, aspects: List[str], adjustment: Optional[str] = None) -> Dict[str, Any]:
        data: Dict[str, Any] = {"task_id": task_id, "aspects": json.dumps(aspects, ensure_ascii=False)}
        if adjustment:
            data["adjustment"] = adjustment
        r = await self._request("POST", f"{self._base_url}/api/v1/research/revise", data=data)
        return r.json()

    async def research_feedback(self, session_id: str, action: str, section: Optional[str] = None, adjustment: Optional[str] = None) -> Dict[str, Any]:
        data: Dict[str, str] = {"session_id": session_id, "action": action}
        if section:
            data["section"] = section
        if adjustment:
            data["adjustment"] = adjustment
        r = await self._request("POST", f"{self._base_url}/api/v1/research/feedback", data=data)
        return r.json()

    async def research_completed(self, limit: int = 50) -> Dict[str, Any]:
        r = await self._request("GET", f"{self._base_url}/api/v1/research/completed", params={"limit": limit})
        return r.json()

    async def research_sessions(self, limit: int = 20, offset: int = 0) -> Dict[str, Any]:
        r = await self._request("GET", f"{self._base_url}/api/v1/research/sessions", params={"limit": limit, "offset": offset})
        return r.json()

    async def download(self, task_id: str) -> Tuple[bytes, str]:
        """Download document. Returns (content_bytes, content_type)."""
        r = await self._request("GET", f"{self._base_url}/api/v1/download/{task_id}", raise_on_404=False)
        if r.status_code == 404:
            raise FileNotFoundError(f"Document not found for task {task_id}")
        content_type = r.headers.get("content-type", "application/octet-stream")
        return r.content, content_type

    # ---- MCP API ----
    # NOTE: MCP router has prefix="/mcp" (mcp_api.py),
    # mounted with prefix="/api/v1" in main.py.
    # Full paths are /api/v1/mcp/ + route path, e.g. /api/v1/mcp/servers

    async def mcp_list(self) -> Dict[str, Any]:
        r = await self._request("GET", f"{self._base_url}/api/v1/mcp/servers")
        return r.json()

    async def mcp_start(self, server_name: str) -> Dict[str, Any]:
        r = await self._request("POST", f"{self._base_url}/api/v1/mcp/servers/{server_name}/start")
        return r.json()

    async def mcp_stop(self, server_name: str) -> Dict[str, Any]:
        r = await self._request("POST", f"{self._base_url}/api/v1/mcp/servers/{server_name}/stop")
        return r.json()

    async def mcp_status(self, server_name: str) -> Dict[str, Any]:
        r = await self._request("GET", f"{self._base_url}/api/v1/mcp/servers/{server_name}/status")
        return r.json()

    async def mcp_health(self) -> Dict[str, Any]:
        r = await self._request("GET", f"{self._base_url}/api/v1/mcp/health")
        return r.json()

    async def mcp_reload(self) -> Dict[str, Any]:
        r = await self._request("POST", f"{self._base_url}/api/v1/mcp/reload")
        return r.json()

    # ---- LLM API ----

    async def llm_models(self) -> Dict[str, Any]:
        r = await self._request("GET", f"{self._base_url}/api/v1/llm/models")
        return r.json()

    async def llm_config(self) -> Dict[str, Any]:
        r = await self._request("GET", f"{self._base_url}/api/v1/llm/config")
        return r.json()

    async def llm_health(self) -> Dict[str, Any]:
        r = await self._request("GET", f"{self._base_url}/api/v1/llm/health")
        return r.json()

    # ---- Prompt API ----

    async def prompt_categories(self) -> List[str]:
        r = await self._request("GET", f"{self._base_url}/api/v1/prompts/categories")
        data = r.json()
        return data.get("categories", [])

    async def prompt_list(self, category: str) -> List[Dict[str, Any]]:
        r = await self._request("GET", f"{self._base_url}/api/v1/prompts/{category}")
        data = r.json()
        return data.get("prompts", [])

    async def prompt_get(self, category: str, name: str) -> Dict[str, Any]:
        r = await self._request("GET", f"{self._base_url}/api/v1/prompts/{category}/{name}")
        return r.json()

    async def prompt_render(self, category: str, name: str, variables: Dict[str, Any], strip_frontmatter: bool = True) -> Dict[str, Any]:
        payload = {
            "category": category,
            "name": name,
            "variables": variables,
            "strip_frontmatter": strip_frontmatter,
        }
        r = await self._request("POST", f"{self._base_url}/api/v1/prompts/render", json=payload)
        return r.json()

    # ---- Document API ----

    async def document_generate(self, task_id: str, output_format: str = "docx", template: str = "consulting") -> Dict[str, Any]:
        payload = {"task_id": task_id, "output_format": output_format, "template": template}
        r = await self._request("POST", f"{self._base_url}/api/v1/documents/generate", json=payload)
        return r.json()

    async def document_versions(self, task_id: str, format: str = "docx") -> Dict[str, Any]:
        r = await self._request("GET", f"{self._base_url}/api/v1/documents/{task_id}/versions", params={"format": format})
        return r.json()

    async def document_rollback(self, task_id: str, format: str, target_version: str) -> Dict[str, Any]:
        r = await self._request(
            "POST",
            f"{self._base_url}/api/v1/documents/{task_id}/rollback",
            params={"format": format, "target_version": target_version},
        )
        return r.json()

    async def document_preview(self, task_id: str, version_id: Optional[str] = None, format: str = "png") -> bytes:
        params: Dict[str, str] = {"format": format}
        if version_id:
            params["version_id"] = version_id
        r = await self._request("GET", f"{self._base_url}/api/v1/documents/{task_id}/preview", raise_on_404=False, params=params)
        return r.content

    async def document_adjust(self, task_id: str, adjustment_type: str, target: Optional[str] = None, changes: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"task_id": task_id, "adjustment_type": adjustment_type}
        if target:
            payload["target"] = target
        if changes:
            payload["changes"] = changes
        r = await self._request("POST", f"{self._base_url}/api/v1/documents/adjust", json=payload)
        return r.json()

    async def document_revisions(self, task_id: str) -> Dict[str, Any]:
        r = await self._request("GET", f"{self._base_url}/api/v1/documents/{task_id}/revisions")
        return r.json()

    async def document_export(self, task_id: str, version_id: str = "latest", output_format: str = "docx") -> Tuple[bytes, str]:
        payload = {"task_id": task_id, "version_id": version_id, "format": output_format}
        r = await self._request("POST", f"{self._base_url}/api/v1/documents/export", raise_on_404=False, json=payload)
        if r.status_code == 404:
            raise FileNotFoundError(f"Document not found for task {task_id}")
        content_type = r.headers.get("content-type", "application/octet-stream")
        return r.content, content_type

    async def document_revision(self, task_id: str, revision_type: str, user_feedback: str, section_id: Optional[str] = None, section_title: Optional[str] = None, keywords: Optional[List[str]] = None, target_content: Optional[str] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"task_id": task_id, "revision_type": revision_type, "user_feedback": user_feedback}
        if section_id:
            payload["section_id"] = section_id
        if section_title:
            payload["section_title"] = section_title
        if keywords:
            payload["keywords"] = keywords
        if target_content:
            payload["target_content"] = target_content
        r = await self._request("POST", f"{self._base_url}/api/v1/documents/revision", json=payload)
        return r.json()

    # ---- Upload API ----

    async def upload_file(self, file_path: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        files = {"files": (path.name, path.read_bytes())}
        data: Dict[str, str] = {}
        if session_id:
            data["session_id"] = session_id
        r = await self._request("POST", f"{self._base_url}/api/v1/upload", data=data, files=files)
        return r.json()

    async def delete_file(self, file_id: str) -> Dict[str, Any]:
        r = await self._request("DELETE", f"{self._base_url}/api/v1/upload/{file_id}")
        return r.json()

    # ---- Changelog ----

    async def changelog(self, format: str = "text", max_lines: int = 50) -> Dict[str, Any]:
        r = await self._request("GET", f"{self._base_url}/api/v1/changelog", params={"format": format, "max_lines": max_lines})
        return r.json()

    # ---- Version ----

    async def version_info(self) -> Dict[str, Any]:
        r = await self._request("GET", f"{self._base_url}/api/v1/version")
        return r.json()

    # ---- Additional Research API ----

    async def research_interact(self, session_id: str, user_message: str, step: int = 0, response: Optional[Dict] = None, llm_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data: Dict[str, Any] = {"session_id": session_id, "step": str(step)}
        if response:
            data["response"] = json.dumps(response, ensure_ascii=False)
        else:
            data["response"] = json.dumps({"user_message": user_message}, ensure_ascii=False)
        if llm_config:
            for k, v in llm_config.items():
                data[f"llm_{k}"] = v
        r = await self._request("POST", f"{self._base_url}/api/v1/research/interact", data=data)
        return r.json()

    async def research_messages(self, task_id: str, offset: int = 0, limit: int = 50) -> Dict[str, Any]:
        r = await self._request("GET", f"{self._base_url}/api/v1/research/{task_id}/messages", params={"offset": offset, "limit": limit})
        return r.json()

    async def research_quality_action(self, session_id: str, action: str, **kwargs) -> Dict[str, Any]:
        data: Dict[str, str] = {"session_id": session_id, "action": action}
        for k, v in kwargs.items():
            if v is not None:
                data[k] = str(v) if not isinstance(v, str) else v
        r = await self._request("POST", f"{self._base_url}/api/v1/research/quality/action", data=data)
        return r.json()

    async def research_quality(self, session_id: str) -> Dict[str, Any]:
        r = await self._request("GET", f"{self._base_url}/api/v1/research/quality/{session_id}")
        return r.json()

    async def research_preview(self, task_id: str) -> Dict[str, Any]:
        r = await self._request("GET", f"{self._base_url}/api/v1/research/preview/{task_id}")
        return r.json()

    async def research_sections(self, task_id: str) -> Dict[str, Any]:
        r = await self._request("GET", f"{self._base_url}/api/v1/research/sections/{task_id}")
        return r.json()

    # ---- Additional LLM API ----

    async def llm_set_config(self, provider: Optional[str] = None, model: Optional[str] = None, api_key: Optional[str] = None, api_endpoint: Optional[str] = None, temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if provider:
            payload["provider"] = provider
        if model:
            payload["model"] = model
        if api_key:
            payload["apiKey"] = api_key
        if api_endpoint:
            payload["apiEndpoint"] = api_endpoint
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["maxTokens"] = max_tokens
        r = await self._request("POST", f"{self._base_url}/api/v1/llm/config", json=payload)
        return r.json()

    async def llm_reset_config(self) -> Dict[str, Any]:
        r = await self._request("POST", f"{self._base_url}/api/v1/llm/config/reset")
        return r.json()
