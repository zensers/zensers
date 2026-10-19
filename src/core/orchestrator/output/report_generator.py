"""
报告生成器

职责：
- 生成研究报告
- 支持多种格式（Markdown, DOCX, PDF）
- 模板化输出

设计文档: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/ORCHESTRATOR_REDESIGN.md
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ReportFormat(Enum):
    """报告格式"""
    MARKDOWN = "markdown"
    DOCX = "docx"
    PDF = "pdf"
    HTML = "html"


@dataclass
class ReportSection:
    """
    报告章节
    
    Attributes:
        title: 章节标题
        content: 章节内容
        level: 标题级别（1-6）
        subsections: 子章节列表
        metadata: 元数据
    """
    title: str
    content: str = ""
    level: int = 1
    subsections: List["ReportSection"] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_subsection(self, section: "ReportSection") -> None:
        """添加子章节"""
        section.level = self.level + 1
        self.subsections.append(section)


@dataclass
class ReportConfig:
    """报告配置"""
    format: ReportFormat = ReportFormat.MARKDOWN
    title: str = "研究报告"
    author: str = "AI Research Assistant"
    include_toc: bool = True          # 目录
    include_summary: bool = True      # 摘要
    include_references: bool = True   # 参考文献
    template_path: Optional[Path] = None


@dataclass
class ReportResult:
    """
    报告结果
    
    Attributes:
        content: 报告内容
        format: 报告格式
        path: 保存路径（如果已保存）
        sections: 章节列表
        generated_at: 生成时间
        stats: 统计信息
    """
    content: str
    format: ReportFormat
    path: Optional[Path] = None
    sections: List[ReportSection] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)
    stats: Dict[str, Any] = field(default_factory=dict)


class ReportGenerator:
    """
    报告生成器
    
    职责：
    - 生成研究报告
    - 支持多种格式
    - 模板化输出
    
    使用示例:
        generator = ReportGenerator(ReportConfig())
        
        # 添加章节
        generator.add_section("市场规模", "2024年市场规模达到...")
        generator.add_section("竞争格局", "主要竞争者包括...")
        
        # 生成报告
        result = generator.generate(topic="新能源汽车市场")
        
        # 保存报告
        generator.save(result, Path("output/report.md"))
    """
    
    def __init__(self, config: Optional[ReportConfig] = None):
        self.config = config or ReportConfig()
        
        # 章节列表
        self._sections: List[ReportSection] = []
        
        # 元数据
        self._metadata: Dict[str, Any] = {}
        
        # 统计
        self._total_generated = 0
    
    def add_section(
        self,
        title: str,
        content: str = "",
        level: int = 1,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ReportSection:
        """
        添加章节
        
        Args:
            title: 章节标题
            content: 章节内容
            level: 标题级别
            metadata: 元数据
            
        Returns:
            添加的章节
        """
        section = ReportSection(
            title=title,
            content=content,
            level=level,
            metadata=metadata or {},
        )
        self._sections.append(section)
        
        logger.debug(f"Added section: {title}")
        
        return section
    
    def set_metadata(self, key: str, value: Any) -> None:
        """设置元数据"""
        self._metadata[key] = value
    
    def generate(
        self,
        topic: str,
        summary: Optional[str] = None,
        references: Optional[List[str]] = None,
    ) -> ReportResult:
        """
        生成报告
        
        Args:
            topic: 研究主题
            summary: 摘要
            references: 参考文献
            
        Returns:
            ReportResult: 报告结果
        """
        self._total_generated += 1
        
        # 根据格式生成内容
        if self.config.format == ReportFormat.MARKDOWN:
            content = self._generate_markdown(topic, summary, references)
        elif self.config.format == ReportFormat.HTML:
            content = self._generate_html(topic, summary, references)
        elif self.config.format == ReportFormat.DOCX:
            content = self._generate_markdown(topic, summary, references)
            # DOCX 生成由 DocumentGenerator 处理
        elif self.config.format == ReportFormat.PDF:
            content = self._generate_markdown(topic, summary, references)
            # PDF 生成由 DocumentGenerator 处理
        else:
            content = self._generate_markdown(topic, summary, references)
        
        # 统计信息
        stats = {
            "total_sections": len(self._sections),
            "total_words": len(content.split()),
            "format": self.config.format.value,
        }
        
        # 保存结果副本（因为clear()会清空_sections）
        sections_copy = list(self._sections)
        
        # 生成完成后清理，防止内存累积
        self.clear()
        
        return ReportResult(
            content=content,
            format=self.config.format,
            sections=sections_copy,
            stats=stats,
        )
    
    def _generate_markdown(
        self,
        topic: str,
        summary: Optional[str],
        references: Optional[List[str]],
    ) -> str:
        """生成 Markdown 格式报告"""
        lines = []
        
        # 标题
        lines.append(f"# {self.config.title}")
        lines.append("")
        lines.append(f"**主题**: {topic}")
        lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"**作者**: {self.config.author}")
        lines.append("")
        
        # 目录
        if self.config.include_toc and self._sections:
            lines.append("## 目录")
            lines.append("")
            for section in self._sections:
                indent = "  " * (section.level - 1)
                anchor = section.title.lower().replace(" ", "-")
                lines.append(f"{indent}- [{section.title}](#{anchor})")
            lines.append("")
        
        # 摘要
        if self.config.include_summary and summary:
            lines.append("## 摘要")
            lines.append("")
            lines.append(summary)
            lines.append("")
        
        # 章节内容
        for section in self._sections:
            self._render_section_markdown(lines, section)
        
        # 参考文献
        if self.config.include_references and references:
            lines.append("## 参考文献")
            lines.append("")
            for i, ref in enumerate(references, 1):
                lines.append(f"{i}. {ref}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _render_section_markdown(
        self,
        lines: List[str],
        section: ReportSection,
    ) -> None:
        """渲染章节为 Markdown"""
        # 标题
        heading = "#" * section.level
        lines.append(f"{heading} {section.title}")
        lines.append("")
        
        # 内容
        if section.content:
            lines.append(section.content)
            lines.append("")
        
        # 子章节
        for subsection in section.subsections:
            self._render_section_markdown(lines, subsection)
    
    def _generate_html(
        self,
        topic: str,
        summary: Optional[str],
        references: Optional[List[str]],
    ) -> str:
        """生成 HTML 格式报告"""
        lines = []
        
        # HTML 头部
        lines.append("<!DOCTYPE html>")
        lines.append("<html lang='zh-CN'>")
        lines.append("<head>")
        lines.append(f"<title>{self.config.title}</title>")
        lines.append("<meta charset='UTF-8'>")
        lines.append("<style>")
        lines.append("body { font-family: Arial, sans-serif; margin: 40px; }")
        lines.append("h1 { color: #333; }")
        lines.append("h2 { color: #555; border-bottom: 1px solid #ddd; }")
        lines.append("</style>")
        lines.append("</head>")
        lines.append("<body>")
        
        # 标题
        lines.append(f"<h1>{self.config.title}</h1>")
        lines.append(f"<p><strong>主题</strong>: {topic}</p>")
        lines.append(f"<p><strong>生成时间</strong>: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>")
        
        # 摘要
        if summary:
            lines.append("<h2>摘要</h2>")
            lines.append(f"<p>{summary}</p>")
        
        # 章节内容
        for section in self._sections:
            self._render_section_html(lines, section)
        
        # 参考文献
        if references:
            lines.append("<h2>参考文献</h2>")
            lines.append("<ol>")
            for ref in references:
                lines.append(f"<li>{ref}</li>")
            lines.append("</ol>")
        
        # HTML 尾部
        lines.append("</body>")
        lines.append("</html>")
        
        return "\n".join(lines)
    
    def _render_section_html(
        self,
        lines: List[str],
        section: ReportSection,
    ) -> None:
        """渲染章节为 HTML"""
        tag = f"h{section.level + 1}"
        lines.append(f"<{tag}>{section.title}</{tag}>")
        
        if section.content:
            lines.append(f"<p>{section.content}</p>")
        
        for subsection in section.subsections:
            self._render_section_html(lines, subsection)
    
    def save(
        self,
        result: ReportResult,
        path: Path,
    ) -> bool:
        """
        保存报告
        
        Args:
            result: 报告结果
            path: 保存路径
            
        Returns:
            是否成功保存
        """
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(path, "w", encoding="utf-8") as f:
                f.write(result.content)
            
            result.path = path
            
            logger.info(f"Report saved to {path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save report: {e}")
            return False
    
    def clear(self) -> None:
        """清空章节"""
        self._sections.clear()
        self._metadata.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_generated": self._total_generated,
            "current_sections": len(self._sections),
        }
