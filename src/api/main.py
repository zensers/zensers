# -*- coding: utf-8 -*-
"""FastAPI Main Application - Zensers API."""
import asyncio
import sys
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
import json
import logging, os, uuid
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from src.core.preview_storage import PreviewStorage
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", force=True)
from logging.handlers import RotatingFileHandler
_log_file = Path(__file__).parent.parent.parent / "logs" / "app.log"
_log_file.parent.mkdir(parents=True, exist_ok=True)
_handler = RotatingFileHandler(str(_log_file), maxBytes=50*1024*1024, backupCount=5, encoding="utf-8", delay=True)
_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
logging.getLogger().addHandler(_handler)

logger = logging.getLogger(__name__)

from src.core.version import get_version_info, get_local_version
from src.core.session_manager import SessionManager
_session_manager = SessionManager.get_instance()
_recovered = _session_manager.recover_all()
logger.info(f"Zensers API starting... (recovered {_recovered} sessions)")

# Attach history compressor to global SessionManager
try:
    from src.core.compress_adapter import SessionHistoryCompressor
    _history_compressor = SessionHistoryCompressor()
    _session_manager.set_history_compressor(_history_compressor)
    logger.info("History compressor attached to SessionManager")
except Exception as e:
    logger.warning(f"History compressor not available: {e}")

def _parse_heartbeat(last_hb: str) -> datetime:
    """安全解析心跳时间戳，统一返回 naive datetime 用于比较。

    支持三种格式：
    - "2024-01-01T12:00:00Z"        → UTC
    - "2024-01-01T12:00:00+08:00"   → 带时区偏移
    - "2024-01-01T12:00:00"         → 无时区，假设 UTC
    """
    hb_time = datetime.fromisoformat(last_hb)
    if hb_time.tzinfo is not None:
        from datetime import timezone
        hb_time = hb_time.astimezone(timezone.utc).replace(tzinfo=None)
    return hb_time

# Recover ProgressStreamer states from persisted session data
from src.core.progress_streamer import ProgressStreamer
_recovered_tasks = 0
for _sid, _session in list(_session_manager._sessions.items()):
    _task_state = ProgressStreamer._restore_from_session(_sid)
    if _task_state:
        _tp = _session.get("task_progress", {})
        _last_hb = _tp.get("last_heartbeat_at")
        _is_stale = True
        if _last_hb and _task_state.status == "running":
            try:
                _hb_time = _parse_heartbeat(_last_hb)
                _is_stale = (datetime.now() - _hb_time).total_seconds() > 300
            except (ValueError, TypeError):
                pass
        if _is_stale and _task_state.status == "running":
            _task_state.status = "paused"
            try:
                _session["interrupted"] = True
                _session["interrupted_reason"] = "Server restarted - background execution lost"
            except Exception:
                pass
        ProgressStreamer._task_states[_sid] = _task_state
        ProgressStreamer._subscribers[_sid] = set()
        _recovered_tasks += 1

logger.info(f"ProgressStreamer recovered {_recovered_tasks} task states from disk")

app = FastAPI(title="Zensers API", description="AI Market Research Platform RESTful API",
              version="1.0.2", openapi_url="/api/v1/openapi.json",
              docs_url="/api/v1/docs", redoc_url="/api/v1/redoc")

_cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000,http://127.0.0.1:3001").split(",")
app.add_middleware(CORSMiddleware,
                   allow_origins=_cors_origins,
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

PreviewStorage.ensure_dirs()
app.mount("/api/v1/html-reports", StaticFiles(directory=str(PreviewStorage.NEW_DIR)), name="previews")

# Download endpoint: serves generated documents as file downloads
from fastapi.responses import FileResponse as _FastAPIFileResponse
@app.get("/api/v1/download/{task_id}")
async def download_document(task_id: str):
    logger.info(f"[DOWNLOAD] ========== Download request for task_id={task_id} ==========")
    
    # Look in data/reports/{task_id}/ for generated reports
    task_dir = Path("data/reports") / task_id
    logger.info(f"[DOWNLOAD] Checking primary location: {task_dir}")
    logger.info(f"[DOWNLOAD] Directory exists: {task_dir.is_dir()}")
    
    if task_dir.is_dir():
        docs = sorted(task_dir.glob("*.docx"))
        logger.info(f"[DOWNLOAD] Found {len(docs)} DOCX files in primary location")
        if docs:
            file_path = docs[-1]
            file_size = file_path.stat().st_size if file_path.exists() else 0
            logger.info(f"[DOWNLOAD] Serving DOCX: {file_path.name}, size={file_size} bytes")
            logger.info(f"[DOWNLOAD] ========== Download SUCCESS (DOCX from primary) ==========")
            return _FastAPIFileResponse(
                str(file_path),
                filename=file_path.name,
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

    # Fallback: look in data/{task_id}/ (legacy location for backward compatibility)
    legacy_dir = Path("data") / task_id
    logger.info(f"[DOWNLOAD] Checking legacy location: {legacy_dir}")
    logger.info(f"[DOWNLOAD] Legacy directory exists: {legacy_dir.is_dir()}")
    
    if legacy_dir.is_dir() and legacy_dir != task_dir:
        docs = sorted(legacy_dir.glob("*.docx"))
        logger.info(f"[DOWNLOAD] Found {len(docs)} DOCX files in legacy location")
        if docs:
            file_path = docs[-1]
            file_size = file_path.stat().st_size if file_path.exists() else 0
            logger.info(f"[DOWNLOAD] Serving DOCX from legacy: {file_path.name}, size={file_size} bytes")
            logger.info(f"[DOWNLOAD] ========== Download SUCCESS (DOCX from legacy) ==========")
            return _FastAPIFileResponse(
                str(file_path),
                filename=file_path.name,
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

    # Fallback to HTML preview
    preview_path = Path("data/previews") / f"{task_id}.html"
    logger.info(f"[DOWNLOAD] Checking HTML preview: {preview_path}")
    logger.info(f"[DOWNLOAD] Preview exists: {preview_path.is_file()}")
    
    if preview_path.is_file():
        file_size = preview_path.stat().st_size
        logger.info(f"[DOWNLOAD] Serving HTML preview, size={file_size} bytes")
        logger.info(f"[DOWNLOAD] ========== Download SUCCESS (HTML preview) ==========")
        return _FastAPIFileResponse(
            str(preview_path),
            filename=f"{task_id}.html",
            media_type="text/html",
        )

    logger.error(f"[DOWNLOAD] ========== Download FAILED ==========")
    logger.error(f"[DOWNLOAD] No document found for task_id={task_id}")
    logger.error(f"[DOWNLOAD] Searched locations:")
    logger.error(f"[DOWNLOAD]   - Primary: {task_dir} (exists: {task_dir.is_dir()})")
    logger.error(f"[DOWNLOAD]   - Legacy: {legacy_dir} (exists: {legacy_dir.is_dir()})")
    logger.error(f"[DOWNLOAD]   - Preview: {preview_path} (exists: {preview_path.is_file()})")
    
    raise HTTPException(status_code=404, detail="Document not found")

_upload_dir = Path("data/uploads")
_upload_dir.mkdir(parents=True, exist_ok=True)

# ============ Container & Memory ============
from src.core.container import configure_container, get_container
from src.core.memory import KnowledgeManager

_container = configure_container()
_knowledge_manager: Optional[KnowledgeManager] = None
try:
    if get_container().has(KnowledgeManager):
        _knowledge_manager = get_container().resolve(KnowledgeManager)
        logger.info("KnowledgeManager initialized and registered")
except Exception as e:
    logger.warning(f"KnowledgeManager initialization skipped: {e}")

# ============ Research API ============
from src.api.research_api import ResearchAPI
from src.core.orchestrator.orchestrator import ResearchOrchestrator
_research_orchestrator = ResearchOrchestrator(
    use_intelligent_routing=True,
    knowledge_manager=_knowledge_manager,
)
research_api = ResearchAPI(
    orchestrator=_research_orchestrator,
    knowledge_manager=_knowledge_manager,
)


@app.post("/api/v1/research/start")
async def start_research(user_input: str = Form(...), user_id: Optional[str] = Form(None),
                         llm_provider: Optional[str] = Form(None), llm_model: Optional[str] = Form(None),
                         llm_api_key: Optional[str] = Form(None), llm_api_endpoint: Optional[str] = Form(None),
                         llm_temperature: Optional[float] = Form(None), llm_max_tokens: Optional[int] = Form(None),
                         llm_top_p: Optional[float] = Form(None),
                         llm_frequency_penalty: Optional[float] = Form(None),
                         llm_presence_penalty: Optional[float] = Form(None)):
    from src.config.settings import settings
    llm_config: Dict[str, Any] = {}
    if llm_provider:
        llm_config["provider"] = llm_provider
    if llm_model:
        llm_config["model"] = llm_model
    if llm_api_key:
        llm_config["api_key"] = llm_api_key
    if llm_api_endpoint:
        llm_config["api_endpoint"] = llm_api_endpoint
    if llm_temperature is not None:
        llm_config["temperature"] = llm_temperature
    if llm_max_tokens is not None:
        llm_config["max_tokens"] = llm_max_tokens
    if llm_top_p is not None:
        llm_config["top_p"] = llm_top_p
    if llm_frequency_penalty is not None:
        llm_config["frequency_penalty"] = llm_frequency_penalty
    if llm_presence_penalty is not None:
        llm_config["presence_penalty"] = llm_presence_penalty

    settings.update_from_request(llm_config)
    return await research_api.start_research(user_input, user_id, llm_config)


@app.post("/api/v1/research/{task_id}/pause")
async def pause_research(task_id: str):
    return await research_api.pause_research(task_id)


@app.post("/api/v1/research/{task_id}/resume")
async def resume_research(task_id: str):
    return await research_api.resume_research(task_id)


@app.post("/api/v1/research/{task_id}/cancel")
async def cancel_research(task_id: str):
    return await research_api.cancel_research(task_id)


@app.post("/api/v1/research/{task_id}/modify")
async def modify_requirements(task_id: str, aspects: str = Form(...),
                               topic: Optional[str] = Form(None)):
    import json
    try:
        aspects_list = json.loads(aspects)
        if not isinstance(aspects_list, list):
            raise ValueError("aspects must be a list")
    except (json.JSONDecodeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid aspects JSON: {e}")
    return await research_api.modify_requirements(task_id, aspects_list, topic)


@app.get("/api/v1/research/{task_id}/status")
async def get_research_status(task_id: str):
    """研究任务状态查询（扩展版）

    用于 SSE 断开后的轮询回退，以及心跳过期检测。
    返回阶段状态 + agent 消息 + 中断标记。
    """
    try:
        from src.core.progress_streamer import ProgressStreamer

        state = ProgressStreamer.get_task_state(task_id)

        if state is None:
            try:
                from src.core.task_persistence import TaskPersistenceManager
                tp = TaskPersistenceManager()
                task = tp.load_task(task_id)
                if task and task.status:
                    return {"task_id": task_id, "status": task.status.state.value,
                            "progress": task.status.progress, "message": task.status.message,
                            "created_at": task.status.created_at, "updated_at": task.status.updated_at}
            except Exception:
                pass
            state = ProgressStreamer.get_or_create_task(task_id)

        response = {
            "task_id": task_id,
            "status": state.status if state.status != "running" else "running",
            "progress": state.progress,
            "current_phase": state.current_phase,
            "error": state.error,
            "phases": [
                {"id": p.id, "name": p.name, "status": p.status, "progress": p.progress}
                for p in (state.phases or [])
            ],
        }

        # Heartbeat staleness check + agent messages from SessionManager
        sm = SessionManager.get_instance()
        session = sm.get(task_id)
        if session:
            tp_data = session.get("task_progress", {})
            if tp_data.get("status") == "running":
                last_hb = tp_data.get("last_heartbeat_at")
                is_stale = True
                if last_hb:
                    try:
                        hb_time = _parse_heartbeat(last_hb)
                        is_stale = (datetime.now() - hb_time).total_seconds() > 300
                    except (ValueError, TypeError):
                        pass
                if is_stale:
                    response["status"] = "paused"
                    response["interrupted"] = True

            # Persisted agent messages (last 10)
            events = session.get("recent_events", [])
            response["agent_messages"] = [
                e["data"] for e in events
                if e.get("event") == "agent_message"
            ][-10:]

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get research status for {task_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.post("/api/v1/research/quick-start")
async def quick_start(user_input: str = Form(...), template_id: str = Form(...),
                       user_id: Optional[str] = Form(None),
                       llm_provider: Optional[str] = Form(None), llm_model: Optional[str] = Form(None),
                       llm_api_key: Optional[str] = Form(None), llm_api_endpoint: Optional[str] = Form(None),
                       llm_temperature: Optional[float] = Form(None), llm_max_tokens: Optional[int] = Form(None),
                       llm_top_p: Optional[float] = Form(None),
                       llm_frequency_penalty: Optional[float] = Form(None),
                       llm_presence_penalty: Optional[float] = Form(None),
                       region: Optional[str] = Form(None), time_range: Optional[str] = Form(None),
                       depth: Optional[str] = Form(None),
                       parameters: Optional[str] = Form(None),
                       auto_confirm: str = Form("false"),
                       template_context: Optional[str] = Form(None)):
    from src.config.settings import settings
    llm_config: Dict[str, Any] = {}
    if llm_provider:
        llm_config["provider"] = llm_provider
    if llm_model:
        llm_config["model"] = llm_model
    if llm_api_key:
        llm_config["api_key"] = llm_api_key
    if llm_api_endpoint:
        llm_config["api_endpoint"] = llm_api_endpoint
    if llm_temperature is not None:
        llm_config["temperature"] = llm_temperature
    if llm_max_tokens is not None:
        llm_config["max_tokens"] = llm_max_tokens
    if llm_top_p is not None:
        llm_config["top_p"] = llm_top_p
    if llm_frequency_penalty is not None:
        llm_config["frequency_penalty"] = llm_frequency_penalty
    if llm_presence_penalty is not None:
        llm_config["presence_penalty"] = llm_presence_penalty

    settings.update_from_request(llm_config)
    # Parse dynamic parameters: prefer parameters JSON, fallback to individual fields
    custom_params = {}
    if parameters:
        try:
            parsed = json.loads(parameters)
            if isinstance(parsed, dict):
                custom_params.update(parsed)
        except (json.JSONDecodeError, TypeError):
            pass
    if region and "region" not in custom_params:
        custom_params["region"] = region
    if time_range and "time_range" not in custom_params:
        custom_params["time_range"] = time_range
    if depth and "depth" not in custom_params:
        custom_params["depth"] = depth
    return await research_api.quick_start(user_input=user_input, template_id=template_id,
                                           user_id=user_id, llm_config=llm_config,
                                           custom_params=custom_params if custom_params else None,
                                           auto_confirm=auto_confirm.lower() == "true",
                                           template_context=template_context)


@app.post("/api/v1/research/interact")
async def interact(session_id: str = Form(...), step: int = Form(...), response: str = Form(...)):
    import json
    try:
        response_dict = json.loads(response)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in response")
    return await research_api.handle_interact(session_id, step, response_dict)


@app.post("/api/v1/research/quality/action")
async def quality_action(request: dict):
    from src.api.research_api import QualityActionRequest
    req = QualityActionRequest(**request)
    return await research_api.handle_quality_action(req)


@app.get("/api/v1/research/quality/{session_id}")
async def get_quality_state(session_id: str):
    return await research_api.get_quality_state(session_id)


@app.post("/api/v1/research/feedback")
async def feedback(session_id: str = Form(...), action: str = Form(...),
                    section: Optional[str] = Form(None), adjustment: Optional[str] = Form(None)):
    return await research_api.handle_feedback(session_id, action, section, adjustment)


@app.get("/api/v1/research/preview/{task_id}")
async def get_preview(task_id: str, format: str = "html"):
    return await research_api.get_preview(task_id, format)


@app.get("/api/v1/research/sections/{task_id}")
async def get_sections(task_id: str):
    return await research_api.get_sections(task_id)


@app.post("/api/v1/research/revise")
async def revise_sections(task_id: str = Form(...), aspects: str = Form(...),
                           adjustment: Optional[str] = Form(None)):
    import json
    try:
        aspects_list = json.loads(aspects)
        if not isinstance(aspects_list, list):
            raise ValueError("aspects must be a list")
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid aspects format")
    return await research_api.revise_sections(task_id, aspects_list, adjustment)


@app.get("/api/v1/research/completed")
async def list_completed_research(limit: int = 50):
    from src.api.document_api import DocumentAPI
    return await DocumentAPI().list_completed_research(limit)


@app.get("/api/v1/research/sessions")
def list_all_sessions(limit: int = 20, offset: int = 0):
    try:
        from src.core.session_manager import SessionManager
        from datetime import datetime
        from pathlib import Path
        import json as json_mod

        sm = SessionManager.get_instance()
        sessions_dir = Path("data/sessions")
        if not sessions_dir.exists():
            return {"sessions": [], "total": 0, "has_more": False}

        # Collect all session IDs with created_at (lightweight read, no full parsing)
        sessions_info = []
        for f in sessions_dir.glob("*.json"):
            if f.stem.startswith("test_"):
                continue
            created_at = None
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    data = json_mod.load(fh)
                    created_at = data.get("created_at")
                    if isinstance(created_at, str):
                        created_at = datetime.fromisoformat(created_at)
            except Exception:
                pass  # corrupted file, created_at stays None
            sessions_info.append((created_at, f.stem))

        # Sort by created_at descending (None at end)
        sessions_info.sort(key=lambda x: (x[0] is not None, x[0] or datetime.min), reverse=True)
        total = len(sessions_info)
        page = sessions_info[offset:offset + limit]

        results = []
        for created_at, sid in page:
            try:
                session = sm.get(sid)
                if not session:
                    continue

                if isinstance(created_at, datetime):
                    created_at = created_at.isoformat()

                research_context = session.get("research_context", {})
                topic = (research_context.get("topic") if isinstance(research_context, dict) else None) or session.get("user_input", "")

                state_machine = session.get("state_machine")
                if state_machine and hasattr(state_machine, "current_state"):
                    status_map = {
                        "understanding": "paused", "clarifying": "paused",
                        "framework_confirm": "analyzing", "executing": "reporting",
                        "paused": "paused", "previewing": "completed",
                        "completed": "completed", "cancelled": "paused",
                    }
                    state = status_map.get(state_machine.current_state.value, "paused")
                else:
                    current_step = session.get("current_step", 0)
                    if current_step == 6:
                        state = "reporting"
                    elif current_step and current_step > 0:
                        state = "analyzing"
                    else:
                        state = "paused"

                results.append({
                    "task_id": sid, "title": topic or session.get("user_input", "Unnamed Research"),
                    "topic": topic, "query": session.get("user_input", ""),
                    "status": state, "created_at": created_at, "completed_at": None,
                    "output_format": session.get("output_type"), "generated_formats": [],
                })
            except Exception as e:
                logger.warning(f"Failed to process session {sid}: {e}")

        return {"sessions": results, "total": total, "has_more": offset + limit < total}
    except Exception as e:
        logger.error(f"list_all_sessions failed: {e}", exc_info=True)
        return {"sessions": [], "total": 0, "has_more": False}


@app.get("/api/v1/research/{task_id}")
async def get_research_detail(task_id: str):
    from src.core.session_manager import SessionManager
    from datetime import datetime
    from pathlib import Path

    sm = SessionManager.get_instance()
    session = sm.get(task_id)

    if not session:
        raise HTTPException(status_code=404, detail="Research not found")

    created_at = session.get("created_at")
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()

    research_context = session.get("research_context", {})
    topic = research_context.get("topic") or session.get("user_input", "")

    state_machine = session.get("state_machine")
    if state_machine and hasattr(state_machine, "current_state"):
        status_map = {
            "understanding": "analyzing", "clarifying": "analyzing",
            "framework_confirm": "analyzing", "executing": "reporting",
            "paused": "paused", "previewing": "completed",
            "completed": "completed", "cancelled": "paused",
        }
        state = status_map.get(state_machine.current_state.value, "analyzing")
        # If state_machine says executing but task already finished, correct to completed
        if state_machine.current_state.value == "executing":
            from src.core.progress_streamer import ProgressStreamer
            ps = ProgressStreamer.get_task_state(task_id)
            if ps is None or ps.status == "completed":
                state = "completed"
            elif ps.status == "error":
                state = "paused"
    else:
        state = "analyzing"

    # P1 fix: Include preview and download URLs for completed tasks
    preview_url = None
    download_url = None
    research_result = session.get("research_result", {})
    has_valid_result = bool(research_result and research_result.get("status") == "completed")
    
    # Check for preview HTML file (only for sessions with valid completed research)
    if has_valid_result:
        preview_path = PreviewStorage.path(task_id)
        if preview_path.exists():
            preview_url = PreviewStorage.url(task_id)
        else:
            output_path = research_result.get("output_path") or research_result.get("document_path")
            if output_path and Path(output_path).exists():
                preview_url = PreviewStorage.url(task_id)
    
    # Check for downloadable document
    task_dir = Path("data/reports") / task_id
    if not task_dir.exists():
        task_dir = Path("data") / task_id  # Fallback to legacy location
    if task_dir.exists():
        docs = sorted(task_dir.glob("*.docx")) + sorted(task_dir.glob("*.html"))
        if docs:
            download_url = f"/api/v1/download/{task_id}"

    meta = {
        "task_id": task_id,
        "title": topic or "Unnamed Research",
        "topic": topic,
        "query": session.get("user_input", ""),
        "status": state,
        "created_at": created_at,
        "completed_at": None,
        "output_format": session.get("output_type"),
        "preview_url": preview_url,
        "download_url": download_url,
        "result": research_result,  # Include full research result
        # P1 fix: signal when preview needs regeneration
        "needs_regenerate": not preview_url and bool(research_result.get("report", {}).get("sections")),
    }

    messages = []
    history = session.get("conversation_history", [])
    for msg in history:
        if isinstance(msg, dict) and "role" in msg and "content" in msg:
            messages.append({
                "id": msg.get("id", f"msg_{len(messages)}"),
                "role": msg["role"],
                "content": msg["content"],
                "timestamp": msg.get("timestamp", created_at or ""),
            })

    return {**meta, "messages": messages, "config": {
        "output_type": meta.get("output_type", "report"),
        "template": "consulting", "sections": [],
    }}


@app.post("/api/v1/upload")
async def upload_files(files: List[UploadFile] = File(...), session_id: Optional[str] = Form(None)):
    uploaded = []
    for file in files:
        file_id = f"file_{uuid.uuid4().hex[:8]}"
        ext = os.path.splitext(file.filename)[1]
        path = _upload_dir / f"{file_id}{ext}"
        content = await file.read()
        with open(path, "wb") as f:
            f.write(content)
        uploaded.append({"id": file_id, "filename": file.filename,
                          "size": len(content), "type": file.content_type, "path": str(path)})
    return {"session_id": session_id, "files": uploaded, "count": len(uploaded)}


@app.delete("/api/v1/upload/{file_id}")
async def delete_file(file_id: str):
    removed = 0
    for path in _upload_dir.glob(f"{file_id}.*"):
        os.remove(path)
        removed += 1
    if removed == 0:
        raise HTTPException(status_code=404, detail="File not found")
    return {"status": "deleted", "file_id": file_id, "removed": removed}


@app.get("/api/v1/stream/{task_id}")
async def stream_progress(task_id: str):
    from src.core.progress_streamer import ProgressStreamer
    streamer = ProgressStreamer(task_id)
    return StreamingResponse(streamer.generate(), media_type="text/event-stream",
                              headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                                       "X-Accel-Buffering": "no"})


@app.get("/api/v1/session-stream/{session_id}")
async def session_stream(session_id: str):
    """
    Persistent session SSE stream.

    Unlike /api/v1/stream/{task_id} which terminates on task complete,
    this stream stays alive for the entire session lifetime.
    Used for chat_response and agent_message events.
    """
    from src.core.session_streamer import SessionStreamer
    streamer = SessionStreamer(session_id)
    return StreamingResponse(streamer.generate(), media_type="text/event-stream",
                              headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                                       "X-Accel-Buffering": "no"})


@app.get("/api/v1/llm/models")
async def list_llm_models():
    return {"providers": [
        {"id": "openai", "name": "OpenAI", "default_endpoint": "https://api.openai.com/v1"},
        {"id": "anthropic", "name": "Anthropic", "default_endpoint": "https://api.anthropic.com/v1"},
        {"id": "deepseek", "name": "DeepSeek", "default_endpoint": "https://api.deepseek.com/v1"},
        {"id": "azure", "name": "Azure OpenAI", "default_endpoint": ""},
        {"id": "local", "name": "Local Model", "default_endpoint": "http://localhost:11434/v1"},
        {"id": "custom", "name": "Custom", "default_endpoint": ""},
    ], "models": [
        {"id": "gpt-4o", "name": "GPT-4o", "provider": "openai", "max_tokens": 128000},
        {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "provider": "openai", "max_tokens": 128000},
        {"id": "gpt-4-turbo", "name": "GPT-4 Turbo", "provider": "openai", "max_tokens": 128000},
        {"id": "gpt-4", "name": "GPT-4", "provider": "openai", "max_tokens": 8192},
        {"id": "gpt-3.5-turbo", "name": "GPT-3.5 Turbo", "provider": "openai", "max_tokens": 16385},
        {"id": "o1-preview", "name": "O1 Preview", "provider": "openai", "max_tokens": 128000},
        {"id": "o1-mini", "name": "O1 Mini", "provider": "openai", "max_tokens": 128000},
        {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet", "provider": "anthropic", "max_tokens": 200000},
        {"id": "claude-3-opus-20240229", "name": "Claude 3 Opus", "provider": "anthropic", "max_tokens": 200000},
        {"id": "claude-3-sonnet-20240229", "name": "Claude 3 Sonnet", "provider": "anthropic", "max_tokens": 200000},
        {"id": "claude-3-haiku-20240307", "name": "Claude 3 Haiku", "provider": "anthropic", "max_tokens": 200000},
        {"id": "deepseek-v4-pro", "name": "DeepSeek V4 Pro", "provider": "deepseek", "max_tokens": 128000},
        {"id": "deepseek-v4-flash", "name": "DeepSeek V4 Flash", "provider": "deepseek", "max_tokens": 128000},
        {"id": "azure-gpt-4o", "name": "Azure GPT-4o", "provider": "azure", "max_tokens": 128000},
        {"id": "azure-gpt-4", "name": "Azure GPT-4", "provider": "azure", "max_tokens": 8192},
        {"id": "llama3.1", "name": "LLaMA 3.1", "provider": "local", "max_tokens": 128000},
        {"id": "llama3.2", "name": "LLaMA 3.2", "provider": "local", "max_tokens": 128000},
        {"id": "mistral", "name": "Mistral", "provider": "local", "max_tokens": 32000},
        {"id": "codellama", "name": "CodeLLaMA", "provider": "local", "max_tokens": 16000},
        {"id": "qwen2.5", "name": "Qwen 2.5", "provider": "local", "max_tokens": 32000},
    ]}


@app.get("/api/v1/llm/config")
async def get_llm_config():
    from src.config.settings import settings
    return {"provider": settings.llm.provider,
            "model": settings.llm.model, "apiEndpoint": settings.llm.base_url,
            "apiKey": settings.llm.api_key,
            "temperature": settings.llm.temperature, "maxTokens": settings.llm.max_tokens,
            "topP": settings.llm.top_p,
            "frequencyPenalty": settings.llm.frequency_penalty,
            "presencePenalty": settings.llm.presence_penalty,
            "hasApiKey": bool(settings.llm.api_key)}


@app.post("/api/v1/llm/config")
async def update_llm_config(config: Dict[str, Any]):
    from src.config.settings import settings
    settings.update_from_request(config)
    return {"provider": settings.llm.provider,
            "model": settings.llm.model, "apiEndpoint": settings.llm.base_url,
            "apiKey": settings.llm.api_key,
            "temperature": settings.llm.temperature, "maxTokens": settings.llm.max_tokens,
            "topP": settings.llm.top_p,
            "frequencyPenalty": settings.llm.frequency_penalty,
            "presencePenalty": settings.llm.presence_penalty,
            "hasApiKey": bool(settings.llm.api_key)}


@app.post("/api/v1/llm/config/reset")
async def reset_llm_config():
    """从 .env 重新加载 LLM 配置"""
    from src.config.settings import settings
    settings.reset_llm_to_env()
    return {"provider": settings.llm.provider,
            "model": settings.llm.model, "apiEndpoint": settings.llm.base_url,
            "apiKey": settings.llm.api_key,
            "temperature": settings.llm.temperature, "maxTokens": settings.llm.max_tokens,
            "topP": settings.llm.top_p,
            "frequencyPenalty": settings.llm.frequency_penalty,
            "presencePenalty": settings.llm.presence_penalty,
            "hasApiKey": bool(settings.llm.api_key)}


@app.get("/api/v1/llm/health")
async def llm_health():
    """Quick diagnostic: test LLM connectivity (no API key transmitted)"""
    from src.config.settings import settings
    from urllib.parse import urlparse
    import socket as _socket
    result = {"model": settings.llm.model, "has_key": bool(settings.llm.api_key)}

    try:
        parsed = urlparse(settings.llm.base_url)
        host = parsed.hostname
        if not host:
            result["reachable"] = False
            result["error"] = "Invalid base_url configuration"
            return result
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        _socket.create_connection((host, port), timeout=5)
        result["reachable"] = True
    except Exception:
        result["reachable"] = False
        result["error"] = "Connection failed"

    return result


# ============ Document API ============
from src.api.document_api import DocumentAPI, DocumentAPIRouter

async def _knowledge_deposit_callback(task_id, aggregated_dict):
    """Post-export knowledge deposit — triggered after user downloads final report"""
    try:
        topic = aggregated_dict.get("topic", task_id)
        await _research_orchestrator._phase5_deposit_knowledge(
            aggregated_dict=aggregated_dict,
            task_id=task_id,
            topic=topic,
        )
        logger.info(f"[EXPORT] Knowledge deposit completed for {task_id}")
    except Exception as e:
        logger.warning(f"[EXPORT] Knowledge deposit failed for {task_id}: {e}")

document_api = DocumentAPI(knowledge_deposit_callback=_knowledge_deposit_callback)
document_router = DocumentAPIRouter(document_api).get_router()
if document_router:
    app.include_router(document_router, prefix="/api/v1")

# ============ Prompt API ============
try:
    from src.api.prompt_api import PromptAPIRouter, prompt_api as _prompt_api_instance
    _prompt_router = PromptAPIRouter(_prompt_api_instance)
    _prompt_routers = _prompt_router.get_routers()
    for _name, _r in _prompt_routers.items():
        app.include_router(_r, prefix="/api/v1")
    logger.info(f"Prompt API mounted ({len(_prompt_routers)} routers)")
except ImportError as e:
    logger.warning(f"Prompt API unavailable: {e}")

# ============ MCP API ============
try:
    from src.api.mcp_api import router as mcp_router
    app.include_router(mcp_router, prefix="/api/v1")
except ImportError:
    pass

# ============ Survey API ============
try:
    from src.survey.task_api import router as survey_router
    app.include_router(survey_router)
    logger.info("Survey API mounted at /api/v1/surveys/")
except ImportError as e:
    logger.warning(f"Survey API unavailable: {e}")

# ============ Version ============
@app.get("/api/v1/version")
async def version():
    info = await get_version_info()
    return info.to_dict()


# ============ Changelog ============
CHANGELOG_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "CHANGELOG.md"


@app.get("/api/v1/changelog")
async def changelog(
    format: str = "text",
    max_lines: int = 50,
):
    if not CHANGELOG_PATH.exists():
        return {"changelog": "", "error": "CHANGELOG.md not found"}

    content = CHANGELOG_PATH.read_text(encoding="utf-8")

    if format == "json":
        import re
        versions = re.split(r"\n(?=## \[)", content)
        entries = []
        for block in versions:
            if not block.strip():
                continue
            lines = block.strip().split("\n")
            header = lines[0] if lines else ""
            entries.append({
                "header": header,
                "body": "\n".join(lines[1:]).strip(),
            })
        return {"changelog": entries, "count": len(entries)}
    else:
        lines = content.strip().split("\n")
        truncated = lines[:max_lines]
        return {"changelog": "\n".join(truncated)}


# ============ Health ============
@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "version": get_local_version()}

@app.get("/")
async def root():
    return {"message": "Zensers API", "docs": "/api/v1/docs"}

_scheduled_dream_task = None

@app.on_event("startup")
async def startup_event():
    logger.info("Zensers API started")

    global _scheduled_dream_task, _dream_scheduler, _dream_cfg

    # DreamModeScheduler 后台循环（始终启动，驱动研究提取 + 可选目录扫描）
    if _dream_scheduler:
        _dream_scheduler.start_background()
        if _dream_cfg and _dream_cfg.knowledge_source_dirs:
            logger.info(
                f"DreamModeScheduler started with source dirs: "
                f"{_dream_cfg.knowledge_source_dirs}, "
                f"scan_interval={_dream_cfg.knowledge_scan_interval}s"
            )
        else:
            logger.info("DreamModeScheduler started (research extraction only, no source dirs)")

    # Scheduled DreamMode (background memory consolidation every 24 hours)
    if _knowledge_manager:
        async def _scheduled_dream():
            try:
                while True:
                    await asyncio.sleep(24 * 3600)
                    await _knowledge_manager.run_dream_mode(trigger="scheduled")
            except asyncio.CancelledError:
                logger.info("Scheduled DreamMode task cancelled")
            except Exception as e:
                logger.warning(f"Scheduled DreamMode failed: {e}")

        _scheduled_dream_task = asyncio.create_task(_scheduled_dream())
        logger.info("Scheduled DreamMode task created (every 24h)")

@app.on_event("shutdown")
async def shutdown_event():
    global _scheduled_dream_task, _dream_scheduler
    logger.info("Zensers API shutting down")

    # 停止 DreamModeScheduler
    if _dream_scheduler:
        await _dream_scheduler.shutdown()
        logger.info("DreamModeScheduler shut down")

    # Cancel scheduled DreamMode
    if _scheduled_dream_task:
        _scheduled_dream_task.cancel()
        logger.info("Scheduled DreamMode task cancelled")

    # Cancel all ResearchAPI background tasks (prevent shutdown from blocking on LLM calls)
    try:
        from src.api.research_api import ResearchAPI
        bg_tasks = ResearchAPI._background_tasks
        if bg_tasks:
            count = 0
            for sid, task in list(bg_tasks.items()):
                if not task.done():
                    task.cancel()
                    count += 1
            bg_tasks.clear()
            ResearchAPI._background_task_gen.clear()
            if count > 0:
                logger.info(f"Cancelled {count} pending ResearchAPI background tasks")
    except Exception as e:
        logger.warning(f"Failed to cancel ResearchAPI background tasks: {e}")

    if _knowledge_manager:
        try:
            _knowledge_manager.close()
            logger.info("KnowledgeManager closed")
        except Exception as e:
            logger.warning(f"KnowledgeManager close failed: {e}")

# ============ DreamModeScheduler ============
from src.core.memory.dream.dream_scheduler import DreamModeScheduler, DreamModeConfig
from src.core.memory.dream.raw_data_store import RawResearchDataStore

_dream_scheduler: Optional[DreamModeScheduler] = None
_dream_cfg: Optional[DreamModeConfig] = None
if _knowledge_manager:
    _dream_cfg = DreamModeConfig.from_env()
    _dream_scheduler = DreamModeScheduler(
        knowledge_bank=_knowledge_manager.knowledge_bank,
        raw_data_store=RawResearchDataStore(user_id=_knowledge_manager.user_id),
        config=_dream_cfg,
    )


