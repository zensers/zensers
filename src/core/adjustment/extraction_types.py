from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.content.content_orchestrator import ContentSection


@dataclass
class SectionSummary:
    title: str
    page_range: str
    content_preview: str = ""
    has_table: bool = False
    has_chart: bool = False


@dataclass
class ExtractionSummary:
    file_count: int
    total_pages: int
    format_types: List[str]
    title: Optional[str]
    sections: List[SectionSummary] = field(default_factory=list)
    tables_count: int = 0
    charts_count: int = 0
    key_topics: List[str] = field(default_factory=list)
    word_count: int = 0
    languages: List[str] = field(default_factory=list)
    extraction_status: str = "success"
    warnings: List[str] = field(default_factory=list)


@dataclass
class ExtractionResult:
    title: str
    sections: List[ContentSection]
    tables: List[List[List[str]]]
    key_topics: List[str]
    metadata: Dict[str, Any]
    summary: Optional[ExtractionSummary] = None


class DataParser(ABC):
    @abstractmethod
    def parse(self, file_path: str) -> ExtractionResult:
        ...
