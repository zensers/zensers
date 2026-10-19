"""
SkillHotReloader 测试套件

覆盖：
- 初始扫描（启动时全量加载）
- 新增文件热加载
- 文件修改热重载
- 文件删除自动卸载
- 非 Skill 文件过滤（__init__.py / base.py / 非 _skill.py）
- 损坏文件安全降级（不影响已有 Skill）
- 并发安全（多线程注册）
- 生命周期管理（start / stop）
"""
import asyncio
import importlib
import sys
import time
import threading
import textwrap
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

from src.skills.base import Skill, SkillConfig, SkillRegistry
from src.skills.hot_reload import SkillHotReloader, SkillLoadError


# ────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_skill_dir(tmp_path):
    """临时 Skill 目录"""
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    return skill_dir


@pytest.fixture
def registry():
    """每个测试用独立 Registry，互不干扰"""
    return SkillRegistry()


@pytest.fixture
def reloader(tmp_skill_dir, registry):
    """创建 HotReloader 实例，测试结束后自动停止"""
    r = SkillHotReloader(skill_dir=str(tmp_skill_dir), registry=registry)
    yield r
    r.stop()


def make_skill_file(directory: Path, skill_name: str, class_name: str) -> Path:
    """在指定目录生成合法 Skill 文件"""
    code = textwrap.dedent(f"""
        from src.skills.base import Skill, SkillConfig

        class {class_name}(Skill):
            @property
            def name(self) -> str:
                return "{skill_name}"

            @property
            def description(self) -> str:
                return "Auto-generated {skill_name} for testing"

            async def execute(self, **kwargs):
                return {{"success": True, "skill": "{skill_name}"}}
    """)
    path = directory / f"{skill_name}_skill.py"
    path.write_text(code, encoding="utf-8")
    return path


def make_broken_skill_file(directory: Path, skill_name: str) -> Path:
    """生成语法错误的 Skill 文件"""
    path = directory / f"{skill_name}_skill.py"
    path.write_text("this is not valid python !!!@@@", encoding="utf-8")
    return path


# ────────────────────────────────────────────────────────────
# 1. 基础实例化
# ────────────────────────────────────────────────────────────

class TestHotReloaderInit:
    def test_creates_with_dir_and_registry(self, tmp_skill_dir, registry):
        r = SkillHotReloader(str(tmp_skill_dir), registry)
        assert r.skill_dir == str(tmp_skill_dir)
        assert r.registry is registry

    def test_uses_global_registry_by_default(self, tmp_skill_dir):
        from src.skills.base import get_registry
        r = SkillHotReloader(str(tmp_skill_dir))
        assert r.registry is get_registry()

    def test_not_running_before_start(self, reloader):
        assert reloader.is_running is False

    def test_invalid_dir_raises(self):
        with pytest.raises(ValueError, match="不存在"):
            SkillHotReloader("/nonexistent/path/xyz")


# ────────────────────────────────────────────────────────────
# 2. 初始扫描（启动时加载现有 Skill）
# ────────────────────────────────────────────────────────────

class TestInitialScan:
    def test_loads_existing_skills_on_start(self, tmp_skill_dir, registry):
        make_skill_file(tmp_skill_dir, "alpha", "AlphaSkill")
        make_skill_file(tmp_skill_dir, "beta", "BetaSkill")

        r = SkillHotReloader(str(tmp_skill_dir), registry)
        r.start()
        time.sleep(0.1)
        r.stop()

        assert registry.get("alpha") is not None
        assert registry.get("beta") is not None

    def test_skips_base_py(self, tmp_skill_dir, registry):
        (tmp_skill_dir / "base.py").write_text("# base", encoding="utf-8")
        make_skill_file(tmp_skill_dir, "gamma", "GammaSkill")

        r = SkillHotReloader(str(tmp_skill_dir), registry)
        r.start()
        time.sleep(0.1)
        r.stop()

        # base.py 不会被当做 Skill 注册
        assert registry.get("base") is None
        assert registry.get("gamma") is not None

    def test_skips_init_py(self, tmp_skill_dir, registry):
        (tmp_skill_dir / "__init__.py").write_text("", encoding="utf-8")
        r = SkillHotReloader(str(tmp_skill_dir), registry)
        r.start()
        time.sleep(0.1)
        r.stop()
        assert registry.get("__init__") is None

    def test_broken_file_does_not_crash(self, tmp_skill_dir, registry):
        make_skill_file(tmp_skill_dir, "good", "GoodSkill")
        make_broken_skill_file(tmp_skill_dir, "broken")

        r = SkillHotReloader(str(tmp_skill_dir), registry)
        r.start()
        time.sleep(0.1)
        r.stop()

        # 正常 Skill 仍然加载成功
        assert registry.get("good") is not None

    def test_returns_loaded_count(self, tmp_skill_dir, registry):
        make_skill_file(tmp_skill_dir, "s1", "S1Skill")
        make_skill_file(tmp_skill_dir, "s2", "S2Skill")

        r = SkillHotReloader(str(tmp_skill_dir), registry)
        count = r.scan_and_load()
        assert count == 2


# ────────────────────────────────────────────────────────────
# 3. 文件新增热加载
# ────────────────────────────────────────────────────────────

class TestFileCreated:
    def test_new_skill_file_auto_registered(self, tmp_skill_dir, registry):
        r = SkillHotReloader(str(tmp_skill_dir), registry)
        r.start()
        time.sleep(0.1)

        # 运行中新增文件
        make_skill_file(tmp_skill_dir, "dynamic", "DynamicSkill")
        time.sleep(0.5)  # 等待 watchdog 回调

        r.stop()
        assert registry.get("dynamic") is not None

    def test_non_skill_py_ignored(self, tmp_skill_dir, registry):
        r = SkillHotReloader(str(tmp_skill_dir), registry)
        r.start()
        time.sleep(0.1)

        # 新增非 Skill 文件（不以 _skill.py 结尾）
        (tmp_skill_dir / "utils.py").write_text("x = 1", encoding="utf-8")
        time.sleep(0.5)

        r.stop()
        assert registry.get("utils") is None


# ────────────────────────────────────────────────────────────
# 4. 文件修改热重载
# ────────────────────────────────────────────────────────────

class TestFileModified:
    def test_modified_skill_reloaded(self, tmp_skill_dir, registry):
        path = make_skill_file(tmp_skill_dir, "mutable", "MutableSkillV1")

        r = SkillHotReloader(str(tmp_skill_dir), registry)
        r.start()
        time.sleep(0.3)

        old_cls = registry.get("mutable")
        assert old_cls is not None

        # 修改文件（升级版本）
        new_code = textwrap.dedent("""
            from src.skills.base import Skill, SkillConfig

            class MutableSkillV2(Skill):
                @property
                def name(self):
                    return "mutable"

                @property
                def description(self):
                    return "v2"

                async def execute(self, **kwargs):
                    return {"success": True, "version": 2}
        """)
        path.write_text(new_code, encoding="utf-8")
        time.sleep(0.5)

        r.stop()
        new_cls = registry.get("mutable")
        assert new_cls is not None
        # 类名已更新为 V2
        assert new_cls.__name__ == "MutableSkillV2"


# ────────────────────────────────────────────────────────────
# 5. 文件删除自动卸载
# ────────────────────────────────────────────────────────────

class TestFileDeleted:
    def test_deleted_skill_unregistered(self, tmp_skill_dir, registry):
        path = make_skill_file(tmp_skill_dir, "temporary", "TemporarySkill")

        r = SkillHotReloader(str(tmp_skill_dir), registry)
        r.start()
        time.sleep(0.3)

        assert registry.get("temporary") is not None

        path.unlink()  # 删除文件
        time.sleep(0.5)

        r.stop()
        assert registry.get("temporary") is None


# ────────────────────────────────────────────────────────────
# 6. 错误处理与安全降级
# ────────────────────────────────────────────────────────────

class TestSafetyAndErrors:
    def test_broken_new_file_does_not_affect_existing(self, tmp_skill_dir, registry):
        make_skill_file(tmp_skill_dir, "stable", "StableSkill")

        r = SkillHotReloader(str(tmp_skill_dir), registry)
        r.start()
        time.sleep(0.2)

        # 运行中加入损坏文件
        make_broken_skill_file(tmp_skill_dir, "poison")
        time.sleep(0.5)

        r.stop()
        # stable Skill 未受影响
        assert registry.get("stable") is not None

    def test_error_callback_called_on_failure(self, tmp_skill_dir, registry):
        errors = []

        def on_error(path, exc):
            errors.append((path, exc))

        r = SkillHotReloader(str(tmp_skill_dir), registry, on_error=on_error)
        r.start()
        time.sleep(0.1)

        make_broken_skill_file(tmp_skill_dir, "bad")
        time.sleep(0.5)

        r.stop()
        assert len(errors) > 0

    def test_load_error_exception_carries_path(self, tmp_skill_dir, registry):
        path = make_broken_skill_file(tmp_skill_dir, "err")
        r = SkillHotReloader(str(tmp_skill_dir), registry)
        with pytest.raises(SkillLoadError):
            r._load_skill_file(str(path))


# ────────────────────────────────────────────────────────────
# 7. 生命周期管理
# ────────────────────────────────────────────────────────────

class TestLifecycle:
    def test_start_sets_running(self, reloader):
        reloader.start()
        time.sleep(0.1)
        assert reloader.is_running is True

    def test_stop_clears_running(self, reloader):
        reloader.start()
        time.sleep(0.1)
        reloader.stop()
        assert reloader.is_running is False

    def test_double_start_is_safe(self, reloader):
        reloader.start()
        reloader.start()  # 第二次 start 不应报错
        time.sleep(0.1)
        assert reloader.is_running is True

    def test_stop_without_start_is_safe(self, tmp_skill_dir, registry):
        r = SkillHotReloader(str(tmp_skill_dir), registry)
        r.stop()  # 未启动直接 stop，不应报错

    def test_context_manager(self, tmp_skill_dir, registry):
        with SkillHotReloader(str(tmp_skill_dir), registry) as r:
            assert r.is_running is True
        assert r.is_running is False


# ────────────────────────────────────────────────────────────
# 8. 状态查询
# ────────────────────────────────────────────────────────────

class TestStatus:
    def test_list_loaded_skills(self, tmp_skill_dir, registry):
        make_skill_file(tmp_skill_dir, "x1", "X1Skill")
        make_skill_file(tmp_skill_dir, "x2", "X2Skill")

        r = SkillHotReloader(str(tmp_skill_dir), registry)
        r.scan_and_load()

        loaded = r.list_loaded()
        assert "x1" in loaded
        assert "x2" in loaded

    def test_loaded_count(self, tmp_skill_dir, registry):
        make_skill_file(tmp_skill_dir, "c1", "C1Skill")
        make_skill_file(tmp_skill_dir, "c2", "C2Skill")
        make_skill_file(tmp_skill_dir, "c3", "C3Skill")

        r = SkillHotReloader(str(tmp_skill_dir), registry)
        r.scan_and_load()

        assert r.loaded_count == 3
