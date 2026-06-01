# -*- coding: utf-8 -*-
"""
Zensers Configuration Management Module v2.0
============================

Unified configuration management, preferring environment variable values.

Configuration (recommended via .env file):
    .env file configuration:
        LLM_API_KEY=sk-your-api-key
        LLM_BASE_URL=https://api.openai.com/v1  # or other compatible services
        LLM_MODEL=gpt-4o

    Supported providers: OpenAI, DeepSeek, GLM-4, Qwen, Moonshot, Ollama, etc.

Usage:
    from src.config.settings import settings

    # Get LLM configuration
    api_key = settings.llm.api_key
    model = settings.llm.model

    # Get database configuration
    db_url = settings.database.postgres_url
"""

import os
import re
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import logging

# Load .env file
try:
    from dotenv import load_dotenv
    load_dotenv()  # Auto-find .env file in project root
except ImportError:
    pass  # python-dotenv not installed, skip

try:
    import yaml
except ImportError:
    yaml = None

logger = logging.getLogger(__name__)


def load_yaml_config(config_path: str) -> Dict[str, Any]:
    """Load YAML configuration file"""
    if yaml is None:
        raise ImportError("Please install PyYAML: pip install pyyaml")

    if not os.path.exists(config_path):
        logger.warning(f"Configuration file does not exist: {config_path}")
        return {}

    with open(config_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Replace environment variables ${VAR_NAME}
    def replace_env_var(match):
        var_name = match.group(1)
        value = os.environ.get(var_name)
        return value if value is not None else match.group(0)

    content = re.sub(r'\$\{(\w+)\}', replace_env_var, content)

    config = yaml.safe_load(content)
    return config or {}


@dataclass
class LLMConfig:
    """LLM Configuration"""
    provider: str = "openai"
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o"
    cheap_model: str = "gpt-3.5-turbo"
    embedding_model: str = "text-embedding-3-small"
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    max_context_tokens: int = 128000
    cost_limit_per_report: float = 5.0


@dataclass
class DatabaseConfig:
    """Database Configuration"""
    # PostgreSQL
    postgres_enabled: bool = True
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_name: str = "zensers"
    postgres_user: str = ""
    postgres_password: str = ""
    postgres_pool_size: int = 10

    # Redis
    redis_enabled: bool = True
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_default_ttl: int = 3600

    # SQLite
    sqlite_enabled: bool = True
    sqlite_path: str = "data/knowledge.db"

    def postgres_url(self, redact: bool = False) -> str:
        """
        Get PostgreSQL connection URL

        Args:
            redact: Whether to redact password (for logging output)

        Returns:
            Database connection URL
        """
        if self.postgres_user and self.postgres_password:
            password = "***" if redact else self.postgres_password
            return f"postgresql://{self.postgres_user}:{password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_name}"
        return f"postgresql://{self.postgres_host}:{self.postgres_port}/{self.postgres_name}"

    def get_safe_url(self) -> str:
        """Get redacted URL (for logging)"""
        return self.postgres_url(redact=True)


@dataclass
class MCPConfig:
    """MCP Configuration"""
    max_concurrent_servers: int = 10
    max_concurrent_tools: int = 10
    max_concurrent_requests: int = 100

    default_timeout_connect: float = 5.0
    default_timeout_request: float = 30.0

    log_level: str = "INFO"
    cache_enabled: bool = True
    cache_ttl: int = 300
    cache_max_size: int = 1000

    servers: List[Dict[str, Any]] = field(default_factory=list)
    tools: List[Dict[str, Any]] = field(default_factory=list)
    data_sources: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class AgentConfig:
    """Agent Configuration"""
    orchestrator_timeout: Optional[int] = None  # None = no global timeout; individual components have their own limits
    orchestrator_max_retries: int = 3

    requirement_analysis_timeout: int = 300
    data_collection_timeout: int = 600
    report_generation_timeout: int = 1800
    quality_check_timeout: int = 300

    dynamic_max_lifetime: int = 7200
    dynamic_max_count: int = 50

    survey_simulation_timeout: int = 600
    survey_max_respondents: int = 1000


@dataclass
class SystemConfig:
    """System Configuration"""
    environment: str = "development"
    debug: bool = True

    log_level: str = "INFO"
    log_file: str = "logs/zensers.log"
    log_rotation: str = "100 MB"
    log_retention: str = "30 days"

    max_concurrent_tasks: int = 10
    task_timeout: int = 1800

    data_dir: str = "data"
    cache_dir: str = "cache"
    temp_dir: str = "tmp"
    report_output_dir: str = "output/reports"
    template_dir: str = "config/templates"

    metrics_port: int = 9090
    health_check_port: int = 8080

    report_max_duration: int = 7200


@dataclass
class ConversationConfig:
    """Conversation / Chat Configuration"""
    max_tool_iterations: int = 10


@dataclass
class QualityConfig:
    """Quality Control Configuration"""
    # Quality thresholds
    threshold_data_collection: int = 70
    threshold_analysis: int = 70
    threshold_report: int = 80

    # Retry configuration
    max_retries: int = 3

    # Degradation configuration
    degradation_enabled: bool = True
    min_data_volume: int = 3
    fallback_message: str = "Insufficient data, conclusion reliability reduced"

    # Output configuration
    include_quality_note: bool = True
    include_attempt_history: bool = True
    save_quality_metadata: bool = True

    def get_threshold(self, stage: str) -> int:
        """Get threshold for specified stage"""
        thresholds = {
            "data_collection": self.threshold_data_collection,
            "analysis": self.threshold_analysis,
            "report": self.threshold_report,
        }
        return thresholds.get(stage, 70)


class Settings:
    """Configuration Manager"""

    _instance = None

    @classmethod
    def _reset_instance(cls):
        """Reset singleton for testing purposes."""
        cls._instance = None

    def __new__(cls, config_path: Optional[str] = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config_path: Optional[str] = None):
        if self._initialized:
            return

        self.config_path = config_path or self._find_config_file()
        self._llm_config_persist_path = "data/llm_config.json"

        # Initialize configuration modules
        self.llm = LLMConfig()
        self.database = DatabaseConfig()
        self.mcp = MCPConfig()
        self.agents = AgentConfig()
        self.system = SystemConfig()
        self.quality = QualityConfig()  # New: quality control config
        self.conversation = ConversationConfig()

        # Data provider configuration (dynamic)
        self.data_providers: Dict[str, Any] = {}
        self.platforms: Dict[str, Any] = {}

        # Load configuration
        self._load_config()
        self._initialized = True

    def _find_config_file(self) -> str:
        """Find configuration file"""
        possible_paths = [
            "config/settings.yaml",
            "config/settings.yml",
            "settings.yaml",
            os.path.expanduser("~/.zensers/settings.yaml"),
        ]

        for path in possible_paths:
            if os.path.exists(path):
                return path

        # No configuration file found, return empty path (will load from .env and defaults)
        return ""

    def _load_config(self) -> None:
        """Load configuration — lowest to highest priority:
           1. LLMConfig defaults (dataclass)
           2. .env file / environment variables
           3. settings.yaml (if present)
           4. Persisted user LLM config from disk (highest — survives restart)
        """
        self._load_from_env()

        # Override with settings.yaml if present
        if self.config_path and os.path.exists(self.config_path):
            try:
                config = load_yaml_config(self.config_path)
                self._parse_config(config)
                logger.info(f"Configuration loaded successfully: {self.config_path}")
            except Exception as e:
                logger.warning(f"Failed to load configuration file: {e}")
        else:
            logger.debug("Using .env and default configuration (recommended approach)")

        # Highest priority: persisted user LLM config from disk
        self._load_llm_config_from_disk()

    def _parse_config(self, config: Dict[str, Any]) -> None:
        """Parse configuration"""
        # LLM configuration
        if 'llm' in config:
            llm = config['llm']

            # Direct properties
            self.llm.provider = llm.get('provider', self.llm.provider)
            self.llm.api_key = llm.get('api_key', self.llm.api_key)
            self.llm.base_url = llm.get('base_url', self.llm.base_url)
            self.llm.model = llm.get('model', self.llm.model)
            self.llm.cheap_model = llm.get('cheap_model', self.llm.cheap_model)
            self.llm.embedding_model = llm.get('embedding_model', self.llm.embedding_model)

            # Parameters
            self.llm.temperature = llm.get('temperature', self.llm.temperature)
            self.llm.max_tokens = llm.get('max_tokens', self.llm.max_tokens)
            self.llm.top_p = llm.get('top_p', self.llm.top_p)
            self.llm.cost_limit_per_report = llm.get('cost_limit_per_report', self.llm.cost_limit_per_report)

        # Database configuration
        if 'database' in config:
            db = config['database']

            if 'postgres' in db:
                pg = db['postgres']
                self.database.postgres_enabled = pg.get('enabled', self.database.postgres_enabled)
                self.database.postgres_host = pg.get('host', self.database.postgres_host)
                self.database.postgres_port = pg.get('port', self.database.postgres_port)
                self.database.postgres_name = pg.get('name', self.database.postgres_name)
                self.database.postgres_user = pg.get('user', self.database.postgres_user)
                self.database.postgres_password = pg.get('password', self.database.postgres_password)
                self.database.postgres_pool_size = pg.get('pool_size', self.database.postgres_pool_size)

            if 'redis' in db:
                rd = db['redis']
                self.database.redis_enabled = rd.get('enabled', self.database.redis_enabled)
                self.database.redis_host = rd.get('host', self.database.redis_host)
                self.database.redis_port = rd.get('port', self.database.redis_port)
                self.database.redis_password = rd.get('password', self.database.redis_password)
                self.database.redis_default_ttl = rd.get('default_ttl', self.database.redis_default_ttl)

            if 'sqlite' in db:
                sq = db['sqlite']
                self.database.sqlite_enabled = sq.get('enabled', self.database.sqlite_enabled)
                self.database.sqlite_path = sq.get('path', self.database.sqlite_path)

        # MCP configuration
        if 'mcp' in config:
            mcp = config['mcp']
            self.mcp.max_concurrent_servers = mcp.get('max_concurrent_servers', self.mcp.max_concurrent_servers)
            self.mcp.max_concurrent_tools = mcp.get('max_concurrent_tools', self.mcp.max_concurrent_tools)
            self.mcp.max_concurrent_requests = mcp.get('max_concurrent_requests', self.mcp.max_concurrent_requests)
            self.mcp.log_level = mcp.get('log_level', self.mcp.log_level)

            if 'default_timeout' in mcp:
                self.mcp.default_timeout_connect = mcp['default_timeout'].get('connect', self.mcp.default_timeout_connect)
                self.mcp.default_timeout_request = mcp['default_timeout'].get('request', self.mcp.default_timeout_request)

            if 'cache' in mcp:
                self.mcp.cache_enabled = mcp['cache'].get('enabled', self.mcp.cache_enabled)
                self.mcp.cache_ttl = mcp['cache'].get('ttl', self.mcp.cache_ttl)
                self.mcp.cache_max_size = mcp['cache'].get('max_size', self.mcp.cache_max_size)

            self.mcp.servers = mcp.get('servers', [])
            self.mcp.tools = mcp.get('tools', [])
            self.mcp.data_sources = mcp.get('data_sources', [])

        # Agent configuration
        if 'agents' in config:
            agents = config['agents']

            if 'orchestrator' in agents:
                self.agents.orchestrator_timeout = agents['orchestrator'].get('timeout', self.agents.orchestrator_timeout)
                self.agents.orchestrator_max_retries = agents['orchestrator'].get('max_retries', self.agents.orchestrator_max_retries)

            if 'fixed' in agents:
                fixed = agents['fixed']
                self.agents.requirement_analysis_timeout = fixed.get('requirement_analysis_timeout', self.agents.requirement_analysis_timeout)
                self.agents.data_collection_timeout = fixed.get('data_collection_timeout', self.agents.data_collection_timeout)
                self.agents.report_generation_timeout = fixed.get('report_generation_timeout', self.agents.report_generation_timeout)
                self.agents.quality_check_timeout = fixed.get('quality_check_timeout', self.agents.quality_check_timeout)

            if 'dynamic' in agents:
                dynamic = agents['dynamic']
                self.agents.dynamic_max_lifetime = dynamic.get('max_lifetime', self.agents.dynamic_max_lifetime)
                self.agents.dynamic_max_count = dynamic.get('max_count', self.agents.dynamic_max_count)

            if 'survey' in agents:
                survey = agents['survey']
                self.agents.survey_simulation_timeout = survey.get('simulation_timeout', self.agents.survey_simulation_timeout)
                self.agents.survey_max_respondents = survey.get('max_respondents', self.agents.survey_max_respondents)

        # System configuration
        if 'system' in config:
            sys = config['system']
            self.system.environment = sys.get('environment', self.system.environment)
            self.system.debug = sys.get('debug', self.system.debug)

            if 'logging' in sys:
                self.system.log_level = sys['logging'].get('level', self.system.log_level)
                self.system.log_file = sys['logging'].get('file', self.system.log_file)
                self.system.log_rotation = sys['logging'].get('rotation', self.system.log_rotation)
                self.system.log_retention = sys['logging'].get('retention', self.system.log_retention)

            if 'concurrency' in sys:
                self.system.max_concurrent_tasks = sys['concurrency'].get('max_concurrent_tasks', self.system.max_concurrent_tasks)
                self.system.task_timeout = sys['concurrency'].get('task_timeout', self.system.task_timeout)

            if 'paths' in sys:
                paths = sys['paths']
                self.system.data_dir = paths.get('data_dir', self.system.data_dir)
                self.system.cache_dir = paths.get('cache_dir', self.system.cache_dir)
                self.system.temp_dir = paths.get('temp_dir', self.system.temp_dir)
                self.system.report_output_dir = paths.get('report_output_dir', self.system.report_output_dir)
                self.system.template_dir = paths.get('template_dir', self.system.template_dir)

            if 'monitoring' in sys:
                self.system.metrics_port = sys['monitoring'].get('metrics_port', self.system.metrics_port)
                self.system.health_check_port = sys['monitoring'].get('health_check_port', self.system.health_check_port)

            if 'report' in sys:
                self.system.report_max_duration = sys['report'].get('max_duration', self.system.report_max_duration)

        # Data provider configuration
        if 'data_providers' in config:
            self.data_providers = config['data_providers']

        # Platform configuration
        if 'platforms' in config:
            self.platforms = config['platforms']

        # Conversation configuration
        if 'conversation' in config:
            conv = config['conversation']
            self.conversation.max_tool_iterations = conv.get(
                'max_tool_iterations', self.conversation.max_tool_iterations
            )

        # Quality control configuration
        if 'quality' in config:
            q = config['quality']

            # Threshold configuration
            if 'thresholds' in q:
                thresholds = q['thresholds']
                self.quality.threshold_data_collection = thresholds.get('data_collection', self.quality.threshold_data_collection)
                self.quality.threshold_analysis = thresholds.get('analysis', self.quality.threshold_analysis)
                self.quality.threshold_report = thresholds.get('report', self.quality.threshold_report)

            # Retry configuration
            self.quality.max_retries = q.get('max_retries', self.quality.max_retries)

            # Degradation configuration
            if 'degradation' in q:
                deg = q['degradation']
                self.quality.degradation_enabled = deg.get('enabled', self.quality.degradation_enabled)
                self.quality.min_data_volume = deg.get('min_data_volume', self.quality.min_data_volume)
                self.quality.fallback_message = deg.get('fallback_message', self.quality.fallback_message)

            # Output configuration
            if 'output' in q:
                out = q['output']
                self.quality.include_quality_note = out.get('include_quality_note', self.quality.include_quality_note)
                self.quality.include_attempt_history = out.get('include_attempt_history', self.quality.include_attempt_history)
                self.quality.save_quality_metadata = out.get('save_quality_metadata', self.quality.save_quality_metadata)

    def _load_from_env(self) -> None:
        """Load configuration from environment variables (highest priority)"""
        # LLM general configuration
        if os.environ.get('LLM_PROVIDER'):
            self.llm.provider = os.environ['LLM_PROVIDER']
        if os.environ.get('LLM_API_KEY'):
            self.llm.api_key = os.environ['LLM_API_KEY']
        if os.environ.get('LLM_BASE_URL'):
            self.llm.base_url = os.environ['LLM_BASE_URL']
        if os.environ.get('LLM_MODEL'):
            self.llm.model = os.environ['LLM_MODEL']
        if os.environ.get('LLM_CHEAP_MODEL'):
            self.llm.cheap_model = os.environ['LLM_CHEAP_MODEL']
        if os.environ.get('LLM_EMBEDDING_MODEL'):
            self.llm.embedding_model = os.environ['LLM_EMBEDDING_MODEL']
        if os.environ.get('LLM_TEMPERATURE'):
            self.llm.temperature = float(os.environ['LLM_TEMPERATURE'])
        if os.environ.get('LLM_MAX_TOKENS'):
            self.llm.max_tokens = int(os.environ['LLM_MAX_TOKENS'])

        # Database
        if os.environ.get('DB_USER'):
            self.database.postgres_user = os.environ['DB_USER']
        if os.environ.get('DB_PASSWORD'):
            self.database.postgres_password = os.environ['DB_PASSWORD']
        if os.environ.get('REDIS_PASSWORD'):
            self.database.redis_password = os.environ['REDIS_PASSWORD']

        # Quality (environment variables take precedence)
        if os.environ.get('QUALITY_THRESHOLD_DATA'):
            self.quality.threshold_data_collection = int(os.environ['QUALITY_THRESHOLD_DATA'])
        if os.environ.get('QUALITY_THRESHOLD_ANALYSIS'):
            self.quality.threshold_analysis = int(os.environ['QUALITY_THRESHOLD_ANALYSIS'])
        if os.environ.get('QUALITY_THRESHOLD_REPORT'):
            self.quality.threshold_report = int(os.environ['QUALITY_THRESHOLD_REPORT'])
        if os.environ.get('QUALITY_MAX_RETRIES'):
            self.quality.max_retries = int(os.environ['QUALITY_MAX_RETRIES'])

    # ── Disk persistence helpers ──────────────────────────────────────────

    def _persist_llm_config(self) -> None:
        """Write current LLM config to disk JSON so it survives restart."""
        try:
            path = Path(self._llm_config_persist_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "provider": self.llm.provider,
                "model": self.llm.model,
                "api_key": self.llm.api_key,
                "api_endpoint": self.llm.base_url,
                "temperature": self.llm.temperature,
                "max_tokens": self.llm.max_tokens,
                "top_p": self.llm.top_p,
                "frequency_penalty": self.llm.frequency_penalty,
                "presence_penalty": self.llm.presence_penalty,
                "cheap_model": self.llm.cheap_model,
                "embedding_model": self.llm.embedding_model,
            }
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            logger.debug("LLM config persisted to %s", path)
        except Exception as e:
            logger.warning("Failed to persist LLM config: %s", e)

    def _load_llm_config_from_disk(self) -> None:
        """Load LLM config from disk JSON, overriding env/defaults."""
        path = Path(self._llm_config_persist_path)
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.llm.provider = data.get("provider", self.llm.provider)
            self.llm.model = data.get("model", self.llm.model)
            self.llm.api_key = data.get("api_key", self.llm.api_key)
            self.llm.base_url = data.get("api_endpoint", self.llm.base_url)
            self.llm.temperature = float(data.get("temperature", self.llm.temperature))
            self.llm.max_tokens = int(data.get("max_tokens", self.llm.max_tokens))
            self.llm.top_p = float(data.get("top_p", self.llm.top_p))
            self.llm.frequency_penalty = float(data.get("frequency_penalty", self.llm.frequency_penalty))
            self.llm.presence_penalty = float(data.get("presence_penalty", self.llm.presence_penalty))
            self.llm.cheap_model = data.get("cheap_model", self.llm.cheap_model)
            self.llm.embedding_model = data.get("embedding_model", self.llm.embedding_model)
            logger.info("LLM config restored from %s", path)
        except Exception as e:
            logger.warning("Failed to load persisted LLM config: %s", e)

    def _clear_llm_config_persist(self) -> None:
        """Delete the persisted LLM config file on disk."""
        try:
            path = Path(self._llm_config_persist_path)
            if path.exists():
                path.unlink()
                logger.debug("Persisted LLM config deleted")
        except Exception as e:
            logger.warning("Failed to delete persisted LLM config: %s", e)

    # ── Public API ────────────────────────────────────────────────────────

    def update_from_request(self, llm_config: Dict[str, Any]) -> None:
        if not llm_config:
            return

        if llm_config.get("provider"):
            self.llm.provider = llm_config["provider"]

        if llm_config.get("model"):
            self.llm.model = llm_config["model"]

        # Use explicit key presence check so empty string can clear the value
        if "api_key" in llm_config:
            self.llm.api_key = llm_config["api_key"]

        if llm_config.get("api_endpoint"):
            self.llm.base_url = llm_config["api_endpoint"]

        if "temperature" in llm_config and llm_config["temperature"] is not None:
            self.llm.temperature = float(llm_config["temperature"])

        if "max_tokens" in llm_config and llm_config["max_tokens"] is not None:
            self.llm.max_tokens = int(llm_config["max_tokens"])

        if "top_p" in llm_config and llm_config["top_p"] is not None:
            self.llm.top_p = float(llm_config["top_p"])

        if "frequency_penalty" in llm_config and llm_config["frequency_penalty"] is not None:
            self.llm.frequency_penalty = float(llm_config["frequency_penalty"])

        if "presence_penalty" in llm_config and llm_config["presence_penalty"] is not None:
            self.llm.presence_penalty = float(llm_config["presence_penalty"])

        # Persist to disk after every update
        self._persist_llm_config()

    def reset_llm_to_env(self) -> None:
        """从 .env 环境变量重新加载 LLM 配置（用于 Reset to Default）"""
        self._clear_llm_config_persist()

        env_mappings = [
            ('LLM_PROVIDER', 'provider', None),
            ('LLM_MODEL', 'model', None),
            ('LLM_API_KEY', 'api_key', None),
            ('LLM_BASE_URL', 'base_url', None),
            ('LLM_CHEAP_MODEL', 'cheap_model', None),
            ('LLM_EMBEDDING_MODEL', 'embedding_model', None),
            ('LLM_TEMPERATURE', 'temperature', float),
            ('LLM_MAX_TOKENS', 'max_tokens', int),
        ]
        for env_key, attr_name, converter in env_mappings:
            if os.environ.get(env_key):
                val = os.environ[env_key]
                if converter:
                    setattr(self.llm, attr_name, converter(val))
                else:
                    setattr(self.llm, attr_name, val)

    def is_production(self) -> bool:
        return self.system.environment == "production"

    def is_development(self) -> bool:
        return self.system.environment == "development"

    def validate_production(self) -> List[str]:
        """
        Validate production environment configuration security

        Returns:
            List of warning messages, empty list means pass
        """
        warnings = []

        if not self.is_production():
            return warnings  # Non-production environment, skip validation

        # Check API Key
        if not self.llm.api_key:
            warnings.append("LLM API Key not configured")

        # Check database password
        if self.database.postgres_enabled and not self.database.postgres_password:
            warnings.append("PostgreSQL password not configured (production should have password)")

        # Check Redis password
        if self.database.redis_enabled and not self.database.redis_password:
            warnings.append("Redis password not configured (production should have password)")

        # Check debug mode
        if self.system.debug:
            warnings.append("Debug mode enabled (should be disabled in production)")

        return warnings

    def get_template_path(self, template_name: str) -> str:
        """Get report template path"""
        return os.path.join(self.system.template_dir, f"{template_name}.yaml")

    def get_llm_config(self, provider: Optional[str] = None, redact: bool = False) -> Dict[str, Any]:
        """
        Get LLM configuration

        Args:
            provider: Provider (reserved parameter)
            redact: Whether to redact sensitive information

        Returns:
            LLM configuration dict
        """
        return {
            "api_key": "***" if redact else self.llm.api_key,
            "base_url": self.llm.base_url,
            "model": self.llm.model,
            "temperature": self.llm.temperature,
            "max_tokens": self.llm.max_tokens,
            "top_p": self.llm.top_p,
            "frequency_penalty": self.llm.frequency_penalty,
            "presence_penalty": self.llm.presence_penalty,
            "cheap_model": self.llm.cheap_model,
            "embedding_model": self.llm.embedding_model,
        }

    def get_safe_llm_config(self) -> Dict[str, Any]:
        """Get redacted LLM configuration (for logging)"""
        return self.get_llm_config(redact=True)


# Global configuration instance
settings = Settings()


def get_settings() -> Settings:
    """Get configuration instance"""
    return settings
