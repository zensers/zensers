# Unified Document Generation Agent Design

> **Version**: v3.0  
> **Date**: 2026-04-11  
> **Status**: Design Complete, Pending Implementation  
> **Architecture Basis**: AGENT_ARCHITECTURE.md + AGENT_SESSION_MANAGEMENT.md  
> **Core Solution**: HTML intermediate format + Unified converter + Version control + Web preview

---

## Important Note: Project Structure Boundaries

> **This design strictly follows the existing project architecture, does not depend on external reference projects**

### Project Code Location (src/ directory only)

| Directory | Description | Modifiable |
|------|------|--------|
| `src/agents/fixed_agents/` | Fixed Agent implementations | ✅ |
| `src/core/` | Core framework | ✅ |
| `src/skills/` | Skill system | ✅ |
| `src/utils/` | Utility functions | ✅ |
| `config/` | Configuration files | ✅ |
| `tests/` | Test code | ✅ |
| `data/` | Runtime data | ✅ |

### Reference Locations (Reference only, not dependencies)

| Directory | Description | Modifiable |
|------|------|--------|
| `mem0/` | External open source project (reference) | ❌ |
| `letta/` | External open source project (reference) | ❌ |
| `graphify/` | External open source project (reference) | ❌ |
| `venv/` | Python virtual environment | ❌ |

---

## 1. Design Background and Objectives

### 1.1 Problem Analysis

| Issue | Current Status | Target Solution |
|------|------|----------|
| Word/PPT generation separated | LayoutDesignAgent(Word) + PPTGenerationAgent(separate design) | Unified DocumentGenerationAgent |
| Template system duplicated | Two independent template designs | One unified template system |
| Adjustment mechanism missing | Word has no adjustment, PPT needs redesign | Unified adjustment mechanism |
| State tracking inconsistent | Word has no state tracking, PPT requires Session management | Unified Session state management |
| **Research results not persisted** | Cannot generate on demand when user doesn't specify format | Persist research results, support deferred generation |
| **Version control missing** | Cannot generate same document multiple times | Complete version control system |
| **Export management missing** | Cannot export to specified location | Export manager |

### 1.2 Design Objectives

1. **Unified Agent** — Single DocumentGenerationAgent handles Word/PPT/PDF
2. **Unified Template** — One template system for all formats
3. **Unified State** — Version + Session + Export unified management
4. **Research Result Persistence** — Support delayed generation and regeneration
5. **Version Control** — Full document version history

---

## 2. Architecture Design

### 2.1 Overall Architecture

```
┌─────────────────────────────────────────────────────────────┐
│               DocumentGenerationAgent                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────┐   ┌───────────────────────────┐   │
│  │   Version Manager    │   │    Export Manager          │   │
│  │   - version history  │   │    - path management       │   │
│  │   - comparison       │   │    - format conversion     │   │
│  │   - rollback         │   │    - batch export          │   │
│  └─────────────────────┘   └───────────────────────────┘   │
│                                                             │
│  ┌─────────────────────┐   ┌───────────────────────────┐   │
│  │   HTML Generator    │   │    Format Converters        │   │
│  │   - template render │   │    - HTML to Word           │   │
│  │   - chart embed     │   │    - HTML to PPT            │   │
│  │   - data inject     │   │    - HTML to PDF            │   │
│  └─────────────────────┘   └───────────────────────────┘   │
│                                                             │
│  ┌─────────────────────┐   ┌───────────────────────────┐   │
│  │   Session Manager   │   │    Research Result Store   │   │
│  │   - state tracking  │   │    - result persistence    │   │
│  │   - progress        │   │    - deferred generation   │   │
│  │   - recovery        │   │    - data integrity        │   │
│  └─────────────────────┘   └───────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Core Data Flow

```
ResearchResult (from Orchestrator)
  │
  ▼
ResearchResultStore.persist()
  │
  └─ Save to disk (JSON + data_points JSON)
  │
  ▼
DocumentGenerationAgent.generate()
  │
  ├─ 1. Load research result
  │     └─ ResearchResultStore.load()
  │
  ├─ 2. Generate HTML (intermediate format)
  │     └─ HTMLGenerator.render()
  │
  ├─ 3. Convert to target format
  │     ├─ to Word → HTMLtoWordConverter
  │     ├─ to PPT  → HTMLtoPPTConverter
  │     └─ to PDF  → HTMLtoPDFConverter
  │
  ├─ 4. Save document + version record
  │     ├─ ExportManager.save()
  │     └─ VersionManager.record()
  │
  └─ 5. Update session status
        └─ SessionManager.complete()
```

---

## 3. Core Components

### 3.1 ResearchResultStore

```python
class ResearchResultStore:
    """Research result persistence - supports deferred generation"""

    STORAGE_VERSION = 2  # Schema version for forward compatibility

    def __init__(self, base_dir: str = "data/research_results"):
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def persist(self, task_id: str, result: ResearchResult) -> str:
        """Persist research result to disk"""
        task_dir = self._base_dir / task_id
        task_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "version": self.STORAGE_VERSION,
            "task_id": task_id,
            "topic": result.topic,
            "summary": result.summary,
            "sections": result.sections,
            "data_points": result.data_points,
            "created_at": time.time(),
        }

        path = task_dir / "result.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return str(path)

    def load(self, task_id: str) -> Optional[ResearchResult]:
        """Load persisted research result"""
        path = self._base_dir / task_id / "result.json"
        if not path.exists():
            return None

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return ResearchResult(
            task_id=data["task_id"],
            topic=data["topic"],
            summary=data.get("summary", ""),
            sections=data.get("sections", []),
            data_points=data.get("data_points", []),
        )
```

### 3.2 Version Manager

```python
class VersionManager:
    """Document version control"""

    MAX_VERSIONS = 10  # Max versions to retain

    def __init__(self, base_dir: str = "output/versions"):
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def record(self, task_id: str, format: str, path: str) -> int:
        """Record a new version, return version number"""
        versions = self._get_versions(task_id)
        version_num = len(versions) + 1

        record = {
            "version": version_num,
            "format": format,
            "path": path,
            "created_at": time.time(),
        }
        versions.append(record)

        self._save_versions(task_id, versions)
        return version_num

    def list_versions(self, task_id: str) -> List[Dict]:
        """List all versions for a task"""
        return self._get_versions(task_id)

    def get_version(self, task_id: str, version: int) -> Optional[Dict]:
        """Get specific version record"""
        versions = self._get_versions(task_id)
        for v in versions:
            if v["version"] == version:
                return v
        return None

    def _get_versions(self, task_id: str) -> List[Dict]:
        path = self._base_dir / f"{task_id}.json"
        if not path.exists():
            return []
        with open(path, "r") as f:
            return json.load(f)

    def _save_versions(self, task_id: str, versions: List[Dict]):
        versions = versions[-self.MAX_VERSIONS:]
        path = self._base_dir / f"{task_id}.json"
        with open(path, "w") as f:
            json.dump(versions, f, indent=2)
```

### 3.3 Export Manager

```python
class ExportManager:
    """Document export management"""

    def __init__(self, output_dir: str = "output/reports"):
        self._output_dir = Path(output_dir)

    def export(self, task_id: str, html_content: str, format: str) -> str:
        """Export document in specified format"""
        output_path = self._output_dir / task_id / f"report.{format}"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if format == "docx":
            self._export_word(html_content, output_path)
        elif format == "pptx":
            self._export_ppt(html_content, output_path)
        elif format == "pdf":
            self._export_pdf(html_content, output_path)
        else:
            raise ValueError(f"Unsupported format: {format}")

        return str(output_path)

    def _export_word(self, html: str, path: Path):
        """Convert HTML to Word"""
        converter = HTMLtoWordConverter()
        converter.convert(html, str(path))

    def _export_ppt(self, html: str, path: Path):
        """Convert HTML to PPT"""
        converter = HTMLtoPPTConverter()
        converter.convert(html, str(path))

    def _export_pdf(self, html: str, path: Path):
        """Convert HTML to PDF"""
        converter = HTMLtoPDFConverter()
        converter.convert(html, str(path))
```

---

## 4. DocumentGenerationAgent Interface

```python
class DocumentGenerationAgent:
    """Unified document generation agent"""

    def __init__(self):
        self._html_generator = HTMLGenerator()
        self._version_manager = VersionManager()
        self._export_manager = ExportManager()
        self._result_store = ResearchResultStore()
        self._session_manager = SessionManager()

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Main entry point"""
        action = task.get("action", "")

        if action == "produce_document":
            return await self._handle_produce(task)
        elif action == "get_preview":
            return await self._handle_preview(task)
        elif action == "get_versions":
            return self._handle_get_versions(task)
        elif action == "export_document":
            return await self._handle_export(task)

        return {"success": False, "error": f"Unknown action: {action}"}

    async def _handle_produce(self, task: Dict) -> Dict:
        """Generate and save document"""
        task_id = task["task_id"]
        output_format = task.get("output_format", "docx")
        research_result = task.get("research_result", {})

        # 1. Persist research result
        self._result_store.persist(task_id, research_result)

        # 2. Generate HTML
        html = await self._html_generator.render(research_result)

        # 3. Export document
        output_path = self._export_manager.export(task_id, html, output_format)

        # 4. Record version
        version = self._version_manager.record(task_id, output_format, output_path)

        return {
            "success": True,
            "version": version,
            "path": output_path,
        }

    async def _handle_preview(self, task: Dict) -> Dict:
        """Generate HTML preview"""
        research_result = task.get("research_result", {})
        html = await self._html_generator.render(research_result)
        return {"success": True, "html": html}

    def _handle_get_versions(self, task: Dict) -> Dict:
        """Get version list"""
        task_id = task["task_id"]
        versions = self._version_manager.list_versions(task_id)
        return {"success": True, "versions": versions}

    async def _handle_export(self, task: Dict) -> Dict:
        """Export existing document"""
        task_id = task["task_id"]
        version = task.get("version")
        output_format = task.get("format", "docx")

        version_data = self._version_manager.get_version(task_id, version)
        if not version_data:
            return {"success": False, "error": f"Version {version} not found"}

        result = self._result_store.load(task_id)
        html = await self._html_generator.render(result)
        output_path = self._export_manager.export(task_id, html, output_format)

        return {"success": True, "path": output_path}
```

---

## 5. File Modification List

| File | Change Type | Description |
|------|----------|------|
| `src/agents/fixed_agents/document_generation_agent.py` | Modify | Refactor to unified architecture |
| `src/core/storage/research_result_store.py` | New | Research result persistence |
| `src/core/document/version_manager.py` | New | Version control |
| `src/core/document/export_manager.py` | New | Export management |
| `src/core/document/html_generator.py` | New | HTML intermediate format generator |
| `src/core/converters/html_to_word.py` | Modify | HTML to Word converter |
| `src/core/converters/html_to_ppt.py` | Modify | HTML to PPT converter |
| `src/core/converters/html_to_pdf.py` | New | HTML to PDF converter |
| `src/core/session/session_manager.py` | Modify | Session state tracking extension |

---

## 6. Implementation Plan

| Phase | Content | Effort | Risk |
|-------|---------|--------|------|
| Phase 1 | ResearchResultStore + basic HTML generation | 2 days | Low |
| Phase 2 | ExportManager + format converters | 3 days | Medium |
| Phase 3 | VersionManager + Session integration | 2 days | Low |
| Phase 4 | Integration testing + documentation | 1 day | Low |

Total: ~8 days
