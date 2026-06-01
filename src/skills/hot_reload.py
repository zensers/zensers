"""
Skill hot reload module

Supports dynamically adding/updating/uninstalling Skills at runtime without restarting the system.

Core capabilities:
  - Scan directory at startup, register all existing Skills
  - watchdog listens for file system events:
      * New *_skill.py  → auto-register
      * Modified *_skill.py  → auto-reload (new class replaces old)
      * Deleted *_skill.py  → auto-unregister
  - Corrupted file safe degrade: load failure does not affect registered Skills
  - Optional on_error callback, convenient for alert system integration
  - Supports with statement (context manager)
  - Thread-safe (Lock protects registry operations)

Usage examples:
    from src.skills.hot_reload import SkillHotReloader

    # Method 1: Manual lifecycle management
    reloader = SkillHotReloader("src/skills")
    reloader.start()   # Start background listener
    ...
    reloader.stop()    # Stop listener

    # Method 2: Context manager (recommended)
    with SkillHotReloader("src/skills") as reloader:
        # reloader auto start/stop
        app.run()
"""
import importlib
import importlib.util
import inspect
import logging
import sys
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional

from watchdog.events import FileSystemEventHandler, FileSystemEvent
from watchdog.observers import Observer

from src.skills.base import Skill, SkillRegistry, get_registry

logger = logging.getLogger(__name__)

# Only listen for files with this suffix
_SKILL_SUFFIX = "_skill.py"
# Files always skipped
_SKIP_FILES = {"__init__.py", "base.py", "hot_reload.py"}


class SkillLoadError(Exception):
    """Raised when skill file fails to load"""

    def __init__(self, path: str, cause: Exception):
        super().__init__(f"Failed to load skill file: {path} — {cause}")
        self.path = path
        self.cause = cause


class _SkillEventHandler(FileSystemEventHandler):
    """watchdog event handler, forwards file system events to HotReloader"""

    def __init__(self, reloader: "SkillHotReloader"):
        self._reloader = reloader

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory and self._is_skill_file(event.src_path):
            logger.info("[HotReload] New skill file: %s", event.src_path)
            self._reloader._handle_file_created(event.src_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory and self._is_skill_file(event.src_path):
            logger.info("[HotReload] Skill file changed: %s", event.src_path)
            self._reloader._handle_file_modified(event.src_path)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory and self._is_skill_file(event.src_path):
            logger.info("[HotReload] Skill file deleted: %s", event.src_path)
            self._reloader._handle_file_deleted(event.src_path)

    @staticmethod
    def _is_skill_file(path: str) -> bool:
        name = Path(path).name
        return name.endswith(_SKILL_SUFFIX) and name not in _SKIP_FILES


class SkillHotReloader:
    """
    Skill hot reload manager

    Args:
        skill_dir:  Skill directory path to watch (must exist)
        registry:   SkillRegistry to use, defaults to global singleton
        on_error:   Load failure callback on_error(path: str, exc: Exception)
    """

    def __init__(
        self,
        skill_dir: str,
        registry: Optional[SkillRegistry] = None,
        on_error: Optional[Callable[[str, Exception], None]] = None,
    ):
        p = Path(skill_dir)
        if not p.exists():
            raise ValueError(f"Skill directory does not exist: {skill_dir}")

        self.skill_dir = str(p.resolve())
        self.registry = registry if registry is not None else get_registry()
        self._on_error = on_error

        self._observer: Optional[Observer] = None
        self._running = False
        self._lock = threading.RLock()  # Use reentrant lock to avoid nested call deadlocks

        # path → skill_name mapping, used to look up skill name on deletion
        self._path_to_skill: Dict[str, str] = {}

    # ─────────────────── Lifecycle ───────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        """Start hot reload (initial scan + background listen), idempotent"""
        with self._lock:
            if self._running:
                return  # Already started, safely ignored

            # 1. Initial full scan
            self.scan_and_load()

            # 2. Start watchdog background thread
            handler = _SkillEventHandler(self)
            self._observer = Observer()
            self._observer.schedule(handler, self.skill_dir, recursive=False)
            self._observer.start()
            self._running = True
            logger.info("[HotReload] Listener started: %s", self.skill_dir)

    def stop(self) -> None:
        """Stop hot reload, idempotent"""
        with self._lock:
            if not self._running:
                return
            if self._observer:
                self._observer.stop()
                # join may hang on Windows, use very short timeout + background cleanup
                try:
                    self._observer.join(timeout=0.5)
                except Exception:
                    pass
                self._observer = None
            self._running = False
            logger.info("[HotReload] Listener stopped")

    def __enter__(self) -> "SkillHotReloader":
        self.start()
        return self

    def __exit__(self, *_) -> None:
        self.stop()

    # ─────────────────── Scan & Load ───────────────────

    def scan_and_load(self) -> int:
        """
        Scan directory, load all valid skill files.

        Returns:
            Number of successfully loaded Skills
        """
        count = 0
        for path in sorted(Path(self.skill_dir).glob("*_skill.py")):
            if path.name in _SKIP_FILES:
                continue
            try:
                self._load_skill_file(str(path))
                count += 1
            except SkillLoadError as e:
                logger.warning("[HotReload] Skipping corrupted file: %s — %s", path, e.cause)
                self._fire_error(str(path), e)
        return count

    def _load_skill_file(self, file_path: str) -> None:
        """
        Dynamically import specified file, find Skill subclasses and register to Registry.

        Args:
            file_path: Skill file absolute path

        Raises:
            SkillLoadError: When there's a syntax error or no Skill subclass found
        """
        path = Path(file_path)
        module_name = f"_hot_skill_{path.stem}_{id(path)}"  # Unique module name, supports reload

        try:
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                raise ImportError("Failed to create module spec")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)  # type: ignore[union-attr]
        except Exception as e:
            # Clean sys.modules to avoid pollution
            sys.modules.pop(module_name, None)
            raise SkillLoadError(file_path, e) from e

        # Find all Skill subclasses in module (excluding base class itself)
        skill_classes = [
            cls
            for _, cls in inspect.getmembers(module, inspect.isclass)
            if issubclass(cls, Skill) and cls is not Skill
            and cls.__module__ == module_name
        ]

        if not skill_classes:
            sys.modules.pop(module_name, None)
            raise SkillLoadError(
                file_path, ValueError("No Skill subclass found in file")
            )

        # Register (take first, typically one Skill per file)
        skill_cls = skill_classes[0]
        # Use instance's name property as registration key (requires temporary instantiation)
        try:
            tmp = skill_cls.__new__(skill_cls)
            skill_name = tmp.name  # Call @property
        except Exception:
            # Fallback to filename inference
            skill_name = path.stem.replace("_skill", "")

        with self._lock:
            self.registry.register(skill_name, skill_cls)
            self._path_to_skill[str(path.resolve())] = skill_name

        logger.info("[HotReload] Register Skill: %s ← %s", skill_name, path.name)

    # ─────────────────── Event Handling ───────────────────

    def _handle_file_created(self, file_path: str) -> None:
        try:
            self._load_skill_file(file_path)
        except SkillLoadError as e:
            logger.error("[HotReload] New file load failed: %s", e)
            self._fire_error(file_path, e)

    def _handle_file_modified(self, file_path: str) -> None:
        """Modify = unregister old version first, then load new version"""
        # First clear old module cache (prevent Python from caching old code)
        abs_path = str(Path(file_path).resolve())
        with self._lock:
            old_name = self._path_to_skill.get(abs_path)
        if old_name:
            self.registry.unregister(old_name)

        # Then load new version
        try:
            self._load_skill_file(file_path)
        except SkillLoadError as e:
            logger.error("[HotReload] File reload failed: %s", e)
            self._fire_error(file_path, e)

    def _handle_file_deleted(self, file_path: str) -> None:
        abs_path = str(Path(file_path).resolve())
        with self._lock:
            skill_name = self._path_to_skill.pop(abs_path, None)
        if skill_name:
            self.registry.unregister(skill_name)
            logger.info("[HotReload] Unregister Skill: %s", skill_name)

    # ─────────────────── Status Query ───────────────────

    def list_loaded(self) -> List[str]:
        """Return list of skill names registered via hot reloader"""
        with self._lock:
            return list(self._path_to_skill.values())

    @property
    def loaded_count(self) -> int:
        """Loaded skill count"""
        with self._lock:
            return len(self._path_to_skill)

    # ─────────────────── Internal Utilities ───────────────────

    def _fire_error(self, path: str, exc: Exception) -> None:
        """Trigger error callback (if any)"""
        if self._on_error:
            try:
                self._on_error(path, exc)
            except Exception:
                pass  # Callback error does not affect main flow
