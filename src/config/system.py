# -*- coding: utf-8 -*-
"""
System Configuration Loading Module
==============

Load and manage system-level configuration (database, paths, logging, monitoring, etc.).

Configuration file structure (config/system.yaml):
    database:
        postgres: {...}
        redis: {...}
        sqlite: {...}

    system:
        environment: development
        logging: {...}
        paths: {...}
        concurrency: {...}

    development: {...}
    data_providers: {...}
    platforms: {...}

Usage:
    from src.config.system import load_system_config, system_config

    # Get data directory
    data_dir = system_config.system.paths.data_dir

    # Get database URL
    db_url = system_config.database.postgres_url
"""

import os
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import logging

try:
    import yaml
except ImportError:
    yaml = None

logger = logging.getLogger(__name__)


# ============================================
# Configuration Data Classes
# ============================================

@dataclass
class PostgresConfig:
    """PostgreSQL Configuration"""
    enabled: bool = True
    host: str = "localhost"
    port: int = 5432
    name: str = "Zensers"
    user: str = ""
    password: str = ""
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30

    def url(self, redact: bool = False) -> str:
        """
        Get database connection URL

        Args:
            redact: Whether to redact password (for logging output)

        Returns:
            Database connection URL
        """
        if self.user and self.password:
            password = "***" if redact else self.password
            return f"postgresql://{self.user}:{password}@{self.host}:{self.port}/{self.name}"
        return f"postgresql://{self.host}:{self.port}/{self.name}"

    def get_safe_url(self) -> str:
        """Get redacted URL (for logging)"""
        return self.url(redact=True)


@dataclass
class RedisConfig:
    """Redis Configuration"""
    enabled: bool = True
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str = ""
    default_ttl: int = 3600
    max_connections: int = 50


@dataclass
class SQLiteConfig:
    """SQLite Configuration"""
    enabled: bool = True
    path: str = "data/knowledge.db"


@dataclass
class DatabaseConfig:
    """Database Configuration"""
    postgres: PostgresConfig = field(default_factory=PostgresConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    sqlite: SQLiteConfig = field(default_factory=SQLiteConfig)

    def postgres_url(self, redact: bool = False) -> str:
        """
        Get PostgreSQL URL

        Args:
            redact: Whether to redact password
        """
        return self.postgres.url(redact=redact)


@dataclass
class LoggingConfig:
    """Logging Configuration"""
    level: str = "INFO"
    file: str = "logs/Zensers.log"
    rotation: str = "100 MB"
    retention: str = "30 days"


@dataclass
class ConcurrencyConfig:
    """Concurrency Configuration"""
    max_concurrent_tasks: int = 10
    task_timeout: int = 1800


@dataclass
class PathsConfig:
    """Paths Configuration"""
    data_dir: str = "data"
    cache_dir: str = "cache"
    temp_dir: str = "tmp"
    report_output_dir: str = "output/reports"
    template_dir: str = "config/templates"
    tasks_dir: str = "data/tasks"  # Task state, checkpoints
    registries_dir: str = "data/registries"  # Session registries


@dataclass
class MonitoringConfig:
    """Monitoring Configuration"""
    enabled: bool = True
    metrics_port: int = 9090
    health_check_port: int = 8080


@dataclass
class ReportConfig:
    """Report Configuration"""
    max_duration: int = 7200
    template_dir: str = "config/templates"


@dataclass
class SystemSettings:
    """System Settings"""
    environment: str = "development"
    debug: bool = True
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    concurrency: ConcurrencyConfig = field(default_factory=ConcurrencyConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    report: ReportConfig = field(default_factory=ReportConfig)

    def is_production(self) -> bool:
        return self.environment == "production"

    def is_development(self) -> bool:
        return self.environment == "development"


@dataclass
class DevelopmentConfig:
    """Development Configuration"""
    test_mode: bool = True
    mock_llm: bool = False
    mock_data_providers: bool = True
    verbose_output: bool = True
    save_intermediate_results: bool = True
    trace_llm_calls: bool = True
    sample_data_dir: str = "examples/data"


@dataclass
class SystemConfig:
    """System Configuration"""
    version: str = "1.0"
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    system: SystemSettings = field(default_factory=SystemSettings)
    development: DevelopmentConfig = field(default_factory=DevelopmentConfig)
    data_providers: Dict[str, Any] = field(default_factory=dict)
    platforms: Dict[str, Any] = field(default_factory=dict)


# ============================================
# Configuration Loader
# ============================================

class SystemConfigLoader:
    """System Configuration Loader"""

    # Default configuration file path
    DEFAULT_CONFIG_PATH = "config/system.yaml"

    # Environment variable template regex
    ENV_VAR_PATTERN = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}')

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration loader

        Args:
            config_path: Configuration file path, defaults to config/system.yaml
        """
        if config_path is None:
            config_path = self.DEFAULT_CONFIG_PATH
        self.config_path = Path(config_path)
        self._config: Optional[SystemConfig] = None
        self._last_modified: Optional[float] = None

    def load(self, path: Optional[str] = None) -> SystemConfig:
        """
        Load configuration

        Args:
            path: Configuration file path (optional)

        Returns:
            SystemConfig instance
        """
        # Determine config path
        if path:
            config_path = Path(path)
        elif self.config_path:
            config_path = self.config_path
        else:
            config_path = Path(self.DEFAULT_CONFIG_PATH)

        # Check if file exists
        if not config_path.exists():
            logger.warning(f"Configuration file does not exist: {config_path}, using default config")
            return self._load_from_env()

        try:
            if yaml is None:
                raise ImportError("Please install PyYAML: pip install pyyaml")

            with open(config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}

            # Resolve environment variables
            data = self._resolve_env_vars(data)

            # Parse configuration
            self._config = self._parse_config(data)
            self._last_modified = config_path.stat().st_mtime
            self.config_path = config_path

            logger.info(f"Loaded system config file: {config_path}")
            return self._config

        except Exception as e:
            logger.error(f"Failed to load system config file: {e}")
            return self._load_from_env()

    def _load_from_env(self) -> SystemConfig:
        """Load configuration from environment variables"""
        config = SystemConfig()

        # Database configuration
        if os.environ.get('DB_USER'):
            config.database.postgres.user = os.environ['DB_USER']
        if os.environ.get('DB_PASSWORD'):
            config.database.postgres.password = os.environ['DB_PASSWORD']
        if os.environ.get('REDIS_PASSWORD'):
            config.database.redis.password = os.environ['REDIS_PASSWORD']

        return config

    def _resolve_env_vars(self, data: Any) -> Any:
        """Recursively resolve environment variables"""
        if isinstance(data, str):
            def replace_env(match) -> str:
                var_name = match.group(1)
                env_value = os.environ.get(var_name)
                return env_value if env_value is not None else match.group(0)
            return self.ENV_VAR_PATTERN.sub(replace_env, data)
        elif isinstance(data, dict):
            return {k: self._resolve_env_vars(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._resolve_env_vars(item) for item in data]
        else:
            return data

    def _parse_config(self, data: Dict[str, Any]) -> SystemConfig:
        """Parse configuration data"""
        config = SystemConfig()
        config.version = data.get('version', '1.0')

        # Parse database configuration
        if 'database' in data:
            db_data = data['database']

            if 'postgres' in db_data:
                pg = db_data['postgres']
                config.database.postgres = PostgresConfig(
                    enabled=pg.get('enabled', True),
                    host=pg.get('host', 'localhost'),
                    port=pg.get('port', 5432),
                    name=pg.get('name', 'Zensers'),
                    user=pg.get('user', ''),
                    password=pg.get('password', ''),
                    pool_size=pg.get('pool_size', 10),
                    max_overflow=pg.get('max_overflow', 20),
                    pool_timeout=pg.get('pool_timeout', 30),
                )

            if 'redis' in db_data:
                rd = db_data['redis']
                config.database.redis = RedisConfig(
                    enabled=rd.get('enabled', True),
                    host=rd.get('host', 'localhost'),
                    port=rd.get('port', 6379),
                    db=rd.get('db', 0),
                    password=rd.get('password', ''),
                    default_ttl=rd.get('default_ttl', 3600),
                    max_connections=rd.get('max_connections', 50),
                )

            if 'sqlite' in db_data:
                sq = db_data['sqlite']
                config.database.sqlite = SQLiteConfig(
                    enabled=sq.get('enabled', True),
                    path=sq.get('path', 'data/knowledge.db'),
                )

        # Parse system configuration
        if 'system' in data:
            sys_data = data['system']

            config.system = SystemSettings(
                environment=sys_data.get('environment', 'development'),
                debug=sys_data.get('debug', True),
            )

            if 'logging' in sys_data:
                log = sys_data['logging']
                config.system.logging = LoggingConfig(
                    level=log.get('level', 'INFO'),
                    file=log.get('file', 'logs/Zensers.log'),
                    rotation=log.get('rotation', '100 MB'),
                    retention=log.get('retention', '30 days'),
                )

            if 'concurrency' in sys_data:
                conc = sys_data['concurrency']
                config.system.concurrency = ConcurrencyConfig(
                    max_concurrent_tasks=conc.get('max_concurrent_tasks', 10),
                    task_timeout=conc.get('task_timeout', 1800),
                )

            if 'paths' in sys_data:
                paths = sys_data['paths']
                config.system.paths = PathsConfig(
                    data_dir=paths.get('data_dir', 'data'),
                    cache_dir=paths.get('cache_dir', 'cache'),
                    temp_dir=paths.get('temp_dir', 'tmp'),
                    report_output_dir=paths.get('report_output_dir', 'output/reports'),
                    template_dir=paths.get('template_dir', 'config/templates'),
                    tasks_dir=paths.get('tasks_dir', 'data/tasks'),
                    registries_dir=paths.get('registries_dir', 'data/registries'),
                )

            if 'monitoring' in sys_data:
                mon = sys_data['monitoring']
                config.system.monitoring = MonitoringConfig(
                    enabled=mon.get('enabled', True),
                    metrics_port=mon.get('metrics_port', 9090),
                    health_check_port=mon.get('health_check_port', 8080),
                )

            if 'report' in sys_data:
                rep = sys_data['report']
                config.system.report = ReportConfig(
                    max_duration=rep.get('max_duration', 7200),
                    template_dir=rep.get('template_dir', 'config/templates'),
                )

        # Parse development configuration
        if 'development' in data:
            dev = data['development']
            config.development = DevelopmentConfig(
                test_mode=dev.get('test_mode', True),
                mock_llm=dev.get('mock_llm', False),
                mock_data_providers=dev.get('mock_data_providers', True),
                verbose_output=dev.get('verbose_output', True),
                save_intermediate_results=dev.get('save_intermediate_results', True),
                trace_llm_calls=dev.get('trace_llm_calls', True),
                sample_data_dir=dev.get('sample_data_dir', 'examples/data'),
            )

        # Data provider configuration (keep as-is)
        if 'data_providers' in data:
            config.data_providers = data['data_providers']

        # Platform configuration (keep as-is)
        if 'platforms' in data:
            config.platforms = data['platforms']

        return config

    def reload(self) -> SystemConfig:
        """Reload configuration"""
        if not self.config_path:
            return self.load()
        return self.load(str(self.config_path))

    def get_config(self) -> Optional[SystemConfig]:
        """Get current configuration"""
        return self._config


# ============================================
# Global Instance and Convenience Functions
# ============================================

# Global loader instance
_system_loader: Optional[SystemConfigLoader] = None


def load_system_config(path: Optional[str] = None) -> SystemConfig:
    """
    Load system configuration

    Args:
        path: Configuration file path, defaults to config/system.yaml

    Returns:
        SystemConfig instance
    """
    global _system_loader

    if _system_loader is None:
        _system_loader = SystemConfigLoader(path)

    return _system_loader.load(path)


def get_system_loader() -> SystemConfigLoader:
    """
    Get global system configuration loader

    Returns:
        SystemConfigLoader instance
    """
    global _system_loader

    if _system_loader is None:
        _system_loader = SystemConfigLoader()

    return _system_loader


def reload_system_config() -> SystemConfig:
    """
    Reload system configuration

    Returns:
        SystemConfig instance
    """
    global _system_loader

    if _system_loader is None:
        _system_loader = SystemConfigLoader()

    return _system_loader.reload()


# Global configuration instance (convenience access)
system_config: Optional[SystemConfig] = None


def get_system_config() -> SystemConfig:
    """
    Get system configuration instance

    Returns:
        SystemConfig instance
    """
    global system_config

    if system_config is None:
        system_config = load_system_config()

    return system_config
