"""
配置系统测试
============

测试配置管理模块的各项功能。
"""

import os
import json
import pytest
from pathlib import Path
from unittest.mock import patch

from src.config.settings import (
    Settings,
    LLMConfig,
    DatabaseConfig,
    SystemConfig,
)


class TestLLMConfig:
    """LLM配置测试"""

    def test_default_values(self):
        """测试默认值"""
        config = LLMConfig()

        assert config.provider == "openai"
        assert config.model == "gpt-4o"
        assert config.temperature == 0.7
        assert config.max_tokens == 4096
        assert config.max_context_tokens == 128000
        assert config.top_p == 1.0
        assert config.frequency_penalty == 0.0
        assert config.presence_penalty == 0.0

    def test_custom_values(self):
        """测试自定义值"""
        config = LLMConfig(
            provider="anthropic",
            model="claude-3-opus",
            temperature=0.5,
            max_tokens=8192,
            top_p=0.9,
        )

        assert config.provider == "anthropic"
        assert config.model == "claude-3-opus"
        assert config.temperature == 0.5
        assert config.max_tokens == 8192
        assert config.top_p == 0.9


class TestDatabaseConfig:
    """数据库配置测试"""

    def test_default_values(self):
        """测试默认值"""
        config = DatabaseConfig()

        assert config.postgres_host == "localhost"
        assert config.postgres_port == 5432
        assert config.postgres_name == "zensers"
        assert config.sqlite_path == "data/knowledge.db"

    def test_url_generation(self):
        """测试URL生成"""
        config = DatabaseConfig(
            postgres_user="testuser",
            postgres_password="testpass",
            postgres_host="db.example.com",
            postgres_port=5433,
            postgres_name="testdb"
        )

        url = config.postgres_url()

        assert "postgresql://" in url
        assert "testuser" in url
        assert "testpass" in url
        assert "db.example.com" in url
        assert "5433" in url
        assert "testdb" in url

    def test_url_without_credentials(self):
        """测试无凭证的URL"""
        config = DatabaseConfig(
            postgres_host="localhost",
            postgres_port=5432,
            postgres_name="testdb"
        )

        url = config.postgres_url()

        assert url == "postgresql://localhost:5432/testdb"

    def test_url_redacted(self):
        """测试脱敏URL"""
        config = DatabaseConfig(
            postgres_user="testuser",
            postgres_password="secret123",
        )

        safe = config.get_safe_url()

        assert "testuser" in safe
        assert "***" in safe
        assert "secret123" not in safe


class TestSystemConfig:
    """系统配置测试"""
    
    def test_default_values(self):
        """测试默认值"""
        config = SystemConfig()
        
        assert config.environment == "development"
        assert config.debug is True
        assert config.log_level == "INFO"
        assert config.max_concurrent_tasks == 10


_ENV_DEFAULTS = {
    "LLM_PROVIDER": "test-provider",
    "LLM_MODEL": "test-model",
    "LLM_API_KEY": "test-api-key",
    "LLM_BASE_URL": "https://test.api.com/v1",
    "LLM_CHEAP_MODEL": "test-cheap",
    "LLM_EMBEDDING_MODEL": "test-embedding",
    "DB_USER": "",
    "DB_PASSWORD": "",
}


class TestSettings:
    """配置管理器测试"""

    @patch.dict(os.environ, _ENV_DEFAULTS, clear=True)
    def test_settings_initialization(self):
        """测试配置初始化"""
        settings = Settings(config_path="nonexistent.toml")

        assert settings.llm.provider == "test-provider"
        assert settings.llm.model == "test-model"
        assert settings.database.postgres_host == "localhost"

    @patch.dict(os.environ, {**_ENV_DEFAULTS, "LLM_API_KEY": "test-key-123"}, clear=True)
    def test_load_from_env(self):
        """测试从环境变量加载"""
        settings = Settings(config_path="nonexistent.toml")

        assert settings.llm.api_key == "test-key-123"

    @patch.dict(os.environ, {
        **_ENV_DEFAULTS,
        "LLM_API_KEY": "test-openai-key",
        "LLM_MODEL": "gpt-4o-mini",
        "DB_USER": "testuser",
        "DB_PASSWORD": "testpass",
    }, clear=True)
    def test_multiple_env_vars(self):
        """测试多个环境变量"""
        settings = Settings(config_path="nonexistent.toml")

        assert settings.llm.api_key == "test-openai-key"
        assert settings.llm.model == "gpt-4o-mini"
        assert settings.database.postgres_user == "testuser"
        assert settings.database.postgres_password == "testpass"

    @patch.dict(os.environ, _ENV_DEFAULTS, clear=True)
    def test_is_production(self):
        """测试生产环境判断"""
        settings = Settings(config_path="nonexistent.toml")
        settings.system.environment = "production"

        assert settings.is_production() is True
        assert settings.is_development() is False

    @patch.dict(os.environ, _ENV_DEFAULTS, clear=True)
    def test_is_development(self):
        """测试开发环境判断"""
        settings = Settings(config_path="nonexistent.toml")
        settings.system.environment = "development"

        assert settings.is_development() is True
        assert settings.is_production() is False

    @patch.dict(os.environ, _ENV_DEFAULTS, clear=True)
    def test_get_llm_config(self):
        """测试获取LLM配置"""
        settings = Settings(config_path="nonexistent.toml")
        settings.llm.api_key = "test-key"

        config = settings.get_llm_config()

        assert config["api_key"] == "test-key"
        assert config["base_url"] == "https://test.api.com/v1"
        assert config["temperature"] == 0.7
        assert "cheap_model" in config
        assert "embedding_model" in config

    @patch.dict(os.environ, _ENV_DEFAULTS, clear=True)
    def test_get_llm_config_redacted(self):
        """测试脱敏LLM配置"""
        settings = Settings(config_path="nonexistent.toml")
        settings.llm.api_key = "sensitive-key"

        config = settings.get_llm_config(redact=True)

        assert config["api_key"] == "***"

    @patch.dict(os.environ, _ENV_DEFAULTS, clear=True)
    def test_update_from_request_full(self):
        """测试从请求更新LLM配置（全字段）"""
        settings = Settings(config_path="nonexistent.toml")

        settings.update_from_request({
            "provider": "anthropic",
            "model": "claude-3-5-sonnet-20241022",
            "api_key": "sk-ant-xxx",
            "api_endpoint": "https://api.anthropic.com/v1",
            "temperature": 0.3,
            "max_tokens": 8192,
            "top_p": 0.95,
            "frequency_penalty": 0.5,
            "presence_penalty": 0.2,
        })

        assert settings.llm.provider == "anthropic"
        assert settings.llm.model == "claude-3-5-sonnet-20241022"
        assert settings.llm.api_key == "sk-ant-xxx"
        assert settings.llm.base_url == "https://api.anthropic.com/v1"
        assert settings.llm.temperature == 0.3
        assert settings.llm.max_tokens == 8192
        assert settings.llm.top_p == 0.95
        assert settings.llm.frequency_penalty == 0.5
        assert settings.llm.presence_penalty == 0.2

    @patch.dict(os.environ, _ENV_DEFAULTS, clear=True)
    def test_update_from_request_partial(self):
        """测试从请求更新LLM配置（部分字段）"""
        settings = Settings(config_path="nonexistent.toml")
        original_model = settings.llm.model

        settings.update_from_request({
            "temperature": 0.1,
            "max_tokens": 2048,
        })

        assert settings.llm.temperature == 0.1
        assert settings.llm.max_tokens == 2048
        assert settings.llm.model == original_model

    @patch.dict(os.environ, _ENV_DEFAULTS, clear=True)
    def test_update_from_request_empty(self):
        """测试空请求不改变配置"""
        settings = Settings(config_path="nonexistent.toml")
        original = settings.llm.provider

        settings.update_from_request({})
        assert settings.llm.provider == original

    @patch.dict(os.environ, _ENV_DEFAULTS, clear=True)
    def test_update_from_request_none(self):
        """测试None请求不改变配置"""
        settings = Settings(config_path="nonexistent.toml")
        original = settings.llm.provider

        settings.update_from_request(None)
        assert settings.llm.provider == original

    @patch.dict(os.environ, _ENV_DEFAULTS, clear=True)
    def test_update_from_request_clears_api_key_when_empty_string(self):
        """测试空字符串可以清除api_key（已修复）"""
        settings = Settings(config_path="nonexistent.toml")
        settings.llm.api_key = "existing-key"

        settings.update_from_request({"api_key": ""})

        assert settings.llm.api_key == ""

    @patch.dict(os.environ, {
        **_ENV_DEFAULTS,
        "LLM_PROVIDER": "openai",
        "LLM_MODEL": "gpt-4o",
        "LLM_API_KEY": "env-key",
    }, clear=True)
    def test_reset_llm_to_env(self):
        """测试从环境变量重置LLM配置"""
        settings = Settings(config_path="nonexistent.toml")
        settings.llm.provider = "anthropic"
        settings.llm.model = "claude-3-opus"
        settings.llm.api_key = "override-key"

        settings.reset_llm_to_env()

        assert settings.llm.provider == "openai"
        assert settings.llm.model == "gpt-4o"
        assert settings.llm.api_key == "env-key"


class TestLLMConfigDiskPersistence:
    """LLM配置磁盘持久化测试"""

    @patch.dict(os.environ, _ENV_DEFAULTS, clear=True)
    def test_update_from_request_persists_to_disk(self):
        """测试update_from_request写入磁盘JSON"""
        settings = Settings(config_path="nonexistent.toml")
        persist_path = Path(settings._llm_config_persist_path)

        # Clean up before test
        if persist_path.exists():
            persist_path.unlink()

        settings.update_from_request({"provider": "anthropic", "model": "claude-3-opus"})

        assert persist_path.exists()
        data = json.loads(persist_path.read_text(encoding="utf-8"))
        assert data["provider"] == "anthropic"
        assert data["model"] == "claude-3-opus"
        assert data["api_key"] == _ENV_DEFAULTS["LLM_API_KEY"]

        persist_path.unlink(missing_ok=True)

    @patch.dict(os.environ, _ENV_DEFAULTS, clear=True)
    def test_disk_persistence_survives_new_instance(self):
        """测试磁盘持久化在新实例中恢复"""
        persist_path = Path("data/llm_config.json")
        persist_path.parent.mkdir(parents=True, exist_ok=True)
        persist_path.write_text(json.dumps({
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "api_key": "sk-persisted-key",
            "api_endpoint": "https://api.deepseek.com/v1",
            "temperature": 0.5,
            "max_tokens": 8192,
            "top_p": 0.9,
            "frequency_penalty": 0.0,
            "presence_penalty": 0.0,
            "cheap_model": "deepseek-v4-flash",
            "embedding_model": "text-embedding-3-small",
        }), encoding="utf-8")

        Settings._reset_instance()
        new_settings = Settings(config_path="nonexistent.toml")

        assert new_settings.llm.provider == "deepseek"
        assert new_settings.llm.model == "deepseek-v4-pro"
        assert new_settings.llm.api_key == "sk-persisted-key"
        assert new_settings.llm.base_url == "https://api.deepseek.com/v1"
        assert new_settings.llm.temperature == 0.5
        assert new_settings.llm.max_tokens == 8192

        persist_path.unlink(missing_ok=True)

    @patch.dict(os.environ, _ENV_DEFAULTS, clear=True)
    def test_reset_llm_to_env_clears_persisted_config(self):
        """测试reset_llm_to_env删除磁盘文件并恢复env值"""
        persist_path = Path("data/llm_config.json")
        persist_path.parent.mkdir(parents=True, exist_ok=True)
        persist_path.write_text(json.dumps({"provider": "custom"}), encoding="utf-8")

        Settings._reset_instance()
        settings = Settings(config_path="nonexistent.toml")
        assert settings.llm.provider == "custom"  # loaded from disk

        settings.reset_llm_to_env()
        assert not persist_path.exists()
        assert settings.llm.provider == _ENV_DEFAULTS["LLM_PROVIDER"]

        persist_path.unlink(missing_ok=True)


class TestConfigFiles:
    """配置文件测试"""
    
    def test_config_file_exists(self):
        """测试配置文件存在"""
        config_path = Path("config/settings.yaml")
        assert config_path.exists(), "配置文件不存在"
    
    def test_env_example_exists(self):
        """测试环境变量模板文件存在"""
        env_example = Path(".env.example")
        assert env_example.exists(), "环境变量模板文件不存在"
    
    def test_gitignore_exists(self):
        """测试gitignore文件存在"""
        gitignore = Path(".gitignore")
        assert gitignore.exists(), ".gitignore文件不存在"
    
    def test_gitignore_contains_sensitive_files(self):
        """测试gitignore包含敏感文件"""
        gitignore = Path(".gitignore")
        content = gitignore.read_text(encoding="utf-8")
        
        # 检查敏感文件是否被忽略
        assert ".env" in content
        assert "settings.toml" in content
        assert "*.key" in content


class TestConfigIntegration:
    """配置集成测试"""
    
    def test_config_module_import(self):
        """测试配置模块导入"""
        from src.config import settings, get_settings
        
        assert settings is not None
        assert callable(get_settings)
    
    def test_config_singleton(self):
        """测试配置单例"""
        from src.config import settings as s1
        from src.config import settings as s2
        
        # 应该是同一个实例
        assert s1 is s2