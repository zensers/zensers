# -*- coding: utf-8 -*-
"""
SectionLocator - 章节定位器

Phase 8: 报告修订闭环

在文档中定位指定章节，支持多种定位方式：
1. 通过 section_id 精确定位
2. 通过 section_title 模糊匹配
3. 通过关键词搜索

设计文档: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/PHASE8_DEVELOPMENT_PLAN.md
"""

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 路径安全常量
DANGEROUS_PATH_PATTERNS = [
    '../', '..\\',  # 路径遍历
    '/etc/', '/root/', '/home/',  # Linux 系统目录
    '\\Windows\\', '\\Program Files\\',  # Windows 系统目录
]

# 允许的文档格式
ALLOWED_EXTENSIONS = {'.md', '.html', '.docx', '.txt'}


class SectionLocatorError(Exception):
    """章节定位器异常基类"""
    pass


class DocumentNotFoundError(SectionLocatorError):
    """文档未找到"""
    pass


class UnsupportedFormatError(SectionLocatorError):
    """不支持的文档格式"""
    pass


class DocumentParseError(SectionLocatorError):
    """文档解析错误"""
    pass


@dataclass
class CachedIndex:
    """缓存索引项"""
    index: Dict[str, "SectionLocation"]
    mtime: float  # 文件修改时间
    size: int     # 文件大小


@dataclass
class SectionLocation:
    """
    章节位置信息
    
    Attributes:
        section_id: 章节唯一标识
        section_title: 章节标题
        start_index: 起始位置（字符索引）
        end_index: 结束位置
        content: 章节内容
        level: 章节层级（1=章，2=节，3=小节）
        parent_id: 父章节ID
        metadata: 额外元数据
    """
    section_id: str
    section_title: str
    start_index: int
    end_index: int
    content: str
    level: int
    parent_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "section_id": self.section_id,
            "section_title": self.section_title,
            "start_index": self.start_index,
            "end_index": self.end_index,
            "content_length": len(self.content),
            "level": self.level,
            "parent_id": self.parent_id,
            "metadata": self.metadata,
        }
    
    @property
    def length(self) -> int:
        """章节长度"""
        return self.end_index - self.start_index


class SectionLocator:
    """
    章节定位器
    
    在文档中定位指定章节，支持多种定位方式。
    
    使用示例:
        locator = SectionLocator()
        
        # 通过标题定位
        location = locator.locate(
            document_path="/path/to/report.docx",
            section_title="市场分析"
        )
        
        # 通过ID定位
        location = locator.locate(
            document_path="/path/to/report.docx",
            section_id="section_3"
        )
        
        # 列出所有章节
        sections = locator.list_sections(document_path)
    """
    
    def __init__(self, cache_enabled: bool = True, allowed_dirs: Optional[List[str]] = None):
        """
        初始化章节定位器
        
        Args:
            cache_enabled: 是否启用缓存
            allowed_dirs: 允许访问的目录列表（安全限制）
        """
        self._cache_enabled = cache_enabled
        self._index_cache: Dict[str, CachedIndex] = {}  # 改为 CachedIndex
        self._allowed_dirs = allowed_dirs
        
        logger.info("SectionLocator initialized")
    
    def _validate_path(self, document_path: str) -> bool:
        """
        验证文档路径是否安全
        
        Args:
            document_path: 文档路径
            
        Returns:
            是否安全
        """
        # 1. 检查危险路径模式
        for pattern in DANGEROUS_PATH_PATTERNS:
            if pattern.lower() in document_path.lower():
                logger.warning(f"Path contains dangerous pattern: {pattern}")
                return False
        
        # 2. 检查文件扩展名
        ext = Path(document_path).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            logger.warning(f"Disallowed file extension: {ext}")
            return False
        
        # 3. 如果设置了允许目录，检查路径是否在其中
        if self._allowed_dirs:
            try:
                real_path = os.path.realpath(document_path)
                for allowed_dir in self._allowed_dirs:
                    allowed_real = os.path.realpath(allowed_dir)
                    if real_path.startswith(allowed_real):
                        return True
                logger.warning(f"Path not in allowed directories: {document_path}")
                return False
            except Exception as e:
                logger.error(f"Path validation error: {e}")
                return False
        
        return True
    
    def _get_file_signature(self, document_path: str) -> Tuple[float, int]:
        """获取文件签名（修改时间和大小）"""
        stat = os.stat(document_path)
        return (stat.st_mtime, stat.st_size)
    
    def locate(
        self,
        document_path: str,
        section_id: Optional[str] = None,
        section_title: Optional[str] = None,
        keywords: Optional[List[str]] = None,
    ) -> Optional[SectionLocation]:
        """
        定位章节
        
        优先级: section_id > section_title > keywords
        
        Args:
            document_path: 文档路径
            section_id: 章节ID（精确匹配）
            section_title: 章节标题（模糊匹配）
            keywords: 关键词列表（搜索匹配）
            
        Returns:
            SectionLocation 或 None
        """
        # 1. 加载或构建索引
        index = self._get_or_build_index(document_path)
        
        if not index:
            logger.warning(f"No sections found in: {document_path}")
            return None
        
        # 2. 精确匹配（优先级最高）
        if section_id and section_id in index:
            logger.debug(f"Located section by ID: {section_id}")
            return index[section_id]
        
        # 3. 标题模糊匹配
        if section_title:
            for loc in index.values():
                if self._fuzzy_match(loc.section_title, section_title):
                    logger.debug(f"Located section by title: {section_title} -> {loc.section_id}")
                    return loc
        
        # 4. 关键词搜索
        if keywords:
            result = self._search_by_keywords(index, keywords)
            if result:
                logger.debug(f"Located section by keywords: {keywords} -> {result.section_id}")
                return result
        
        logger.warning(f"Section not found: id={section_id}, title={section_title}")
        return None
    
    def list_sections(
        self,
        document_path: str,
        level: Optional[int] = None,
    ) -> List[SectionLocation]:
        """
        列出所有章节
        
        Args:
            document_path: 文档路径
            level: 过滤指定层级（可选）
            
        Returns:
            章节列表（按位置排序）
        """
        index = self._get_or_build_index(document_path)
        sections = list(index.values())
        
        if level is not None:
            sections = [s for s in sections if s.level == level]
        
        return sorted(sections, key=lambda s: s.start_index)
    
    def get_section_tree(
        self,
        document_path: str,
    ) -> Dict[str, Any]:
        """
        获取章节树结构
        
        Returns:
            嵌套的章节树
        """
        sections = self.list_sections(document_path)
        
        # 构建树结构
        tree: Dict[str, Any] = {"root": []}
        
        for section in sections:
            node = {
                "section_id": section.section_id,
                "section_title": section.section_title,
                "level": section.level,
                "children": [],
            }
            
            if section.parent_id and section.parent_id in tree:
                tree[section.parent_id].append(node)
            else:
                tree["root"].append(node)
            
            # 为子章节预留位置
            tree[section.section_id] = node["children"]
        
        return tree["root"]
    
    def clear_cache(self, document_path: Optional[str] = None) -> None:
        """
        清除缓存
        
        Args:
            document_path: 指定文档路径，None则清除全部
        """
        if document_path:
            self._index_cache.pop(document_path, None)
        else:
            self._index_cache.clear()
        
        logger.debug(f"Cache cleared: {document_path or 'all'}")
    
    # ==================== 内部方法 ====================
    
    def _get_or_build_index(self, document_path: str) -> Dict[str, "SectionLocation"]:
        """获取或构建章节索引（带缓存一致性检查）"""
        if self._cache_enabled and document_path in self._index_cache:
            cached = self._index_cache[document_path]
            # 检查文件是否被修改
            try:
                current_mtime, current_size = self._get_file_signature(document_path)
                if cached.mtime == current_mtime and cached.size == current_size:
                    return cached.index
                else:
                    logger.debug(f"Cache invalidated for {document_path} (file modified)")
            except OSError:
                pass  # 文件可能已删除，继续重新构建
        
        index = self._build_index(document_path)
        
        if self._cache_enabled and index:
            try:
                mtime, size = self._get_file_signature(document_path)
                self._index_cache[document_path] = CachedIndex(index, mtime, size)
            except OSError:
                pass  # 忽略缓存失败
        
        return index
    
    def _build_index(self, document_path: str) -> Dict[str, SectionLocation]:
        """
        构建章节索引
        
        根据文件类型选择解析器
        
        Raises:
            DocumentNotFoundError: 文档不存在
            UnsupportedFormatError: 不支持的格式
            DocumentParseError: 解析失败
        """
        # 路径安全验证
        if not self._validate_path(document_path):
            logger.error(f"Path validation failed: {document_path}")
            raise DocumentParseError(f"Path validation failed: {document_path}")
        
        path = Path(document_path)
        
        if not path.exists():
            logger.error(f"Document not found: {document_path}")
            return {}  # 返回空字典，调用方可以处理
        
        suffix = path.suffix.lower()
        
        if suffix == '.docx':
            return self._parse_docx(document_path)
        elif suffix == '.html':
            return self._parse_html(document_path)
        elif suffix == '.md':
            return self._parse_markdown(document_path)
        else:
            logger.warning(f"Unsupported format: {suffix}")
            return {}
    
    def _parse_docx(self, document_path: str) -> Dict[str, SectionLocation]:
        """
        解析 Word 文档结构
        
        使用 python-docx 解析文档，识别标题样式
        """
        try:
            from docx import Document
        except ImportError:
            logger.warning("python-docx not installed, using fallback parser")
            return self._parse_docx_fallback(document_path)
        
        index: Dict[str, SectionLocation] = {}
        document = Document(document_path)
        
        # 获取所有段落
        paragraphs = list(document.paragraphs)
        
        # 识别标题段落
        section_counter = 0
        current_section: Optional[SectionLocation] = None
        content_start = 0
        
        # 构建全文内容用于计算位置
        full_text = "\n".join(p.text for p in paragraphs)
        
        for i, para in enumerate(paragraphs):
            text = para.text.strip()
            if not text:
                continue
            
            # 检查是否为标题（通过样式）
            style_name = para.style.name.lower() if para.style else ""
            is_heading = any(h in style_name for h in ['heading', '标题', 'title'])
            
            # 检查标题级别
            level = 0
            if 'heading 1' in style_name or '标题 1' in style_name:
                level = 1
            elif 'heading 2' in style_name or '标题 2' in style_name:
                level = 2
            elif 'heading 3' in style_name or '标题 3' in style_name:
                level = 3
            elif is_heading:
                level = 2  # 默认为二级标题
            
            if level > 0:
                # 保存上一个章节
                if current_section:
                    current_section.end_index = full_text.find(text) - 1
                    current_section.content = full_text[current_section.start_index:current_section.end_index]
                
                # 创建新章节
                section_counter += 1
                section_id = f"section_{section_counter}"
                start_idx = full_text.find(text)
                
                current_section = SectionLocation(
                    section_id=section_id,
                    section_title=text,
                    start_index=start_idx,
                    end_index=start_idx + len(text),  # 临时值
                    content="",  # 后续填充
                    level=level,
                    parent_id=None,
                )
                
                index[section_id] = current_section
        
        # 处理最后一个章节
        if current_section:
            current_section.end_index = len(full_text)
            current_section.content = full_text[current_section.start_index:]
        
        # 设置父子关系
        self._build_parent_relationships(index)
        
        logger.info(f"Parsed {len(index)} sections from Word document")
        return index
    
    def _parse_docx_fallback(self, document_path: str) -> Dict[str, SectionLocation]:
        """
        Word 文档解析降级方案
        
        使用正则表达式识别标题
        """
        index: Dict[str, SectionLocation] = {}
        
        # 读取文档内容（简化版）
        try:
            import zipfile
            with zipfile.ZipFile(document_path, 'r') as zf:
                xml_content = zf.read('word/document.xml').decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to read docx: {e}")
            return {}
        
        # 使用正则提取标题
        title_pattern = r'<w:t[^>]*>([^<]+)</w:t>'
        titles = re.findall(title_pattern, xml_content)
        
        section_counter = 0
        for title in titles:
            title = title.strip()
            if title and len(title) < 100:  # 标题通常较短
                section_counter += 1
                section_id = f"section_{section_counter}"
                
                index[section_id] = SectionLocation(
                    section_id=section_id,
                    section_title=title,
                    start_index=0,
                    end_index=0,
                    content="",
                    level=2,
                )
        
        logger.info(f"Parsed {len(index)} sections (fallback)")
        return index
    
    def _parse_html(self, document_path: str) -> Dict[str, SectionLocation]:
        """
        解析 HTML 文档结构
        
        识别 h1, h2, h3 等标题标签
        """
        index: Dict[str, SectionLocation] = {}
        
        try:
            with open(document_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            logger.error(f"Failed to read HTML: {e}")
            return {}
        
        # 使用正则提取标题
        heading_pattern = r'<h([1-6])[^>]*>([^<]+)</h\1>'
        matches = re.finditer(heading_pattern, content, re.IGNORECASE)
        
        section_counter = 0
        for match in matches:
            level = int(match.group(1))
            title = match.group(2).strip()
            
            if title:
                section_counter += 1
                section_id = f"section_{section_counter}"
                
                index[section_id] = SectionLocation(
                    section_id=section_id,
                    section_title=title,
                    start_index=match.start(),
                    end_index=match.end(),
                    content=title,  # 简化处理
                    level=level,
                )
        
        self._build_parent_relationships(index)
        
        logger.info(f"Parsed {len(index)} sections from HTML")
        return index
    
    def _parse_markdown(self, document_path: str) -> Dict[str, SectionLocation]:
        """
        解析 Markdown 文档结构
        
        识别 # ## ### 等标题
        """
        index: Dict[str, SectionLocation] = {}
        
        try:
            with open(document_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except Exception as e:
            logger.error(f"Failed to read Markdown: {e}")
            return {}
        
        section_counter = 0
        full_content = "".join(lines)
        
        # First pass: identify all headings
        heading_positions = []
        current_pos = 0
        
        for i, line in enumerate(lines):
            match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if match:
                level = len(match.group(1))
                title = match.group(2).strip()
                heading_positions.append({
                    'level': level,
                    'title': title,
                    'start': current_pos,
                    'line_index': i,
                })
            current_pos += len(line)
        
        # Second pass: build sections with content
        for i, heading in enumerate(heading_positions):
            section_counter += 1
            section_id = f"section_{section_counter}"
            
            # Calculate content end position (next heading or end of file)
            if i + 1 < len(heading_positions):
                end_pos = heading_positions[i + 1]['start']
            else:
                end_pos = len(full_content)
            
            # Extract section content
            section_content = full_content[heading['start']:end_pos].strip()
            
            index[section_id] = SectionLocation(
                section_id=section_id,
                section_title=heading['title'],
                start_index=heading['start'],
                end_index=end_pos,
                content=section_content,
                level=heading['level'],
            )
        
        self._build_parent_relationships(index)
        
        logger.info(f"Parsed {len(index)} sections from Markdown")
        return index
    
    def _build_parent_relationships(
        self,
        index: Dict[str, SectionLocation],
    ) -> None:
        """构建父子关系"""
        sections = sorted(index.values(), key=lambda s: s.start_index)
        
        for i, section in enumerate(sections):
            # 查找最近的更高层级章节作为父节点
            for j in range(i - 1, -1, -1):
                if sections[j].level < section.level:
                    section.parent_id = sections[j].section_id
                    break
    
    def _fuzzy_match(
        self,
        text1: str,
        text2: str,
        threshold: float = 0.6,
    ) -> bool:
        """
        模糊匹配
        
        Args:
            text1: 文本1
            text2: 文本2
            threshold: 相似度阈值
            
        Returns:
            是否匹配
        """
        # 简化处理：包含关系
        t1 = text1.lower().strip()
        t2 = text2.lower().strip()
        
        # 完全包含
        if t2 in t1 or t1 in t2:
            return True
        
        # 计算相似度（简化版）
        common = len(set(t1) & set(t2))
        max_len = max(len(t1), len(t2))
        
        if max_len == 0:
            return False
        
        similarity = common / max_len
        return similarity >= threshold
    
    def _search_by_keywords(
        self,
        index: Dict[str, SectionLocation],
        keywords: List[str],
    ) -> Optional[SectionLocation]:
        """
        通过关键词搜索章节
        
        Args:
            index: 章节索引
            keywords: 关键词列表
            
        Returns:
            最佳匹配的章节
        """
        best_match: Optional[SectionLocation] = None
        best_score = 0
        
        for section in index.values():
            # 计算关键词匹配分数
            score = 0
            content_lower = section.content.lower()
            title_lower = section.section_title.lower()
            
            for keyword in keywords:
                keyword_lower = keyword.lower()
                
                # 标题匹配权重更高
                if keyword_lower in title_lower:
                    score += 2
                elif keyword_lower in content_lower:
                    score += 1
            
            if score > best_score:
                best_score = score
                best_match = section
        
        return best_match


__all__ = [
    "SectionLocator",
    "SectionLocation",
    "SectionLocatorError",
    "DocumentNotFoundError",
    "UnsupportedFormatError",
    "DocumentParseError",
    "CachedIndex",
]
