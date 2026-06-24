# -*- coding: utf-8 -*-
"""
Document Generation Web API
===========================

Provides RESTful API endpoints for document generation:
1. Document Generation API
2. Version Management API
3. Export API
4. Preview API
5. Adjustment API
6. Research Delayed Generation API

Design Principles:
- Input Validation: validate all inputs for type and format
- Path Safety: prevent path traversal attacks
- Error Handling: clear exception types, meaningful error messages
- Logging: log key operations
"""

import logging
import re
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

# FastAPI optional dependency
try:
    from fastapi import FastAPI, HTTPException, APIRouter
    from pydantic import BaseModel, validator
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    # Placeholder class
    FastAPI = object
    APIRouter = object
    HTTPException = Exception
    BaseModel = object
    validator = lambda *args, **kwargs: lambda x: x

logger = logging.getLogger(__name__)


# ==================== Constants ====================

# Supported output formats
VALID_OUTPUT_FORMATS = {"docx", "pptx", "pdf", "html"}

# Supported templates
VALID_TEMPLATES = {"consulting", "academic", "business", "minimal"}

# Supported adjustment types
VALID_ADJUSTMENT_TYPES = {"GLOBAL", "PAGE", "SECTION", "ELEMENT"}

# Supported preview formats
VALID_PREVIEW_FORMATS = {"png", "jpg", "pdf"}

# Safe name pattern (prevent injection)
SAFE_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')

# Version ID pattern
VERSION_ID_PATTERN = re.compile(r'^v\d+$')

# Task ID pattern
TASK_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')

# Max list limit
MAX_LIST_LIMIT = 1000

# Dangerous path patterns
DANGEROUS_PATH_PATTERNS = [
    '../', '..\\',  # Path traversal
    '/etc/', '/root/', '/home/',  # System directories
    '\\Windows\\', '\\Program Files\\',  # Windows system directories
]


# ==================== Data Models ====================

class OutputFormat(str, Enum):
    """Output format enum"""
    DOCX = "docx"
    PPTX = "pptx"
    PDF = "pdf"
    HTML = "html"


class AdjustmentType(str, Enum):
    """Adjustment type enum"""
    GLOBAL = "GLOBAL"
    PAGE = "PAGE"
    SECTION = "SECTION"
    ELEMENT = "ELEMENT"


@dataclass
class GenerateDocumentRequest:
    """Generate document request"""
    task_id: str
    output_format: str = "docx"
    template: str = "consulting"
    
    def validate(self) -> Optional[str]:
        """Validate request parameters, returns error message or None"""
        if not self.task_id:
            return "task_id is required"
        
        if not TASK_ID_PATTERN.match(self.task_id):
            return f"Invalid task_id format: {self.task_id}"
        
        if self.output_format not in VALID_OUTPUT_FORMATS:
            return f"Invalid output_format: {self.output_format}. Valid formats: {VALID_OUTPUT_FORMATS}"
        
        if self.template not in VALID_TEMPLATES:
            return f"Invalid template: {self.template}. Valid templates: {VALID_TEMPLATES}"
        
        return None


@dataclass
class ExportDocumentRequest:
    """Export document request"""
    task_id: str
    version_id: str
    format: str
    export_path: Optional[str] = None
    
    def validate(self) -> Optional[str]:
        """Validate request parameters"""
        if not self.task_id or not TASK_ID_PATTERN.match(self.task_id):
            return f"Invalid task_id: {self.task_id}"
        
        if self.version_id != 'latest' and not VERSION_ID_PATTERN.match(self.version_id):
            return f"Invalid version_id: {self.version_id}"
        
        if self.format not in VALID_OUTPUT_FORMATS:
            return f"Invalid format: {self.format}"
        
        # Path safety check (skip if export_path not provided)
        if self.export_path:
            for pattern in DANGEROUS_PATH_PATTERNS:
                if pattern.lower() in self.export_path.lower():
                    return f"Unsafe export path detected"
        
        return None


@dataclass
class AdjustDocumentRequest:
    """Adjust document request"""
    task_id: str
    adjustment_type: str
    target: Optional[str]
    changes: Dict[str, Any] = field(default_factory=dict)
    
    def validate(self) -> Optional[str]:
        """Validate request parameters"""
        if not self.task_id or not TASK_ID_PATTERN.match(self.task_id):
            return f"Invalid task_id: {self.task_id}"
        
        if self.adjustment_type not in VALID_ADJUSTMENT_TYPES:
            return f"Invalid adjustment_type: {self.adjustment_type}. Valid types: {VALID_ADJUSTMENT_TYPES}"
        
        # SECTION and ELEMENT types require target
        if self.adjustment_type in ("SECTION", "ELEMENT") and not self.target:
            return f"Target is required for {self.adjustment_type} adjustment"
        
        return None


@dataclass
class DelayedGenerateRequest:
    """Delayed generate request"""
    task_id: str
    output_format: str = "docx"
    template: str = "consulting"
    
    def validate(self) -> Optional[str]:
        """Validate request parameters"""
        if not self.task_id or not TASK_ID_PATTERN.match(self.task_id):
            return f"Invalid task_id: {self.task_id}"
        
        if self.output_format not in VALID_OUTPUT_FORMATS:
            return f"Invalid output_format: {self.output_format}"
        
        if self.template not in VALID_TEMPLATES:
            return f"Invalid template: {self.template}"
        
        return None


# ==================== Revision Related Requests ====================

# Supported revision types
VALID_REVISION_TYPES = {"minor", "section", "phase", "full"}


@dataclass
class RevisionRequest:
    """Revision request"""
    task_id: str
    revision_type: str
    user_feedback: str
    section_id: Optional[str] = None
    section_title: Optional[str] = None
    keywords: Optional[List[str]] = None
    target_content: Optional[str] = None
    
    def validate(self) -> Optional[str]:
        """Validate request parameters"""
        if not self.task_id or not TASK_ID_PATTERN.match(self.task_id):
            return f"Invalid task_id: {self.task_id}"
        
        if self.revision_type not in VALID_REVISION_TYPES:
            return f"Invalid revision_type: {self.revision_type}. Valid types: {VALID_REVISION_TYPES}"
        
        # section type requires location information
        if self.revision_type == "section":
            if not any([self.section_id, self.section_title, self.keywords]):
                return "section revision requires section_id, section_title, or keywords"
            if not self.target_content:
                return "section revision requires target_content"
        
        return None


@dataclass
class RevisionLoopRequest:
    """Revision loop request"""
    task_id: str
    max_rounds: int = 10
    
    def validate(self) -> Optional[str]:
        """Validate request parameters"""
        if not self.task_id or not TASK_ID_PATTERN.match(self.task_id):
            return f"Invalid task_id: {self.task_id}"
        
        if self.max_rounds < 1 or self.max_rounds > 10:
            return "max_rounds must be between 1 and 10"
        
        return None


@dataclass
class FeedbackRequest:
    """User feedback request"""
    loop_id: str
    accepted: bool
    revision_type: Optional[str] = None
    section_id: Optional[str] = None
    section_title: Optional[str] = None
    keywords: Optional[List[str]] = None
    user_feedback: Optional[str] = None
    target_content: Optional[str] = None
    
    def validate(self) -> Optional[str]:
        """Validate request parameters"""
        if not self.loop_id:
            return "loop_id is required"
        
        if self.accepted:
            return None  # Confirmation of finalization requires no other parameters
        
        # Revision requires more information
        if self.revision_type and self.revision_type not in VALID_REVISION_TYPES:
            return f"Invalid revision_type: {self.revision_type}"
        
        return None


# ==================== API Implementation ====================

class DocumentAPI:
    """
    Document Generation API
    
    Provides RESTful API interface for document generation, version management, export, preview and adjustment.
    """
    
    def __init__(
        self,
        storage_dir: Optional[str] = None,
        version_manager = None,
        export_manager = None,
        preview_generator = None,
        adjustment_handler = None,
        research_result_store = None,
        knowledge_deposit_callback = None,
    ):
        """
        Initialize API
        
        Args:
            storage_dir: Storage directory
            version_manager: Version manager instance
            export_manager: Export manager instance
            preview_generator: Preview generator instance
            adjustment_handler: Adjustment handler instance
            research_result_store: Research result store instance
            knowledge_deposit_callback: async callable(task_id, aggregated_dict) for post-export knowledge deposit
        """
        self.storage_dir = Path(storage_dir) if storage_dir else Path("./data/documents")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Dependency injection (lazy loading)
        self._version_manager = version_manager
        self._export_manager = export_manager
        self._preview_generator = preview_generator
        self._adjustment_handler = adjustment_handler
        self._research_result_store = research_result_store
        self._knowledge_deposit_callback = knowledge_deposit_callback
        self._background_tasks = set()  # prevent GC of fire-and-forget tasks
        
        logger.info(f"DocumentAPI initialized with storage_dir={self.storage_dir}")
    
    def _is_safe_path(self, path: str) -> bool:
        """Check if path is safe"""
        for pattern in DANGEROUS_PATH_PATTERNS:
            if pattern.lower() in path.lower():
                return False
        return True
    
    # ==================== Document Generation API ====================
    
    async def generate_document(
        self,
        request: GenerateDocumentRequest
    ) -> Dict[str, Any]:
        """
        Generate document
        
        Args:
            request: Generate document request
            
        Returns:
            Generation result
        """
        # Validate input
        error = request.validate()
        if error:
            logger.warning(f"Invalid generate request: {error}")
            return {"status": "failed", "error": error}
        
        try:
            logger.info(f"Generating document for task={request.task_id}, format={request.output_format}")
            
            # Get research result
            research_result = await self._get_research_result(request.task_id)
            if not research_result:
                return {"status": "failed", "error": f"Research result not found: {request.task_id}"}
            
            # Generate document
            result = await self._generate_document(
                research_result=research_result,
                output_format=request.output_format,
                template=request.template
            )
            
            logger.info(f"Document generated: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to generate document: {e}")
            return {"status": "failed", "error": str(e)}
    
    async def _get_research_result(self, task_id: str) -> Optional[Dict]:
        """Get research result"""
        if self._research_result_store:
            return await self._research_result_store.get_result(task_id)
        # Mock implementation
        return {
            "task_id": task_id,
            "topic": "Sample Research",
            "sections": [],
            "status": "completed"
        }
    
    async def _generate_document(
        self,
        research_result: Dict,
        output_format: str,
        template: str
    ) -> Dict[str, Any]:
        """Generate document"""
        # Mock implementation
        return {
            "status": "success",
            "document_path": f"{self.storage_dir}/{research_result['task_id']}.{output_format}",
            "version_id": "v1"
        }
    
    # ==================== Version Management API ====================
    
    async def list_versions(
        self,
        task_id: str,
        format: str
    ) -> List[Dict]:
        """
        List versions
        
        Args:
            task_id: Task ID
            format: Document format
            
        Returns:
            Version list
        """
        if not TASK_ID_PATTERN.match(task_id):
            logger.warning(f"Invalid task_id: {task_id}")
            return []
        
        if format not in VALID_OUTPUT_FORMATS:
            logger.warning(f"Invalid format: {format}")
            return []
        
        return await self._list_versions(task_id, format)
    
    async def _list_versions(self, task_id: str, format: str) -> List[Dict]:
        """List versions"""
        if self._version_manager:
            return await self._version_manager.list_versions(task_id, format)
        # Mock implementation
        return [{"version_id": "v1", "created_at": datetime.now().isoformat()}]
    
    async def rollback_version(
        self,
        task_id: str,
        format: str,
        target_version: str
    ) -> Dict[str, Any]:
        """
        Rollback version
        
        Args:
            task_id: Task ID
            format: Document format
            target_version: Target version
            
        Returns:
            Rollback result
        """
        if not TASK_ID_PATTERN.match(task_id):
            return {"status": "failed", "error": f"Invalid task_id: {task_id}"}
        
        if not VERSION_ID_PATTERN.match(target_version):
            return {"status": "failed", "error": f"Invalid version_id: {target_version}"}
        
        return await self._rollback_version(task_id, format, target_version)
    
    async def _rollback_version(
        self,
        task_id: str,
        format: str,
        target_version: str
    ) -> Dict[str, Any]:
        """Rollback version"""
        if self._version_manager:
            return await self._version_manager.rollback_to_version(task_id, format, target_version)
        # Mock implementation
        return {
            "status": "success",
            "version_id": f"v{int(target_version[1:]) + 1}",
            "rolled_back_from": target_version
        }
    
    # ==================== Export API ====================
    
    async def export_document(
        self,
        request: ExportDocumentRequest
    ) -> Dict[str, Any]:
        """
        Export document
        
        Args:
            request: Export request
            
        Returns:
            Export result
        """
        # Validate input
        error = request.validate()
        if error:
            logger.warning(f"Invalid export request: {error}")
            return {"status": "failed", "error": error}
        
        # Path safety check (skip if export_path not provided)
        if request.export_path and not self._is_safe_path(request.export_path):
            logger.warning(f"Unsafe export path: {request.export_path}")
            return {"status": "failed", "error": "Unsafe export path"}
        
        return await self._export_document(request)
    
    async def _export_document(self, request: ExportDocumentRequest) -> Dict[str, Any]:
        """Export document: convert latest HTML preview to DOCX"""
        task_id = request.task_id
        
        # ========== EXPORT START ==========
        logger.info(f"[EXPORT] ========== Starting export for task_id={task_id} ==========")
        logger.info(f"[EXPORT] Step 1: Checking preview file existence")
        
        # 1. Read latest HTML preview
        preview_path = Path("data/previews") / f"{task_id}.html"
        logger.info(f"[EXPORT] Preview path: {preview_path}")
        logger.info(f"[EXPORT] Preview exists: {preview_path.exists()}")
        
        if not preview_path.exists():
            logger.error(f"[EXPORT] FAILED: Preview file not found at {preview_path}")
            # List available previews for debugging
            previews_dir = Path("data/previews")
            if previews_dir.exists():
                available = list(previews_dir.glob("*.html"))[:10]
                logger.info(f"[EXPORT] Available previews (first 10): {[p.name for p in available]}")
            return {"status": "failed", "error": "Preview not found. Generate preview first."}
        
        # Read and validate HTML content
        logger.info(f"[EXPORT] Step 2: Reading HTML content")
        try:
            html_content = preview_path.read_text(encoding="utf-8")
            html_size = len(html_content)
            logger.info(f"[EXPORT] HTML content read successfully, size={html_size} bytes ({html_size/1024:.1f} KB)")
            
            # Validate HTML content
            if not html_content.strip():
                logger.error(f"[EXPORT] FAILED: HTML content is empty")
                return {"status": "failed", "error": "Preview HTML is empty"}
            
            # Log HTML structure info
            has_article = "<article" in html_content.lower()
            has_section = "<section" in html_content.lower()
            has_body = "<body" in html_content.lower()
            logger.info(f"[EXPORT] HTML structure: article={has_article}, section={has_section}, body={has_body}")
            
        except Exception as e:
            logger.error(f"[EXPORT] FAILED: Error reading preview file: {e}")
            return {"status": "failed", "error": f"Failed to read preview: {e}"}

        # 2. Ensure output directory exists under data/reports/
        logger.info(f"[EXPORT] Step 3: Preparing output directory")
        output_dir = Path("data/reports") / task_id
        output_path = str(output_dir / f"{task_id}_report.docx")
        logger.info(f"[EXPORT] Output directory: {output_dir}")
        logger.info(f"[EXPORT] Output path: {output_path}")
        
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"[EXPORT] Output directory created/verified")
        except Exception as e:
            logger.error(f"[EXPORT] FAILED: Could not create output directory: {e}")
            return {"status": "failed", "error": f"Failed to create output directory: {e}"}

        # 3. Convert HTML to DOCX
        logger.info(f"[EXPORT] Step 4: Converting HTML to DOCX")
        try:
            from src.converters.html_to_word import HTMLToWordConverter
            logger.info(f"[EXPORT] HTMLToWordConverter imported successfully")
            
            converter = HTMLToWordConverter()
            logger.info(f"[EXPORT] Converter created, docx_available={converter._docx_available}")
            
            result = converter.convert(html=html_content, output_path=output_path)
            logger.info(f"[EXPORT] Conversion result: success={result.success}, error={result.error}, error_code={result.error_code}")
            
        except ImportError as e:
            logger.error(f"[EXPORT] FAILED: Could not import HTMLToWordConverter: {e}")
            return {"status": "failed", "error": f"Converter not available: {e}"}
        except Exception as e:
            logger.error(f"[EXPORT] FAILED: Unexpected error during conversion: {e}", exc_info=True)
            return {"status": "failed", "error": f"DOCX conversion failed: {e}"}

        if not result.success:
            logger.error(f"[EXPORT] FAILED: Conversion returned failure: {result.error} (code: {result.error_code})")
            return {"status": "failed", "error": result.error or "DOCX conversion failed"}

        # 4. Verify output file
        logger.info(f"[EXPORT] Step 5: Verifying output file")
        output_file = Path(output_path)
        if output_file.exists():
            actual_size = output_file.stat().st_size
            logger.info(f"[EXPORT] Output file exists, size={actual_size} bytes")
        else:
            logger.error(f"[EXPORT] WARNING: Output file does not exist at {output_path}")

        logger.info(f"[EXPORT] ========== Export SUCCESS for task_id={task_id} ==========")
        logger.info(f"[EXPORT] Download URL: /api/v1/download/{task_id}")
        logger.info(f"[EXPORT] File name: {task_id}_report.docx")
        logger.info(f"[EXPORT] File size: {result.file_size}")
        
        # Post-export: trigger knowledge deposit (non-blocking)
        if self._knowledge_deposit_callback:
            try:
                import json as _json
                cache_path = Path("data") / task_id / "research_result_cache.json"
                if not cache_path.exists():
                    cache_path = Path("data/reports") / task_id / "research_result_cache.json"
                if cache_path.exists():
                    with open(cache_path, "r", encoding="utf-8") as _f:
                        _cached = _json.load(_f)
                    from src.core.orchestrator.execution.task_utils import safe_create_task
                    _task = safe_create_task(
                        self._knowledge_deposit_callback(task_id, _cached),
                        name=f"knowledge_deposit_{task_id}"
                    )
                    self._background_tasks.add(_task)
                    _task.add_done_callback(self._background_tasks.discard)
                    logger.info(f"[EXPORT] Knowledge deposit scheduled for task_id={task_id}")
                else:
                    logger.info(f"[EXPORT] No cache file found, skipping knowledge deposit")
            except Exception as _kd_err:
                logger.warning(f"[EXPORT] Knowledge deposit scheduling failed: {_kd_err}")
        
        return {
            "status": "success",
            "download_url": f"/api/v1/download/{task_id}",
            "file_name": f"{task_id}_report.docx",
            "file_size": result.file_size,
        }
    
    # ==================== Preview API ====================
    
    async def get_preview(
        self,
        task_id: str,
        version_id: Optional[str] = None,
        format: str = "png"
    ) -> Dict[str, Any]:
        """
        Get preview
        
        Args:
            task_id: Task ID
            version_id: Version ID (optional)
            format: Preview format
            
        Returns:
            Preview result
        """
        if not TASK_ID_PATTERN.match(task_id):
            return {"status": "failed", "error": f"Invalid task_id: {task_id}"}
        
        if version_id and not VERSION_ID_PATTERN.match(version_id):
            return {"status": "failed", "error": f"Invalid version_id: {version_id}"}
        
        if format not in VALID_PREVIEW_FORMATS:
            return {"status": "failed", "error": f"Invalid preview format: {format}"}
        
        return await self._generate_preview(task_id, version_id, format)
    
    async def _generate_preview(
        self,
        task_id: str,
        version_id: Optional[str],
        format: str
    ) -> Dict[str, Any]:
        """Generate preview"""
        if self._preview_generator:
            document_path = f"{self.storage_dir}/{task_id}.docx"
            return await self._preview_generator.generate_preview(
                document_path=document_path,
                format=format
            )
        # Mock implementation
        return {
            "status": "success",
            "preview_path": f"{self.storage_dir}/{task_id}_preview.{format}",
            "format": format,
            "pages": 1
        }
    
    # ==================== Adjustment API ====================
    
    async def adjust_document(
        self,
        request: AdjustDocumentRequest
    ) -> Dict[str, Any]:
        """
        Adjust document
        
        Args:
            request: Adjustment request
            
        Returns:
            Adjustment result
        """
        # Validate input
        error = request.validate()
        if error:
            logger.warning(f"Invalid adjust request: {error}")
            return {"status": "failed", "error": error}
        
        return await self._adjust_document(request)
    
    async def _adjust_document(self, request: AdjustDocumentRequest) -> Dict[str, Any]:
        """Adjust document"""
        if self._adjustment_handler:
            return await self._adjustment_handler.handle_adjustment(
                task_id=request.task_id,
                adjustment_type=request.adjustment_type,
                target=request.target,
                changes=request.changes
            )
        # Mock implementation
        return {
            "status": "success",
            "adjustment_id": f"adj_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "adjustment_type": request.adjustment_type,
            "target": request.target
        }
    
    # ==================== Research Delayed Generation API ====================
    
    async def list_completed_research(
        self,
        limit: int = 100
    ) -> List[Dict]:
        """
        List completed research
        
        Args:
            limit: Result count limit
            
        Returns:
            Research list
        """
        # Validate limit
        if limit < 1 or limit > MAX_LIST_LIMIT:
            limit = 100
        
        return await self._list_completed_research(limit)
    
    async def _list_completed_research(self, limit: int) -> List[Dict]:
        """List completed research"""
        if self._research_result_store:
            return await self._research_result_store.list_results(limit=limit, status="completed")
        # Mock implementation - returns complete data matching frontend types
        now = datetime.now().isoformat()
        return [
            {
                "task_id": "research_001",
                "title": "New Energy Vehicle Market Analysis Report",
                "topic": "New Energy Vehicle Market Analysis",
                "status": "completed",
                "created_at": now,
                "completed_at": now,
                "output_format": "docx",
                "generated_formats": ["docx", "pdf"]
            },
            {
                "task_id": "research_002",
                "title": "Medical AI Industry Research Report",
                "topic": "Medical AI",
                "status": "completed",
                "created_at": now,
                "completed_at": now,
                "output_format": "pptx",
                "generated_formats": ["pptx"]
            },
            {
                "task_id": "research_003",
                "title": "Semiconductor Industry Chain Research Report",
                "topic": "Semiconductor Industry Chain",
                "status": "completed",
                "created_at": now,
                "completed_at": now,
                "output_format": "docx",
                "generated_formats": ["docx", "pdf", "html"]
            }
        ][:limit]
    
    async def delayed_generate(
        self,
        request: DelayedGenerateRequest
    ) -> Dict[str, Any]:
        """
        Delayed generate document
        
        Args:
            request: Delayed generate request
            
        Returns:
            Generation result
        """
        # Validate input
        error = request.validate()
        if error:
            logger.warning(f"Invalid delayed generate request: {error}")
            return {"status": "failed", "error": error}
        
        return await self._delayed_generate(request)
    
    async def _delayed_generate(self, request: DelayedGenerateRequest) -> Dict[str, Any]:
        """Delayed generate document"""
        # Get research result and generate
        research_result = await self._get_research_result(request.task_id)
        if not research_result:
            return {"status": "failed", "error": f"Research result not found: {request.task_id}"}
        
        return await self._generate_document(
            research_result=research_result,
            output_format=request.output_format,
            template=request.template
        )
    
    # ==================== Revision API ====================
    
    async def handle_revision(
        self,
        request: RevisionRequest
    ) -> Dict[str, Any]:
        """
        Handle revision request
        
        Args:
            request: Revision request
            
        Returns:
            Revision result
        """
        # Validate input
        error = request.validate()
        if error:
            logger.warning(f"Invalid revision request: {error}")
            return {"status": "failed", "error": error}
        
        return await self._handle_revision(request)
    
    async def _handle_revision(self, request: RevisionRequest) -> Dict[str, Any]:
        """Handle revision"""
        # Get document path
        document_path = self._get_document_path(request.task_id)
        if not document_path:
            return {"status": "failed", "error": f"Document not found for task: {request.task_id}"}
        
        # Use RevisionHandler to process
        try:
            from ..core.adjustment import RevisionHandler, RevisionRequest
            
            handler = RevisionHandler()
            revision_request = RevisionRequest(
                task_id=request.task_id,
                revision_type=request.revision_type,
                user_feedback=request.user_feedback,
                section_id=request.section_id,
                section_title=request.section_title,
                keywords=request.keywords,
                target_content=request.target_content,
            )
            
            result = handler.handle_revision(document_path, revision_request)
            
            return {
                "status": "success" if result.success else "failed",
                "revision_id": result.revision_id,
                "revision_type": result.revision_type,
                "section_id": result.section_id,
                "revision_count": result.revision_count,
                "error": result.error,
            }
            
        except Exception as e:
            logger.error(f"Revision failed: {e}")
            return {"status": "failed", "error": str(e)}
    
    async def start_revision_loop(
        self,
        request: RevisionLoopRequest
    ) -> Dict[str, Any]:
        """
        Start revision loop
        
        Args:
            request: Revision loop request
            
        Returns:
            Workflow state
        """
        error = request.validate()
        if error:
            return {"status": "failed", "error": error}
        
        return await self._start_revision_loop(request)
    
    async def _start_revision_loop(self, request: RevisionLoopRequest) -> Dict[str, Any]:
        """Start revision loop"""
        document_path = self._get_document_path(request.task_id)
        if not document_path:
            return {"status": "failed", "error": f"Document not found for task: {request.task_id}"}
        
        try:
            from ..core.workflow import PreviewRevisionWorkflow
            
            workflow = PreviewRevisionWorkflow()
            state = workflow.start(
                task_id=request.task_id,
                document_path=document_path,
                max_rounds=request.max_rounds,
            )
            
            return state.to_dict()
            
        except Exception as e:
            logger.error(f"Failed to start revision loop: {e}")
            return {"status": "failed", "error": str(e)}
    
    async def get_revision_loop_status(
        self,
        loop_id: str
    ) -> Dict[str, Any]:
        """
        Get revision loop status
        
        Args:
            loop_id: Workflow ID
            
        Returns:
            Workflow state
        """
        try:
            from ..core.workflow import PreviewRevisionWorkflow
            
            # Note: Need to get workflow instance from somewhere
            # Simplified implementation: return error prompt
            return {
                "status": "failed",
                "error": "Workflow instance not found. Use workflow instance directly.",
            }
            
        except Exception as e:
            return {"status": "failed", "error": str(e)}
    
    async def get_revision_history(
        self,
        task_id: str
    ) -> Dict[str, Any]:
        """
        Get revision history
        
        Args:
            task_id: Task ID
            
        Returns:
            Revision history
        """
        if not task_id or not TASK_ID_PATTERN.match(task_id):
            return {"status": "failed", "error": f"Invalid task_id: {task_id}"}
        
        try:
            from ..core.adjustment import RevisionManager
            
            manager = RevisionManager()
            history = manager.get_revision_history(task_id)
            
            return {
                "status": "success",
                "task_id": task_id,
                "revisions": [r.to_dict() for r in history],
                "count": len(history),
            }
            
        except Exception as e:
            return {"status": "failed", "error": str(e)}
    
    def _get_document_path(self, task_id: str) -> Optional[str]:
        """Get document path"""
        # Check common formats
        for ext in ['.md', '.docx', '.html']:
            path = self.storage_dir / f"{task_id}{ext}"
            if path.exists():
                return str(path)
        
        # Check version directory
        version_dir = self.storage_dir / task_id / "versions"
        if version_dir.exists():
            versions = sorted(version_dir.glob("*.md"))
            if versions:
                return str(versions[-1])
        
        return None


# ==================== FastAPI Router ====================

class DocumentAPIRouter:
    """
    FastAPI Router
    
    Maps DocumentAPI methods to HTTP endpoints.
    """
    
    def __init__(self, api: DocumentAPI):
        """
        Initialize router
        
        Args:
            api: DocumentAPI instance
        """
        self.api = api
        self.routes = []
        
        if FASTAPI_AVAILABLE:
            self._setup_routes()
        else:
            # Mock route list
            self.routes = [
                type('Route', (), {'path': '/documents/generate'}),
                type('Route', (), {'path': '/documents/{task_id}/versions'}),
                type('Route', (), {'path': '/documents/export'}),
                type('Route', (), {'path': '/documents/{task_id}/preview'}),
                type('Route', (), {'path': '/documents/adjust'}),
                type('Route', (), {'path': '/research/completed'}),
                type('Route', (), {'path': '/research/{task_id}/generate'}),
                # Revision related routes
                type('Route', (), {'path': '/documents/revision'}),
                type('Route', (), {'path': '/documents/revision-loop'}),
                type('Route', (), {'path': '/documents/revision-loop/{loop_id}'}),
                type('Route', (), {'path': '/documents/{task_id}/revisions'}),
            ]
    
    def _setup_routes(self):
        """Setup FastAPI routes"""
        router = APIRouter(prefix="/documents", tags=["documents"])
        
        # Document generation
        @router.post("/generate")
        async def generate_document(request: GenerateDocumentRequest):
            return await self.api.generate_document(request)
        
        # Version management
        @router.get("/{task_id}/versions")
        async def list_versions(task_id: str, format: str = "docx"):
            return await self.api.list_versions(task_id, format)
        
        @router.post("/{task_id}/rollback")
        async def rollback_version(task_id: str, format: str, target_version: str):
            return await self.api.rollback_version(task_id, format, target_version)
        
        # Export
        @router.post("/export")
        async def export_document(request: ExportDocumentRequest):
            return await self.api.export_document(request)
        
        # Preview
        @router.get("/{task_id}/preview")
        async def get_preview(task_id: str, version_id: Optional[str] = None, format: str = "png"):
            return await self.api.get_preview(task_id, version_id, format)
        
        # Adjustment
        @router.post("/adjust")
        async def adjust_document(request: AdjustDocumentRequest):
            return await self.api.adjust_document(request)
        
        # Revision
        @router.post("/revision")
        async def handle_revision(request: RevisionRequest):
            return await self.api.handle_revision(request)
        
        # Revision loop
        @router.post("/revision-loop")
        async def start_revision_loop(request: RevisionLoopRequest):
            return await self.api.start_revision_loop(request)
        
        @router.get("/revision-loop/{loop_id}")
        async def get_revision_loop_status(loop_id: str):
            return await self.api.get_revision_loop_status(loop_id)
        
        # Revision history
        @router.get("/{task_id}/revisions")
        async def get_revision_history(task_id: str):
            return await self.api.get_revision_history(task_id)
        
        self._router = router
        self.routes = router.routes
    
    def get_router(self):
        """Get FastAPI Router"""
        if FASTAPI_AVAILABLE and hasattr(self, '_router'):
            return self._router
        return None


def create_app(
    storage_dir: Optional[str] = None,
    **kwargs
):
    """
    Create FastAPI application
    
    Args:
        storage_dir: Storage directory
        **kwargs: Parameters passed to DocumentAPI
        
    Returns:
        FastAPI application instance
    """
    if not FASTAPI_AVAILABLE:
        logger.warning("FastAPI not available, returning mock app")
        return type('MockApp', (), {
            'title': 'Document Generation API',
            'routes': []
        })()
    
    app = FastAPI(
        title="Document Generation API",
        description="Unified Document Generation RESTful API",
        version="1.0.0"
    )
    
    # Initialize API
    api = DocumentAPI(storage_dir=storage_dir, **kwargs)
    
    # Register routes
    router_wrapper = DocumentAPIRouter(api)
    router = router_wrapper.get_router()
    if router:
        app.include_router(router)
    
    # Research related routes
    research_router = APIRouter(prefix="/research", tags=["research"])
    
    @research_router.get("/completed")
    async def list_completed_research(limit: int = 100):
        return await api.list_completed_research(limit)
    
    @research_router.post("/{task_id}/generate")
    async def delayed_generate(
        task_id: str,
        output_format: str = "docx",
        template: Optional[str] = None,
    ):
        """Delayed generate document"""
        from .document_api import DelayedGenerateRequest
        return await api.delayed_generate(DelayedGenerateRequest(
            task_id=task_id,
            output_format=output_format,
            template=template or "consulting",
        ))
    
    app.include_router(research_router)
    
    logger.info("FastAPI app created successfully")
    return app
