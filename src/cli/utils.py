"""CLI shared utilities."""
import logging
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

def setup_cli_logging(verbose: bool = False, log_file: Optional[str] = None) -> None:
    """Configure CLI logging system."""
    log_level = logging.DEBUG if verbose else logging.INFO
    if log_file is None:
        log_dir = Path(__file__).resolve().parent.parent.parent / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = str(log_dir / "zensers.log")
    else:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding='utf-8'),
        ]
    )
    logging.getLogger("src.core.orchestrator").setLevel(log_level)
    logging.getLogger("src.core.agents").setLevel(log_level)
    logging.getLogger("src.core.execution").setLevel(log_level)
    logging.getLogger("src.skills").setLevel(log_level)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)
    logging.info(f"Logging system initialized, log file: {log_file}")

API_BASE_URL: str = ""

def set_api_base_url(url: str) -> None:
    global API_BASE_URL
    API_BASE_URL = url.rstrip("/")

def get_api_base_url() -> str:
    return API_BASE_URL or _detect_api_base_url()

def _detect_api_base_url() -> str:
    import os
    return os.environ.get("ZENSERS_API_URL", "http://localhost:8000").rstrip("/")

import json as _json
from dataclasses import dataclass, asdict

@dataclass
class CLIConfig:
    default_output_format: str = "markdown"
    auto_save_reports: bool = True
    max_concurrent_tasks: int = 3
    api_base_url: str = ""
    default_language: str = "zh"

    @classmethod
    def load(cls) -> "CLIConfig":
        config_path = Path.home() / ".zensers" / "config.json"
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = _json.load(f)
                return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
            except Exception:
                pass
        return cls()

    def save(self) -> None:
        config_path = Path.home() / ".zensers" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            _json.dump(asdict(self), f, indent=2, ensure_ascii=False)

    @staticmethod
    def config_path() -> Path:
        return Path.home() / ".zensers" / "config.json"


_output_json: bool = False

def set_output_json(value: bool) -> None:
    global _output_json
    _output_json = value

def is_output_json() -> bool:
    return _output_json
