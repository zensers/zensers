# -*- coding: utf-8 -*-
"""
SectionLocator 和 ContentApplier 单元测试

Phase 8: 报告修订闭环
"""

import os
import tempfile
import pytest
from pathlib import Path

from src.core.adjustment.section_locator import SectionLocator, SectionLocation
from src.core.adjustment.content_applier import ContentApplier, ApplyResult


# ===== SectionLocator 测试 =====

class TestSectionLocation:
    """SectionLocation 数据类测试"""
    
    def test_creation(self):
        """测试创建"""
        loc = SectionLocation(
            section_id="section_1",
            section_title="市场分析",
            start_index=0,
            end_index=100,
            content="市场分析内容",
            level=2,
        )
        
        assert loc.section_id == "section_1"
        assert loc.section_title == "市场分析"
        assert loc.level == 2
        assert loc.parent_id is None
    
    def test_length(self):
        """测试长度计算"""
        loc = SectionLocation(
            section_id="s1",
            section_title="Test",
            start_index=10,
            end_index=110,
            content="x" * 100,
            level=1,
        )
        
        assert loc.length == 100
    
    def test_to_dict(self):
        """测试序列化"""
        loc = SectionLocation(
            section_id="s1",
            section_title="Test",
            start_index=0,
            end_index=10,
            content="test",
            level=1,
        )
        
        data = loc.to_dict()
        
        assert data["section_id"] == "s1"
        assert data["section_title"] == "Test"
        assert data["level"] == 1
        assert "content_length" in data


class TestSectionLocator:
    """SectionLocator 测试"""
    
    @pytest.fixture
    def locator(self):
        """创建定位器"""
        return SectionLocator(cache_enabled=True)
    
    @pytest.fixture
    def markdown_file(self, tmp_path):
        """创建测试 Markdown 文件"""
        content = """# 新能源汽车行业研究

## 市场规模

2024年全球新能源汽车销量达到1800万辆。

## 竞争格局

### 头部企业

宁德时代和比亚迪占据主导地位。

### 新进入者

小米和华为等科技企业进入市场。

## 技术趋势

固态电池和智能驾驶是主要方向。

## 投资建议

建议关注产业链上游企业。
"""
        file_path = tmp_path / "test_report.md"
        file_path.write_text(content, encoding='utf-8')
        return str(file_path)
    
    @pytest.fixture
    def html_file(self, tmp_path):
        """创建测试 HTML 文件"""
        content = """<!DOCTYPE html>
<html>
<body>
<h1>新能源汽车行业研究</h1>
<h2>市场规模</h2>
<p>2024年全球新能源汽车销量达到1800万辆。</p>
<h2>竞争格局</h2>
<h3>头部企业</h3>
<p>宁德时代和比亚迪占据主导地位。</p>
<h3>新进入者</h3>
<p>小米和华为等科技企业进入市场。</p>
<h2>技术趋势</h2>
<p>固态电池和智能驾驶是主要方向。</p>
</body>
</html>
"""
        file_path = tmp_path / "test_report.html"
        file_path.write_text(content, encoding='utf-8')
        return str(file_path)
    
    # --- Markdown 解析测试 ---
    
    def test_parse_markdown(self, locator, markdown_file):
        """测试 Markdown 解析"""
        sections = locator.list_sections(markdown_file)
        
        assert len(sections) > 0
        # 应该识别出标题
        titles = [s.section_title for s in sections]
        assert "新能源汽车行业研究" in titles
        assert "市场规模" in titles
        assert "竞争格局" in titles
    
    def test_locate_by_title(self, locator, markdown_file):
        """测试通过标题定位"""
        location = locator.locate(
            markdown_file,
            section_title="市场规模",
        )
        
        assert location is not None
        assert "市场规模" in location.section_title
        assert location.level == 2
    
    def test_locate_by_id(self, locator, markdown_file):
        """测试通过ID定位"""
        # 先列出所有章节获取ID
        sections = locator.list_sections(markdown_file)
        assert len(sections) > 0
        
        section_id = sections[0].section_id
        
        # 通过ID定位
        location = locator.locate(
            markdown_file,
            section_id=section_id,
        )
        
        assert location is not None
        assert location.section_id == section_id
    
    def test_locate_fuzzy_match(self, locator, markdown_file):
        """测试模糊匹配"""
        # 使用部分标题
        location = locator.locate(
            markdown_file,
            section_title="竞争",
        )
        
        assert location is not None
        assert "竞争格局" in location.section_title
    
    def test_locate_by_keywords(self, locator, markdown_file):
        """测试关键词搜索"""
        location = locator.locate(
            markdown_file,
            keywords=["宁德时代", "比亚迪"],
        )
        
        assert location is not None
    
    def test_locate_not_found(self, locator, markdown_file):
        """测试未找到"""
        location = locator.locate(
            markdown_file,
            section_title="不存在的章节",
        )
        
        assert location is None
    
    def test_list_sections_by_level(self, locator, markdown_file):
        """测试按层级列出章节"""
        level1 = locator.list_sections(markdown_file, level=1)
        level2 = locator.list_sections(markdown_file, level=2)
        
        assert len(level1) >= 1  # 至少1个一级标题
        assert len(level2) >= 3  # 至少3个二级标题
    
    def test_section_tree(self, locator, markdown_file):
        """测试章节树"""
        tree = locator.get_section_tree(markdown_file)
        
        assert isinstance(tree, list)
        assert len(tree) > 0
    
    # --- HTML 解析测试 ---
    
    def test_parse_html(self, locator, html_file):
        """测试 HTML 解析"""
        sections = locator.list_sections(html_file)
        
        assert len(sections) > 0
        titles = [s.section_title for s in sections]
        assert "市场规模" in titles
    
    def test_locate_html_by_title(self, locator, html_file):
        """测试 HTML 标题定位"""
        location = locator.locate(
            html_file,
            section_title="竞争格局",
        )
        
        assert location is not None
        assert "竞争格局" in location.section_title
    
    # --- 缓存测试 ---
    
    def test_cache(self, locator, markdown_file):
        """测试缓存"""
        # 第一次调用
        sections1 = locator.list_sections(markdown_file)
        
        # 第二次调用（应该使用缓存）
        sections2 = locator.list_sections(markdown_file)
        
        assert len(sections1) == len(sections2)
    
    def test_clear_cache(self, locator, markdown_file):
        """测试清除缓存"""
        # 构建缓存
        locator.list_sections(markdown_file)
        assert len(locator._index_cache) > 0
        
        # 清除指定文件缓存
        locator.clear_cache(markdown_file)
        assert markdown_file not in locator._index_cache
    
    def test_clear_all_cache(self, locator, markdown_file):
        """测试清除全部缓存"""
        locator.list_sections(markdown_file)
        locator.clear_cache()
        assert len(locator._index_cache) == 0
    
    # --- 不存在文件测试 ---
    
    def test_nonexistent_file(self, locator):
        """测试不存在的文件"""
        sections = locator.list_sections("/nonexistent/file.docx")
        assert len(sections) == 0
    
    def test_unsupported_format(self, locator, tmp_path):
        """测试不支持的格式"""
        file_path = tmp_path / "test.txt"
        file_path.write_text("Hello", encoding='utf-8')
        
        sections = locator.list_sections(str(file_path))
        assert len(sections) == 0


# ===== ContentApplier 测试 =====

class TestApplyResult:
    """ApplyResult 数据类测试"""
    
    def test_success_result(self):
        """测试成功结果"""
        result = ApplyResult(
            success=True,
            new_document_path="/output/new.docx",
            backup_path="/backup/old.docx",
            changes={"section_id": "s1"},
        )
        
        assert result.success is True
        assert result.new_document_path is not None
    
    def test_failure_result(self):
        """测试失败结果"""
        result = ApplyResult(
            success=False,
            error="Section not found",
        )
        
        assert result.success is False
        assert result.error is not None
    
    def test_to_dict(self):
        """测试序列化"""
        result = ApplyResult(
            success=True,
            new_document_path="/output/new.docx",
            changes={"section_id": "s1"},
        )
        
        data = result.to_dict()
        assert data["success"] is True
        assert "changes" in data


class TestContentApplier:
    """ContentApplier 测试"""
    
    @pytest.fixture
    def applier(self, tmp_path):
        """创建应用器"""
        return ContentApplier(
            backup_dir=str(tmp_path / "backups"),
            create_backup=True,
        )
    
    @pytest.fixture
    def markdown_file(self, tmp_path):
        """创建测试 Markdown 文件"""
        content = """# 新能源汽车行业研究

## 市场规模

2024年全球新能源汽车销量达到1800万辆。
同比增长35%。

## 竞争格局

宁德时代和比亚迪占据主导地位。
"""
        file_path = tmp_path / "test_report.md"
        file_path.write_text(content, encoding='utf-8')
        return str(file_path)
    
    @pytest.fixture
    def section_location(self):
        """创建测试章节位置"""
        return SectionLocation(
            section_id="section_2",
            section_title="市场规模",
            start_index=20,
            end_index=80,
            content="2024年全球新能源汽车销量达到1800万辆。\n同比增长35%。",
            level=2,
        )
    
    def test_apply_markdown(self, applier, markdown_file, section_location):
        """测试 Markdown 内容应用"""
        result = applier.apply(
            document_path=markdown_file,
            location=section_location,
            new_content="2025年全球新能源汽车销量预计达到2500万辆。\n同比增长40%。",
        )
        
        assert result.success is True
        assert result.new_document_path is not None
        assert result.backup_path is not None
        assert "section_id" in result.changes
    
    def test_apply_creates_backup(self, applier, markdown_file, section_location):
        """测试备份创建"""
        result = applier.apply(
            document_path=markdown_file,
            location=section_location,
            new_content="新内容",
        )
        
        assert result.success is True
        assert result.backup_path is not None
        assert Path(result.backup_path).exists()
    
    def test_apply_nonexistent_file(self, applier, section_location):
        """测试不存在的文件"""
        result = applier.apply(
            document_path="/nonexistent/file.docx",
            location=section_location,
            new_content="新内容",
        )
        
        assert result.success is False
        assert "not found" in result.error.lower()
    
    def test_apply_empty_content(self, applier, markdown_file, section_location):
        """测试空内容"""
        result = applier.apply(
            document_path=markdown_file,
            location=section_location,
            new_content="",
        )
        
        assert result.success is False
        assert "empty" in result.error.lower()
    
    def test_apply_unsupported_format(self, applier, tmp_path, section_location):
        """测试不支持的格式"""
        file_path = tmp_path / "test.txt"
        file_path.write_text("Hello", encoding='utf-8')
        
        result = applier.apply(
            document_path=str(file_path),
            location=section_location,
            new_content="新内容",
        )
        
        assert result.success is False
        assert "unsupported" in result.error.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
