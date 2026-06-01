"""
FileSkill 测试 - TDD模式
"""
import pytest
import tempfile
import os
from pathlib import Path


class TestFileSkill:
    """测试文件读写 Skill"""

    @pytest.fixture
    def temp_dir(self):
        """临时目录"""
        with tempfile.TemporaryDirectory() as d:
            yield d

    @pytest.fixture
    def skill(self, temp_dir):
        """创建允许临时目录的 FileSkill"""
        from src.skills.file_skill import FileSkill
        from src.skills.base import SkillConfig
        # 允许临时目录进行测试
        return FileSkill(
            SkillConfig(name="file_skill", version="1.0.0"),
            allowed_dirs=[temp_dir]
        )

    @pytest.mark.asyncio
    async def test_write_text_file(self, skill, temp_dir):
        """测试写入文本文件"""
        filepath = os.path.join(temp_dir, "test.txt")
        result = await skill.execute(
            action="write",
            filepath=filepath,
            content="Hello, World!"
        )
        assert result["success"] is True
        assert Path(filepath).read_text(encoding="utf-8") == "Hello, World!"

    @pytest.mark.asyncio
    async def test_read_text_file(self, skill, temp_dir):
        """测试读取文本文件"""
        filepath = os.path.join(temp_dir, "read_test.txt")
        Path(filepath).write_text("读取内容", encoding="utf-8")

        result = await skill.execute(action="read", filepath=filepath)
        assert result["success"] is True
        assert result["content"] == "读取内容"

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, skill, temp_dir):
        """测试读取不存在的文件"""
        filepath = os.path.join(temp_dir, "nonexistent.txt")
        result = await skill.execute(action="read", filepath=filepath)
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_write_creates_parent_dirs(self, skill, temp_dir):
        """测试写入时自动创建父目录"""
        filepath = os.path.join(temp_dir, "a", "b", "c.txt")
        result = await skill.execute(action="write", filepath=filepath, content="深层目录")
        assert result["success"] is True
        assert Path(filepath).exists()

    @pytest.mark.asyncio
    async def test_list_directory(self, skill, temp_dir):
        """测试列出目录内容"""
        Path(os.path.join(temp_dir, "file1.txt")).write_text("1", encoding="utf-8")
        Path(os.path.join(temp_dir, "file2.txt")).write_text("2", encoding="utf-8")

        result = await skill.execute(action="list", filepath=temp_dir)
        assert result["success"] is True
        assert len(result["files"]) == 2

    @pytest.mark.asyncio
    async def test_delete_file(self, skill, temp_dir):
        """测试删除文件"""
        filepath = os.path.join(temp_dir, "delete_me.txt")
        Path(filepath).write_text("临时文件", encoding="utf-8")

        result = await skill.execute(action="delete", filepath=filepath)
        assert result["success"] is True
        assert not Path(filepath).exists()

    @pytest.mark.asyncio
    async def test_write_json_file(self, skill, temp_dir):
        """测试写入 JSON 文件"""
        import json
        filepath = os.path.join(temp_dir, "data.json")
        data = {"name": "test", "value": 42}

        result = await skill.execute(action="write_json", filepath=filepath, content=data)
        assert result["success"] is True
        loaded = json.loads(Path(filepath).read_text(encoding="utf-8"))
        assert loaded["name"] == "test"

    @pytest.mark.asyncio
    async def test_read_json_file(self, skill, temp_dir):
        """测试读取 JSON 文件"""
        import json
        filepath = os.path.join(temp_dir, "data.json")
        Path(filepath).write_text(json.dumps({"key": "val"}), encoding="utf-8")

        result = await skill.execute(action="read_json", filepath=filepath)
        assert result["success"] is True
        assert result["content"]["key"] == "val"

    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self, skill, temp_dir):
        """测试路径遍历攻击被阻止"""
        # 尝试访问临时目录外的文件
        result = await skill.execute(
            action="read",
            filepath="/etc/passwd"  # Unix 系统文件
        )
        assert result["success"] is False
        # 应该被阻止（无论是禁止目录还是超出允许范围）
        error = result.get("error", "")
        assert "禁止" in error or "超出" in error or "验证失败" in error

    @pytest.mark.asyncio
    async def test_delete_non_empty_directory_blocked(self, skill, temp_dir):
        """测试删除非空目录被阻止"""
        # 创建非空目录
        subdir = os.path.join(temp_dir, "subdir")
        os.makedirs(subdir)
        Path(os.path.join(subdir, "file.txt")).write_text("content", encoding="utf-8")
        
        # 尝试删除非空目录
        result = await skill.execute(action="delete", filepath=subdir)
        assert result["success"] is False
        assert "不为空" in result.get("error", "")

    @pytest.mark.asyncio
    async def test_unknown_action(self, skill, temp_dir):
        """测试未知操作"""
        result = await skill.execute(action="fly", filepath="/tmp/x")
        assert result["success"] is False
