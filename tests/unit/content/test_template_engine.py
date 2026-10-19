# -*- coding: utf-8 -*-
"""
TemplateEngine 测试
===================

测试模板引擎功能：
1. 模板加载
2. 样式应用
3. 变量渲染
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any


class TestTemplateEngineInit:
    """测试 TemplateEngine 初始化"""
    
    @pytest.fixture
    def temp_templates(self):
        """创建临时模板目录"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    def test_engine_initialization(self, temp_templates):
        """测试引擎初始化"""
        from src.content.template_engine import TemplateEngine
        
        engine = TemplateEngine(templates_dir=temp_templates)
        
        assert engine is not None
        assert engine.templates_dir == Path(temp_templates)
    
    def test_engine_default_templates_dir(self):
        """测试默认模板目录"""
        from src.content.template_engine import TemplateEngine
        
        engine = TemplateEngine()
        
        assert engine.templates_dir is not None


class TestTemplateEngineApply:
    """测试模板应用"""
    
    @pytest.fixture
    def temp_templates(self):
        """创建临时模板目录"""
        temp_dir = tempfile.mkdtemp()
        templates_dir = Path(temp_dir) / "templates"
        templates_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建简单模板
        template_content = '''
<!DOCTYPE html>
<html>
<head>
    <title>{{ title }}</title>
    <style>
        body { font-family: {{ font_family }}; }
        h1 { color: {{ primary_color }}; }
    </style>
</head>
<body>
    {{ content }}
</body>
</html>
'''
        (templates_dir / "standard.html").write_text(template_content, encoding="utf-8")
        
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def engine(self, temp_templates):
        """创建引擎实例"""
        from src.content.template_engine import TemplateEngine
        return TemplateEngine(templates_dir=temp_templates)
    
    def test_apply_template(self, engine, temp_templates):
        """测试应用模板"""
        html_content = "<article><h1>测试报告</h1></article>"
        template_name = "standard"
        variables = {
            "title": "测试报告",
            "font_family": "Arial",
            "primary_color": "#333333",
            "content": html_content
        }
        
        result = engine.apply_template(
            html_content=html_content,
            template_name=template_name,
            variables=variables
        )
        
        assert result is not None
        assert "测试报告" in result
    
    def test_apply_with_missing_template(self, engine):
        """测试模板不存在"""
        html_content = "<article><h1>测试</h1></article>"
        
        # 不存在的模板应返回原始内容或使用默认
        result = engine.apply_template(
            html_content=html_content,
            template_name="nonexistent"
        )
        
        assert result is not None
    
    def test_apply_preserves_content(self, engine, temp_templates):
        """测试保留原始内容"""
        html_content = "<article><h1>重要内容</h1><p>这是关键段落</p></article>"
        
        result = engine.apply_template(
            html_content=html_content,
            template_name="standard",
            variables={"content": html_content}
        )
        
        assert "重要内容" in result
        assert "关键段落" in result


class TestTemplateEngineStyles:
    """测试样式处理"""
    
    @pytest.fixture
    def engine(self):
        from src.content.template_engine import TemplateEngine
        return TemplateEngine()
    
    def test_get_default_styles(self, engine):
        """测试获取默认样式"""
        styles = engine.get_default_styles()
        
        assert styles is not None
        assert "colors" in styles or "fonts" in styles
    
    def test_apply_inline_styles(self, engine):
        """测试内联样式应用"""
        html_content = "<article><h1>标题</h1></article>"
        styles = {
            "primary_color": "#1A2744",
            "font_family": "Georgia"
        }
        
        result = engine.apply_inline_styles(html_content, styles)
        
        assert result is not None
    
    def test_merge_styles(self, engine):
        """测试合并样式"""
        base_styles = {"color": "blue", "font": "Arial"}
        custom_styles = {"color": "red", "size": "12px"}
        
        merged = engine.merge_styles(base_styles, custom_styles)
        
        assert merged["color"] == "red"  # 自定义覆盖
        assert merged["font"] == "Arial"  # 保留基础
        assert merged["size"] == "12px"  # 新增


class TestTemplateEngineVariables:
    """测试变量处理"""
    
    @pytest.fixture
    def engine(self):
        from src.content.template_engine import TemplateEngine
        return TemplateEngine()
    
    def test_render_variables(self, engine):
        """测试渲染变量"""
        template = "<h1>{{ title }}</h1><p>{{ description }}</p>"
        variables = {
            "title": "测试标题",
            "description": "测试描述"
        }
        
        result = engine.render_variables(template, variables)
        
        assert "测试标题" in result
        assert "测试描述" in result
        assert "{{ title }}" not in result
    
    def test_render_missing_variable(self, engine):
        """测试缺失变量"""
        template = "<h1>{{ title }}</h1><p>{{ missing }}</p>"
        variables = {"title": "标题"}
        
        result = engine.render_variables(template, variables)
        
        assert "标题" in result
        # 缺失变量应保持原样或使用默认
        assert result is not None
    
    def test_render_nested_variables(self, engine):
        """测试嵌套变量"""
        template = "<div class='{{ style.class }}'>{{ content }}</div>"
        variables = {
            "style": {"class": "container"},
            "content": "内容"
        }
        
        result = engine.render_variables(template, variables)
        
        assert result is not None


class TestTemplateEngineFormats:
    """测试格式适配"""
    
    @pytest.fixture
    def engine(self):
        from src.content.template_engine import TemplateEngine
        return TemplateEngine()
    
    def test_get_format_template(self, engine):
        """测试获取格式模板"""
        docx_template = engine.get_format_template("docx")
        pptx_template = engine.get_format_template("pptx")
        
        assert docx_template is not None
        assert pptx_template is not None
    
    def test_format_specific_styles(self, engine):
        """测试格式特定样式"""
        docx_styles = engine.get_format_styles("docx")
        pptx_styles = engine.get_format_styles("pptx")
        
        # Word和PPT应有不同样式
        assert docx_styles is not None
        assert pptx_styles is not None


class TestTemplateEngineIntegration:
    """测试集成场景"""
    
    @pytest.fixture
    def temp_templates(self):
        """创建临时模板目录"""
        temp_dir = tempfile.mkdtemp()
        templates_dir = Path(temp_dir) / "templates"
        templates_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建完整模板
        template_content = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{{ title }}</title>
    <style>
        body { font-family: {{ fonts.body }}; color: {{ colors.text }}; }
        h1 { color: {{ colors.primary }}; }
        h2 { color: {{ colors.secondary }}; }
        .slide { background: {{ colors.background }}; }
    </style>
</head>
<body>
    {{ content }}
</body>
</html>
'''
        (templates_dir / "consulting.html").write_text(template_content, encoding="utf-8")
        
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def engine(self, temp_templates):
        from src.content.template_engine import TemplateEngine
        return TemplateEngine(templates_dir=temp_templates)
    
    def test_full_workflow(self, engine, temp_templates):
        """测试完整工作流"""
        from src.content.content_orchestrator import ContentOrchestrator
        
        # 1. 生成HTML
        orchestrator = ContentOrchestrator()
        html = orchestrator.transform_to_html(
            research_result={
                "title": "新能源汽车市场研究",
                "sections": [
                    {"id": "s1", "title": "市场规模", "content": "分析内容"}
                ]
            },
            output_format="docx"
        )
        
        # 2. 应用模板
        result = engine.apply_template(
            html_content=html,
            template_name="consulting",
            variables={
                "title": "新能源汽车市场研究",
                "content": html,
                "fonts": {"body": "Arial"},
                "colors": {
                    "primary": "#1A2744",
                    "secondary": "#2C3E50",
                    "text": "#333",
                    "background": "#fff"
                }
            }
        )
        
        assert result is not None
        assert "新能源汽车市场研究" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])