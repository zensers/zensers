# -*- coding: utf-8 -*-
"""
Document Generation Data Models
===============================

Defines input/output data structures for DocumentGenerationAgent.

Design Principles:
1. Type Safety: Use Enum and strong typing
2. Complete Validation: Input validation in from_dict methods
3. Serialization Friendly: Bidirectional to_dict/from_dict conversion
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


class ValidationError(Exception):
    """Model validation exception"""
    pass


class DocumentFormat(Enum):
    """Document output format"""
    DOCX = "docx"    # Word document
    PPTX = "pptx"    # PowerPoint presentation
    PDF = "pdf"      # PDF document
    HTML = "html"    # HTML webpage


class GenerationAction(Enum):
    """Document generation action type"""
    PRODUCE_DOCUMENT = "produce_document"       # Generate document (create version)
    REGENERATE_DOCUMENT = "regenerate_document" # Regenerate (new version)
    ADJUST_CONTENT = "adjust_content"           # Adjust content (new version)
    EXPORT_DOCUMENT = "export_document"         # Export to specified location
    GET_PREVIEW = "get_preview"                 # Get preview
    LIST_VERSIONS = "list_versions"             # List versions
    ROLLBACK_VERSION = "rollback_version"       # Rollback version
    COMPARE_VERSIONS = "compare_versions"       # Compare versions


@dataclass
class DocumentGenerationRequest:
    """
    Document Generation Request
    
    Input parameter structure, supports two modes:
    1. Immediate Generation: Pass research_result + output_format
    2. Delayed Generation: Pass task_id (load from historical research results)
    
    Attributes:
        action: Action to execute
        task_id: Task ID (delayed generation mode)
        research_result: Research result content (immediate generation mode)
        output_format: Output format
        output_dir: Output directory (optional, uses storage path by default)
        template: Template name (optional)
        version_id: Target version ID (rollback/compare mode)
        version_id_2: Second version ID (compare mode)
        adjustments: Adjustment parameters (adjust mode)
        export_path: Export path (export mode)
        session_context: Session context information
    """
    action: GenerationAction
    task_id: Optional[str] = None
    research_result: Optional[Dict[str, Any]] = None
    output_format: Optional[DocumentFormat] = None
    output_dir: Optional[str] = None  # New: output directory
    template: Optional[str] = None
    
    # Version operation related
    version_id: Optional[str] = None
    version_id_2: Optional[str] = None
    
    # Adjustment parameters
    adjustments: List[Dict[str, Any]] = field(default_factory=list)
    
    # Export path
    export_path: Optional[str] = None
    
    # Session context
    session_context: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "action": self.action.value,
            "task_id": self.task_id,
            "research_result": self.research_result,
            "output_format": self.output_format.value if self.output_format else None,
            "output_dir": self.output_dir,
            "template": self.template,
            "version_id": self.version_id,
            "version_id_2": self.version_id_2,
            "adjustments": self.adjustments,
            "export_path": self.export_path,
            "session_context": self.session_context
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentGenerationRequest":
        """
        Create request from dictionary
        
        Validates required fields and converts types.
        
        Args:
            data: Input data dictionary
            
        Returns:
            DocumentGenerationRequest instance
            
        Raises:
            ValidationError: Field validation failed
        """
        # Validate required fields
        if "action" not in data:
            raise ValidationError("Missing required field: action")
        
        # Parse action
        try:
            action = GenerationAction(data["action"])
        except ValueError as e:
            raise ValidationError(f"Invalid action value: {data['action']}") from e
        
        # Validate required fields based on action type
        output_format = None
        if action in [GenerationAction.PRODUCE_DOCUMENT, GenerationAction.REGENERATE_DOCUMENT]:
            if "output_format" not in data:
                raise ValidationError(f"Missing required field 'output_format' for action: {action.value}")
            
            try:
                output_format = DocumentFormat(data["output_format"])
            except ValueError as e:
                raise ValidationError(f"Invalid output_format value: {data['output_format']}") from e
        
        return cls(
            action=action,
            task_id=data.get("task_id"),
            research_result=data.get("research_result"),
            output_format=output_format,
            output_dir=data.get("output_dir"),
            template=data.get("template"),
            version_id=data.get("version_id"),
            version_id_2=data.get("version_id_2"),
            adjustments=data.get("adjustments", []),
            export_path=data.get("export_path"),
            session_context=data.get("session_context")
        )


@dataclass
class DocumentGenerationResult:
    """
    Document Generation Result
    
    Output structure containing generation status, file path, version info, etc.
    
    Attributes:
        success: Whether successful
        task_id: Task ID
        output_format: Output format
        document_path: Generated document path
        version_id: Version ID
        file_size: File size (bytes)
        pages_estimate: Page count estimate
        preview_path: Preview image path
        error: Error message (on failure)
        error_code: Error code (on failure)
        versions: Version list (list_versions action)
        diff_result: Version diff (compare_versions action)
        warning: Warning message (used in skeleton implementation)
        message: Operation message (on success)
        metadata: Additional metadata
    """
    success: bool
    task_id: Optional[str] = None
    output_format: Optional[DocumentFormat] = None
    document_path: Optional[str] = None
    version_id: Optional[str] = None
    file_size: Optional[int] = None
    pages_estimate: Optional[int] = None
    preview_path: Optional[str] = None
    
    # Error information
    error: Optional[str] = None
    error_code: Optional[str] = None
    
    # Special action results
    versions: Optional[List[Dict[str, Any]]] = None
    diff_result: Optional[Dict[str, Any]] = None
    
    # Warning message (used in skeleton implementation)
    warning: Optional[str] = None
    
    # Operation message (Week 34 addition)
    message: Optional[str] = None
    
    # Additional metadata (Week 34 addition)
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        result = {
            "success": self.success,
            "task_id": self.task_id,
            "output_format": self.output_format.value if self.output_format else None,
            "document_path": self.document_path,
            "version_id": self.version_id,
            "file_size": self.file_size,
            "pages_estimate": self.pages_estimate,
            "preview_path": self.preview_path,
            "error": self.error,
            "error_code": self.error_code,
            "versions": self.versions,
            "diff_result": self.diff_result,
            "warning": self.warning,
            "message": self.message,
            "metadata": self.metadata,
        }
        
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentGenerationResult":
        """
        Create result from dictionary
        
        Args:
            data: Result data dictionary
            
        Returns:
            DocumentGenerationResult instance
        """
        # Parse output_format
        output_format = None
        if data.get("output_format"):
            try:
                output_format = DocumentFormat(data["output_format"])
            except ValueError:
                pass
        
        return cls(
            success=data.get("success", False),
            task_id=data.get("task_id"),
            output_format=output_format,
            document_path=data.get("document_path"),
            version_id=data.get("version_id"),
            file_size=data.get("file_size"),
            pages_estimate=data.get("pages_estimate"),
            preview_path=data.get("preview_path"),
            error=data.get("error"),
            error_code=data.get("error_code"),
            versions=data.get("versions"),
            diff_result=data.get("diff_result"),
            warning=data.get("warning"),
            message=data.get("message"),
            metadata=data.get("metadata"),
        )


@dataclass
class DocumentVersion:
    """
    Document Version
    
    Records version information for each document generation, supports version tracing.
    
    Attributes:
        version_id: Version ID (v1, v2, v3...)
        format: Document format
        file_path: Document storage path
        file_size: File size
        created_at: Creation time
        created_by: Creation type (initial|regenerate|adjustment|rollback)
        template: Template used
        adjustments: Adjustment records
        parent_version: Parent version ID
        change_summary: Change summary
        checksum: File checksum
    """
    version_id: str
    format: DocumentFormat
    file_path: str
    file_size: int
    created_at: datetime
    created_by: str  # initial|regenerate|adjustment|rollback
    
    # Version information
    template: Optional[str] = None
    adjustments: List[Dict[str, Any]] = field(default_factory=list)
    parent_version: Optional[str] = None
    change_summary: str = ""
    
    # Checksum information
    checksum: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "version_id": self.version_id,
            "format": self.format.value,
            "file_path": self.file_path,
            "file_size": self.file_size,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "template": self.template,
            "adjustments": self.adjustments,
            "parent_version": self.parent_version,
            "change_summary": self.change_summary,
            "checksum": self.checksum
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentVersion":
        """
        Create version from dictionary
        
        Args:
            data: Version data dictionary
            
        Returns:
            DocumentVersion instance
            
        Raises:
            ValidationError: Field validation failed
        """
        # Validate required fields
        required_fields = ["version_id", "format", "file_path", "file_size", "created_at", "created_by"]
        for field_name in required_fields:
            if field_name not in data:
                raise ValidationError(f"Missing required field: {field_name}")
        
        # Parse format
        try:
            format = DocumentFormat(data["format"])
        except ValueError as e:
            raise ValidationError(f"Invalid format value: {data['format']}") from e
        
        # Parse created_at
        try:
            created_at = datetime.fromisoformat(data["created_at"])
        except ValueError as e:
            raise ValidationError(f"Invalid created_at format: {data['created_at']}") from e
        
        return cls(
            version_id=data["version_id"],
            format=format,
            file_path=data["file_path"],
            file_size=data["file_size"],
            created_at=created_at,
            created_by=data["created_by"],
            template=data.get("template"),
            adjustments=data.get("adjustments", []),
            parent_version=data.get("parent_version"),
            change_summary=data.get("change_summary", ""),
            checksum=data.get("checksum")
        )


# Export list
__all__ = [
    "ValidationError",
    "DocumentFormat",
    "GenerationAction",
    "DocumentGenerationRequest",
    "DocumentGenerationResult",
    "DocumentVersion",
]
