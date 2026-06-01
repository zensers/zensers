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
