# -*- coding: utf-8 -*-
"""实战前配置体检：data/llm_profiles.json 结构不变量（R2）。

只断言结构与布尔/长度条件；本文件绝不打印、记录或拼入任何 api_key 值。
"""
import json
from pathlib import Path

import pytest

PROFILES_PATH = Path("data/llm_profiles.json")


def _load_config():
    if not PROFILES_PATH.exists():
        pytest.skip("data/llm_profiles.json 不存在，跳过配置体检")
    return json.loads(PROFILES_PATH.read_text(encoding="utf-8"))


def test_default_profile_exists():
    config = _load_config()
    profiles = config.get("profiles", {})
    assert config.get("default_profile") in profiles


def test_at_least_one_enabled_profile_with_key():
    config = _load_config()
    profiles = config.get("profiles", {})
    usable = [
        name for name, profile in profiles.items()
        if profile.get("enabled") is True and str(profile.get("api_key") or "").strip()
    ]
    assert usable, "没有任何 enabled 且带 api_key 的 profile（实战会直接 AUTH/BALANCE 耗尽）"


def test_enabled_profiles_have_endpoint_and_model():
    config = _load_config()
    profiles = config.get("profiles", {})
    for name, profile in profiles.items():
        if profile.get("enabled") is not True:
            continue
        assert str(profile.get("base_url") or "").strip(), f"enabled profile '{name}' 缺 base_url"
        assert str(profile.get("model") or "").strip(), f"enabled profile '{name}' 缺 model"


def test_fallback_chain_names_exist():
    config = _load_config()
    profiles = config.get("profiles", {})
    chain = config.get("fallback_chain", []) or []
    assert chain, "fallback_chain 为空：引擎没有候选可升级"
    missing = [name for name in chain if name not in profiles]
    assert missing == []
    # 禁用 profile 允许留在链上：引擎按 enabled/健康状态跳过，不做静态校验。


def test_routing_references_exist():
    config = _load_config()
    profiles = config.get("profiles", {})
    for routing_key in ("fixed_agent_routing", "action_routing"):
        routing = config.get(routing_key, {}) or {}
        missing = sorted({name for name in routing.values() if name not in profiles})
        assert missing == [], f"{routing_key} 引用了不存在的 profile: {missing}"
