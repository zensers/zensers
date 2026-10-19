# -*- coding: utf-8 -*-
"""
Agent Configuration Loading Module
================

Load and manage detailed Agent configurations.

Configuration file structure (config/agents.yaml):
    requirement_analysis:
        llm: {model, temperature, max_tokens}
        capabilities: [...]
        industry_templates: [...]
        output: {...}

    report_generation:
        llm: {...}
        capabilities: [...]
        templates: {...}
        output_formats: [...]

Usage:
    from src.config.agents import load_agents_config, get_agent_config

    # Load all config
    agents_config = load_agents_config()

    # Get specific Agent config
    req_config = get_agent_config("requirement_analysis")
"""

import os
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import logging

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    yaml = None
    YAML_AVAILABLE = False

logger = logging.getLogger(__name__)


# ============================================
# Configuration Data Classes
# ============================================

@dataclass
class AgentLLMConfig:
    """Agent LLM Configuration"""
    model: str = "gpt-4o"
    temperature: float = 0.7
    max_tokens: int = 4096


@dataclass
class IndustryTemplate:
    """Industry Template"""
    name: str = ""
    keywords: List[str] = field(default_factory=list)
    aspects: List[str] = field(default_factory=list)


@dataclass
class OutputConfig:
    """Output Configuration"""
    format: str = "structured"
    include_complexity: bool = True
    include_skills: bool = True


@dataclass
class ReportTemplate:
    """Report Template"""
    name: str = ""
    structure: List[str] = field(default_factory=list)
    style: str = "formal"
    word_count_target: int = 6000


@dataclass
class AgentConfig:
    """Single Agent Configuration"""
    name: str = ""
    llm: AgentLLMConfig = field(default_factory=AgentLLMConfig)
    capabilities: List[str] = field(default_factory=list)
    industry_templates: List[IndustryTemplate] = field(default_factory=list)
    output: OutputConfig = field(default_factory=OutputConfig)
    templates: Dict[str, ReportTemplate] = field(default_factory=dict)
    output_formats: List[str] = field(default_factory=list)
    check_items: List[Dict[str, Any]] = field(default_factory=list)
    thresholds: Dict[str, float] = field(default_factory=dict)
    data_sources: List[Dict[str, Any]] = field(default_factory=list)
    timeout: Dict[str, int] = field(default_factory=dict)


@dataclass
class AgentsConfig:
    """All Agent Configuration"""
    version: str = "1.0"

    # Per-Agent configurations
    requirement_analysis: AgentConfig = field(default_factory=AgentConfig)
    report_generation: AgentConfig = field(default_factory=AgentConfig)
    layout_design: AgentConfig = field(default_factory=AgentConfig)
    quality_check: AgentConfig = field(default_factory=AgentConfig)
    data_collection: AgentConfig = field(default_factory=AgentConfig)

    # Global timeout configuration
    timeouts: Dict[str, int] = field(default_factory=dict)

    # Retry configuration
    retries: Dict[str, Any] = field(default_factory=dict)


# ============================================
# Configuration Loader
# ============================================

class AgentsConfigLoader:
    """Agent Configuration Loader"""

    # Default configuration file path
    DEFAULT_CONFIG_PATH = "config/agents.yaml"

    # Environment variable template regex
    ENV_VAR_PATTERN = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}')

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration loader

        Args:
            config_path: Configuration file path, defaults to config/agents.yaml
        """
        if config_path is None:
            config_path = self.DEFAULT_CONFIG_PATH
        self.config_path = Path(config_path)
        self._config: Optional[AgentsConfig] = None
        self._last_modified: Optional[float] = None

    def load(self, path: Optional[str] = None) -> AgentsConfig:
        """
        Load configuration

        Args:
            path: Configuration file path (optional)

        Returns:
            AgentsConfig instance
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
            return AgentsConfig()

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

            logger.info(f"Loaded Agent config file: {config_path}")
            return self._config

        except Exception as e:
            logger.error(f"Failed to load Agent config file: {e}")
            return AgentsConfig()

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

    def _parse_config(self, data: Dict[str, Any]) -> AgentsConfig:
        """Parse configuration data"""
        config = AgentsConfig()
        config.version = data.get('version', '1.0')

        # Parse per-Agent configurations
        agent_names = [
            'requirement_analysis',
            'report_generation',
            'layout_design',
            'quality_check',
            'data_collection'
        ]

        for agent_name in agent_names:
            if agent_name in data:
                agent_data = data[agent_name]
                agent_config = self._parse_agent_config(agent_name, agent_data)
                setattr(config, agent_name, agent_config)

        # Parse global configuration
        if 'timeouts' in data:
            config.timeouts = data['timeouts']

        if 'retries' in data:
            config.retries = data['retries']

        return config

    def _parse_agent_config(self, name: str, data: Dict[str, Any]) -> AgentConfig:
        """Parse single Agent configuration"""
        config = AgentConfig(name=name)

        # LLM configuration
        if 'llm' in data:
            llm_data = data['llm']
            config.llm = AgentLLMConfig(
                model=llm_data.get('model', 'gpt-4o'),
                temperature=llm_data.get('temperature', 0.7),
                max_tokens=llm_data.get('max_tokens', 4096),
            )

        # Capability configuration
        if 'capabilities' in data:
            config.capabilities = data['capabilities']

        # Industry templates
        if 'industry_templates' in data:
            templates = []
            for t in data['industry_templates']:
                templates.append(IndustryTemplate(
                    name=t.get('name', ''),
                    keywords=t.get('keywords', []),
                    aspects=t.get('aspects', []),
                ))
            config.industry_templates = templates

        # Output configuration
        if 'output' in data:
            output_data = data['output']
            config.output = OutputConfig(
                format=output_data.get('format', 'structured'),
                include_complexity=output_data.get('include_complexity', True),
                include_skills=output_data.get('include_skills', True),
            )

        # Report templates
        if 'templates' in data:
            templates = {}
            for key, t in data['templates'].items():
                templates[key] = ReportTemplate(
                    name=t.get('name', ''),
                    structure=t.get('structure', []),
                    style=t.get('style', 'formal'),
                    word_count_target=t.get('word_count_target', 6000),
                )
            config.templates = templates

        # Output formats
        if 'output_formats' in data:
            config.output_formats = data['output_formats']

        # Check items
        if 'check_items' in data:
            config.check_items = data['check_items']

        # Thresholds
        if 'thresholds' in data:
            config.thresholds = data['thresholds']

        # Data sources
        if 'data_sources' in data:
            config.data_sources = data['data_sources']

        # Timeout
        if 'timeout' in data:
            config.timeout = data['timeout']

        return config

    def reload(self) -> AgentsConfig:
        """Reload configuration"""
        if not self.config_path:
            return self.load()
        return self.load(str(self.config_path))

    def get_config(self) -> Optional[AgentsConfig]:
        """Get current configuration"""
        return self._config

    def get_agent_config(self, agent_name: str) -> Optional[AgentConfig]:
        """
        Get specific Agent configuration

        Args:
            agent_name: Agent name

        Returns:
            AgentConfig instance, or None if not found
        """
        if self._config is None:
            self.load()

        if self._config is None:
            return None

        return getattr(self._config, agent_name, None)


# ============================================
# Global Instance and Convenience Functions
# ============================================

# Global loader instance
_agents_loader: Optional[AgentsConfigLoader] = None


def load_agents_config(path: Optional[str] = None) -> AgentsConfig:
    """
    Load Agent configuration

    Args:
        path: Configuration file path, defaults to config/agents.yaml

    Returns:
        AgentsConfig instance
    """
    global _agents_loader

    if _agents_loader is None:
        _agents_loader = AgentsConfigLoader(path)

    return _agents_loader.load(path)


def get_agent_config(agent_name: str) -> Optional[AgentConfig]:
    """
    Get specific Agent configuration

    Args:
        agent_name: Agent name (requirement_analysis, report_generation, etc.)

    Returns:
        AgentConfig instance
    """
    global _agents_loader

    if _agents_loader is None:
        _agents_loader = AgentsConfigLoader()
        _agents_loader.load()

    return _agents_loader.get_agent_config(agent_name)


def get_agents_loader() -> AgentsConfigLoader:
    """
    Get global Agent configuration loader

    Returns:
        AgentsConfigLoader instance
    """
    global _agents_loader

    if _agents_loader is None:
        _agents_loader = AgentsConfigLoader()

    return _agents_loader


def reload_agents_config() -> AgentsConfig:
    """
    Reload Agent configuration

    Returns:
        AgentsConfig instance
    """
    global _agents_loader

    if _agents_loader is None:
        _agents_loader = AgentsConfigLoader()

    return _agents_loader.reload()
