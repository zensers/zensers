"""
MCP Security Utilities

Secure credential storage with keyring and encrypted file fallback.
Supports credential rotation scheduling and audit.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class SecureCredentialStorage:
    """
    Secure storage for MCP credentials.

    Storage hierarchy (first available is used):
    1. OS keyring — system-level secure storage
    2. Encrypted file — encrypted JSON file as fallback
    3. Environment variables — for system-level only (read-only)

    Usage:
        storage = SecureCredentialStorage(encryption_key=os.urandom(32))
        storage.store("wind", {"api_key": "secret"})
        cred = storage.retrieve("wind")
    """

    def __init__(self, encryption_key: Optional[bytes] = None, storage_dir: str = "data"):
        self._encryption_key = encryption_key
        self._storage_file = Path(storage_dir) / "credentials.enc"
        self._storage_dir = Path(storage_dir)
        self._keyring_service = "mcp_credentials"

    def store(self, server_name: str, credential: Dict[str, Any]) -> bool:
        """Store a credential securely. Returns True if successful."""
        # Try OS keyring first (cross-platform secure storage)
        if self._store_keyring(server_name, credential):
            return True

        # Fallback to encrypted file
        if self._encryption_key:
            return self._store_encrypted(server_name, credential)

        logger.warning(f"No secure storage available for {server_name}")
        return False

    def retrieve(self, server_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve a credential from secure storage."""
        # Try keyring first
        cred = self._retrieve_keyring(server_name)
        if cred:
            return cred

        # Fallback to encrypted file
        if self._encryption_key:
            return self._retrieve_encrypted(server_name)

        return None

    def delete(self, server_name: str) -> bool:
        """Delete a stored credential."""
        deleted = False

        try:
            import keyring
            try:
                keyring.delete_password(self._keyring_service, server_name)
                deleted = True
            except keyring.errors.PasswordDeleteError:
                pass
        except ImportError:
            pass

        # Also try encrypted file
        if self._storage_file.exists():
            try:
                data = self._load_encrypted_file()
                data.pop(server_name, None)
                self._save_encrypted_file(data)
                deleted = True
            except Exception:
                pass

        return deleted

    def list_servers(self) -> List[str]:
        """List all servers with stored credentials."""
        servers = set()

        # Try keyring
        try:
            import keyring
            # keyring doesn't support listing, skip
        except ImportError:
            pass

        # Try encrypted file
        if self._storage_file.exists():
            try:
                data = self._load_encrypted_file()
                servers.update(data.keys())
            except Exception:
                pass

        return list(servers)

    def _store_keyring(self, server_name: str, credential: Dict[str, Any]) -> bool:
        """Store credential using OS keyring"""
        try:
            import keyring
            keyring.set_password(
                self._keyring_service,
                server_name,
                json.dumps(credential),
            )
            return True
        except ImportError:
            logger.debug("keyring not available, using encrypted file fallback")
            return False
        except Exception as e:
            logger.warning(f"keyring storage failed: {e}")
            return False

    def _retrieve_keyring(self, server_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve credential from OS keyring"""
        try:
            import keyring
            data = keyring.get_password(self._keyring_service, server_name)
            if data:
                return json.loads(data)
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"keyring retrieval failed: {e}")
        return None

    def _store_encrypted(self, server_name: str, credential: Dict[str, Any]) -> bool:
        """Store credential in encrypted file"""
        try:
            from cryptography.fernet import Fernet

            self._storage_dir.mkdir(parents=True, exist_ok=True)
            data = self._load_encrypted_file()
            data[server_name] = credential

            f = Fernet(self._encryption_key)
            encrypted = f.encrypt(json.dumps(data).encode())
            self._storage_file.write_bytes(encrypted)
            return True
        except Exception as e:
            logger.error(f"Encrypted storage failed: {e}")
            return False

    def _retrieve_encrypted(self, server_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve credential from encrypted file"""
        try:
            from cryptography.fernet import Fernet

            if not self._storage_file.exists():
                return None

            f = Fernet(self._encryption_key)
            data = json.loads(f.decrypt(self._storage_file.read_bytes()))
            return data.get(server_name)
        except Exception as e:
            logger.error(f"Encrypted retrieval failed: {e}")
            return None

    def _load_encrypted_file(self) -> Dict[str, Any]:
        """Load and decrypt the entire credential file"""
        if not self._storage_file.exists():
            return {}
        from cryptography.fernet import Fernet
        f = Fernet(self._encryption_key)
        return json.loads(f.decrypt(self._storage_file.read_bytes()))

    def _save_encrypted_file(self, data: Dict[str, Any]) -> None:
        """Encrypt and save the entire credential file"""
        from cryptography.fernet import Fernet
        f = Fernet(self._encryption_key)
        self._storage_file.write_bytes(f.encrypt(json.dumps(data).encode()))


class CredentialRotationManager:
    """
    Manages credential rotation schedules and notifications.

    Tracks when each server's credentials were last rotated
    and notifies when rotation is due.
    """

    def __init__(self, storage_path: str = "data"):
        self._path = Path(storage_path)
        self._path.mkdir(parents=True, exist_ok=True)
        self._schedule_file = self._path / "rotation_schedule.json"
        self._schedule: Dict[str, Dict[str, Any]] = self._load_schedule()

    def schedule_rotation(self, server_name: str, interval_days: int) -> None:
        """Schedule automatic rotation reminder for a server"""
        self._schedule[server_name] = {
            "last_rotation": datetime.now().isoformat(),
            "interval_days": interval_days,
            "next_rotation": (datetime.now() + timedelta(days=interval_days)).isoformat(),
        }
        self._save_schedule()

    def check_rotation_needed(self) -> List[str]:
        """Check which servers need credential rotation"""
        now = datetime.now()
        needs_rotation = []
        for server_name, info in self._schedule.items():
            next_date = datetime.fromisoformat(info["next_rotation"])
            if now >= next_date:
                needs_rotation.append(server_name)
        return needs_rotation

    def mark_rotated(self, server_name: str) -> None:
        """Mark a server's credentials as rotated"""
        info = self._schedule.get(server_name)
        if info:
            interval = info["interval_days"]
            self.schedule_rotation(server_name, interval)

    def _load_schedule(self) -> Dict[str, Dict[str, Any]]:
        if self._schedule_file.exists():
            try:
                return json.loads(self._schedule_file.read_text())
            except Exception:
                pass
        return {}

    def _save_schedule(self) -> None:
        self._schedule_file.write_text(json.dumps(self._schedule, indent=2))
