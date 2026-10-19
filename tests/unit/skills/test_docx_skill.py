"""
DocxSkill 测试 - TDD模式
"""
import pytest
import tempfile
import os
from pathlib import Path


class TestDocxSkill:
    """测试 Word 文档生成 Skill"""

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as d:
            yield d

    @pytest.fixture
    def skill(self):
        from src.skills.docx_skill import DocxSkill
        from src.skills.base import SkillConfig
        return DocxSkill(SkillConfig(name="docx_skill", version="1.0.0"))

    @pytest.mark.asyncio
    async def test_create_document(self, skill, temp_dir):
        """测试创建空文档"""
        filepath = os.path.join(temp_dir, "test.docx")
        result = await skill.execute(action="create", filepath=filepath)
        assert result["success"] is True
        assert Path(filepath).exists()

    @pytest.mark.asyncio
    async def test_add_heading(self, skill, temp_dir):
        """测试添加标题"""
        filepath = os.path.join(temp_dir, "heading_test.docx")
        await skill.execute(action="create", filepath=filepath)
        result = await skill.execute(
            action="add_heading",
            filepath=filepath,
            text="新能源汽车市场分析",
            level=1
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_add_paragraph(self, skill, temp_dir):
        """测试添加段落"""
        filepath = os.path.join(temp_dir, "para_test.docx")
        await skill.execute(action="create", filepath=filepath)
        result = await skill.execute(
            action="add_paragraph",
            filepath=filepath,
            text="2024年中国新能源汽车销量突破900万辆，同比增长35%。"
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_add_table(self, skill, temp_dir):
        """测试添加表格"""
        filepath = os.path.join(temp_dir, "table_test.docx")
        await skill.execute(action="create", filepath=filepath)

        table_data = [
            ["品牌", "销量", "市占率"],
            ["比亚迪", "300万辆", "33%"],
            ["特斯拉", "180万辆", "20%"],
        ]
        result = await skill.execute(
            action="add_table",
            filepath=filepath,
            data=table_data
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_save_and_read_back(self, skill, temp_dir):
        """测试保存后文档可读取"""
        filepath = os.path.join(temp_dir, "save_test.docx")
        await skill.execute(action="create", filepath=filepath)
        await skill.execute(action="add_heading", filepath=filepath, text="测试标题", level=1)
        await skill.execute(action="add_paragraph", filepath=filepath, text="测试段落内容。")

        # 验证文件存在且有内容
        assert Path(filepath).exists()
        assert Path(filepath).stat().st_size > 0

    @pytest.mark.asyncio
    async def test_add_multiple_sections(self, skill, temp_dir):
        """测试添加多个章节"""
        filepath = os.path.join(temp_dir, "multi_section.docx")
        await skill.execute(action="create", filepath=filepath)

        sections = [
            {"heading": "市场概况", "content": "市场规模达4000亿元。"},
            {"heading": "竞争分析", "content": "主要竞争对手包括比亚迪、特斯拉。"},
            {"heading": "发展趋势", "content": "预计2025年市场规模将突破6000亿元。"},
        ]

        for section in sections:
            await skill.execute(action="add_heading", filepath=filepath, text=section["heading"], level=2)
            result = await skill.execute(action="add_paragraph", filepath=filepath, text=section["content"])
            assert result["success"] is True

        assert Path(filepath).stat().st_size > 0

    @pytest.mark.asyncio
    async def test_apply_styles(self, skill, temp_dir):
        """测试应用文档样式"""
        filepath = os.path.join(temp_dir, "styled.docx")
        result = await skill.execute(
            action="create",
            filepath=filepath,
            title="市场研究报告",
            author="AI Research"
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_unknown_action(self, skill, temp_dir):
        """测试未知操作"""
        result = await skill.execute(action="format_hard_drive", filepath="/tmp/x.docx")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_build_full_report(self, skill, temp_dir):
        """测试构建完整报告"""
        filepath = os.path.join(temp_dir, "full_report.docx")
        result = await skill.execute(
            action="build_report",
            filepath=filepath,
            title="新能源汽车市场分析报告",
            sections=[
                {"heading": "执行摘要", "level": 1, "content": "本报告分析了新能源汽车市场。"},
                {"heading": "市场规模", "level": 2, "content": "2024年市场规模4000亿元。"},
                {"heading": "数据表格", "level": 2, "table": [
                    ["指标", "2023", "2024"],
                    ["销量", "700万辆", "900万辆"],
                ]},
            ]
        )
        assert result["success"] is True
        assert Path(filepath).exists()
