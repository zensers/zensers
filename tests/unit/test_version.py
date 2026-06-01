import os
from pathlib import Path
import pytest
from src.core.version import compare_versions, get_local_version, VersionInfo


# ================================================================
# compare_versions 参数化测试
# ================================================================

@pytest.mark.parametrize("v1,v2,expected", [
    # 相等
    ("1.0.0", "1.0.0", 0),
    ("2.3.4", "2.3.4", 0),
    # Patch 差异
    ("1.0.0", "1.0.1", -1),
    ("1.0.1", "1.0.0", 1),
    # 多位数 Patch
    ("1.0.9", "1.0.10", -1),
    ("1.0.10", "1.0.9", 1),
    # Minor 差异
    ("1.0.0", "1.1.0", -1),
    ("2.1.0", "2.0.0", 1),
    # Major 差异
    ("1.0.0", "2.0.0", -1),
    ("3.0.0", "2.0.0", 1),
    # Pre-release < release
    ("1.0.0-alpha", "1.0.0", -1),
    ("1.0.0", "1.0.0-alpha", 1),
    # alpha < beta
    ("1.0.0-alpha", "1.0.0-beta", -1),
    ("1.0.0-beta", "1.0.0-alpha", 1),
    # 数字比较（beta.2 < beta.11）
    ("1.0.0-beta.2", "1.0.0-beta.11", -1),
    ("1.0.0-beta.11", "1.0.0-beta.2", 1),
    # 数字 < 字符串
    ("1.0.0-1", "1.0.0-alpha", -1),
    ("1.0.0-alpha", "1.0.0-1", 1),
    # 短 < 长
    ("1.0.0-alpha", "1.0.0-alpha.1", -1),
    ("1.0.0-alpha.1", "1.0.0-alpha", 1),
    # 含构建元数据（忽略）
    ("1.0.0+build123", "1.0.0", 0),
    ("1.0.0", "1.0.0+build456", 0),
    # 复杂 prerelease
    ("1.0.0-rc.1", "1.0.0-rc.2", -1),
    ("1.0.0-rc.2", "1.0.0", -1),
    ("1.0.0-alpha.1.beta.2", "1.0.0-alpha.1.beta.3", -1),
])
def test_compare_versions(v1, v2, expected):
    assert compare_versions(v1, v2) == expected


# ================================================================
# get_local_version 测试
# ================================================================

def test_get_local_version_from_env(monkeypatch):
    """ZENSERS_VERSION 环境变量优先"""
    monkeypatch.setenv("ZENSERS_VERSION", "2.0.0-rc.1")
    assert get_local_version() == "2.0.0-rc.1"


def test_get_local_version_from_file():
    """回退到 VERSION 文件"""
    os.environ.pop("ZENSERS_VERSION", None)
    ver = get_local_version()
    # VERSION 文件内容为 "1.0.0"
    assert ver == "1.0.0", f"Expected 1.0.0, got {ver}"


# ================================================================
# VersionInfo 数据模型测试
# ================================================================

def test_version_info_to_dict():
    info = VersionInfo(
        local_version="1.0.0",
        remote_version="1.1.0",
        build_date="2026-05-13",
        is_latest=False,
    )
    d = info.to_dict()
    assert d["local_version"] == "1.0.0"
    assert d["remote_version"] == "1.1.0"
    assert d["is_latest"] is False
    assert d["check_error"] is None
    assert d["changelog_url"] == "/api/v1/changelog"


def test_version_info_defaults():
    info = VersionInfo(local_version="1.0.0")
    assert info.is_latest is True
    assert info.check_error is None


def test_version_info_is_latest_null():
    """is_latest=None 表示检测失败"""
    info = VersionInfo(local_version="1.0.0", is_latest=None, check_error="remote_unreachable")
    assert info.is_latest is None
    assert info.check_error == "remote_unreachable"
    d = info.to_dict()
    assert d["is_latest"] is None
    assert d["check_error"] == "remote_unreachable"
