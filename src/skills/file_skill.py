"""
FileSkill - File read/write Skill

Provides file read, write, list, delete and other operations.

Security notes:
- By default restricted to data/ directory
- Allowed directories can be configured via allowed_base_dirs
- Access to sensitive system directories is forbidden
"""
import json
import platform
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from src.skills.base import Skill, SkillConfig


# Default allowed base directories
DEFAULT_ALLOWED_DIRS: Set[str] = {
    "data",
    "output",
    "cache",
    "temp",
}

# Forbidden sensitive system directories
# Unix system directories
FORBIDDEN_UNIX_DIRS: Set[str] = {
    "/etc", "/root", "/var/log", "/sys", "/proc",
}

# Windows system directories
FORBIDDEN_WINDOWS_DIRS: Set[str] = {
    "C:\\Windows", "C:\\Program Files", "C:\\Program Files (x86)",
}

# Select forbidden directories based on OS
_IS_WINDOWS = platform.system() == "Windows"
FORBIDDEN_DIRS: Set[str] = FORBIDDEN_WINDOWS_DIRS if _IS_WINDOWS else FORBIDDEN_UNIX_DIRS


def _is_safe_path(filepath: str, allowed_dirs: Set[str]) -> tuple[bool, str]:
    """
    Verify if path is safe
    
    Args:
        filepath: Path to verify
        allowed_dirs: Set of allowed base directories
        
    Returns:
        (is_safe, error_message)
    """
    if not filepath:
        return False, "Path cannot be empty"
    
    try:
        # 解析为绝对路径
        abs_path = Path(filepath).resolve()
        
        # 检查是否在禁止目录内
        for forbidden in FORBIDDEN_DIRS:
            forbidden_path = Path(forbidden)
            try:
                abs_path.relative_to(forbidden_path)
                return False, f"Forbidden system directory: {forbidden}"
            except ValueError:
                continue
        
        # Check if within allowed directories
        cwd = Path.cwd()
        for allowed in allowed_dirs:
            # Support relative and absolute paths
            if Path(allowed).is_absolute():
                allowed_path = Path(allowed)
            else:
                allowed_path = cwd / allowed
            
            try:
                abs_path.relative_to(allowed_path.resolve())
                return True, ""
            except ValueError:
                continue
        
        return False, f"Path is outside allowed range. Allowed directories: {', '.join(allowed_dirs)}"
        
    except Exception as e:
        return False, f"Path validation failed: {str(e)}"


class FileSkill(Skill):
    """
    File read/write Skill

    Supported operations:
    - read: Read text file
    - write: Write text file
    - read_json: Read JSON file
    - write_json: Write JSON file
    - list: List directory contents
    - delete: Delete file or directory
    
    Security features:
    - Path traversal protection
    - System directory access restriction
    - Configurable allowed directory whitelist
    """

    def __init__(self, config: Optional[SkillConfig] = None, allowed_dirs: Optional[List[str]] = None):
        """
        Initialize file skill
        
        Args:
            config: Skill configuration
            allowed_dirs: List of allowed directories, defaults to data/, output/, cache/, temp/
        """
        super().__init__(config)
        self._allowed_dirs: Set[str] = set(allowed_dirs) if allowed_dirs else DEFAULT_ALLOWED_DIRS

    @property
    def name(self) -> str:
        return "file_skill"

    @property
    def description(self) -> str:
        return "File read/write operations, supporting text and JSON formats. By default restricted to data/, output/, cache/, temp/ directories."

    def _validate_path(self, filepath: str) -> tuple[bool, str]:
        """Verify if path is safe"""
        return _is_safe_path(filepath, self._allowed_dirs)

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Execute file operation

        Args:
            action: Operation type (read/write/read_json/write_json/list/delete)
            filepath: File or directory path
            content: Content to write (required for write/write_json)
            encoding: Encoding (default utf-8)

        Returns:
            Operation result dict
        """
        action = kwargs.get("action", "")
        filepath = kwargs.get("filepath", "")
        content = kwargs.get("content")
        encoding = kwargs.get("encoding", "utf-8")

        handlers = {
            "read": self._read,
            "write": self._write,
            "read_json": self._read_json,
            "write_json": self._write_json,
            "list": self._list_dir,
            "delete": self._delete,
        }

        handler = handlers.get(action)
        if handler is None:
            return self._failure(f"Unknown action: {action}", "Unsupported file operation")

        try:
            return await handler(filepath, content, encoding)
        except PermissionError as e:
            return self._failure(f"Insufficient permissions: {e}")
        except FileNotFoundError as e:
            return self._failure(f"File not found: {e}")
        except json.JSONDecodeError as e:
            return self._failure(f"JSON parse error: {e}")
        except Exception as e:
            return self._failure(str(e))

    async def _read(self, filepath: str, content: Any, encoding: str) -> Dict[str, Any]:
        """Read text file"""
        # Safety validation
        is_safe, error = self._validate_path(filepath)
        if not is_safe:
            return self._failure(error, "Path validation failed")
        
        path = Path(filepath)
        if not path.exists():
            return self._failure(f"File not found: {filepath}")
        if not path.is_file():
            return self._failure(f"Not a file: {filepath}")
        text = path.read_text(encoding=encoding)
        return self._success({"content": text})

    async def _write(self, filepath: str, content: Any, encoding: str) -> Dict[str, Any]:
        """Write text file (auto-create directory)"""
        # Safety validation
        is_safe, error = self._validate_path(filepath)
        if not is_safe:
            return self._failure(error, "Path validation failed")
        
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(content), encoding=encoding)
        return self._success({"filepath": filepath}, "Write successful")

    async def _read_json(self, filepath: str, content: Any, encoding: str) -> Dict[str, Any]:
        """Read JSON file"""
        # Safety validation
        is_safe, error = self._validate_path(filepath)
        if not is_safe:
            return self._failure(error, "Path validation failed")
        
        path = Path(filepath)
        if not path.exists():
            return self._failure(f"File not found: {filepath}")
        if not path.is_file():
            return self._failure(f"Not a file: {filepath}")
        data = json.loads(path.read_text(encoding=encoding))
        return self._success({"content": data})

    async def _write_json(self, filepath: str, content: Any, encoding: str) -> Dict[str, Any]:
        """Write JSON file"""
        # Safety validation
        is_safe, error = self._validate_path(filepath)
        if not is_safe:
            return self._failure(error, "Path validation failed")
        
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding=encoding)
        return self._success({"filepath": filepath}, "JSON write successful")

    async def _list_dir(self, filepath: str, content: Any, encoding: str) -> Dict[str, Any]:
        """List directory contents"""
        # Safety validation
        is_safe, error = self._validate_path(filepath)
        if not is_safe:
            return self._failure(error, "Path validation failed")
        
        path = Path(filepath)
        if not path.is_dir():
            return self._failure(f"Directory not found: {filepath}")
        files = [
            {
                "name": f.name,
                "is_dir": f.is_dir(),
                "size": f.stat().st_size if f.is_file() else 0,
            }
            for f in path.iterdir()
        ]
        return self._success({"files": files, "count": len(files)})

    async def _delete(self, filepath: str, content: Any, encoding: str) -> Dict[str, Any]:
        """Delete file or directory"""
        # Safety validation
        is_safe, error = self._validate_path(filepath)
        if not is_safe:
            return self._failure(error, "Path validation failed")
        
        path = Path(filepath)
        if not path.exists():
            return self._failure(f"Path not found: {filepath}")
        
        # Safety check: forbids deleting non-empty directories
        if path.is_dir():
            # Check if directory is empty
            if any(path.iterdir()):
                return self._failure(f"Directory not empty, refusing to delete: {filepath}", "Please clear the directory contents first")
            path.rmdir()
        else:
            path.unlink()
        return self._success({"filepath": filepath}, "Deleted successfully")
