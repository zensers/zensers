"""
MCP Credential Manager

Manages authentication credentials for all MCP servers.
Supports multi-level credential sources with priority stacking.

Priority order: session > user > system
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from threading import Lock

from .config import AuthConfig, AuthType

logger = logging.getLogger(__name__)


@dataclass
class Credential:
    """A single credential entry for an MCP server"""
    server_name: str
    auth: AuthConfig
    source: str  # "system" | "user" | "session"
    expires_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)


class CredentialManager:
    """
    Manages credentials for all MCP servers.

    Resolution priority: session > user > system
    Supports OAuth token refresh and audit logging.
    """

    PRIORITY_ORDER = {"session": 0, "user": 1, "system": 2}

    def __init__(self):
        self._credentials: Dict[str, List[Credential]] = {}
        self._effective_cache: Dict[str, Optional[AuthConfig]] = {}
        self._lock = Lock()
        self._audit_log: List[Dict] = []

    def register_system(self, server_name: str, auth: AuthConfig) -> None:
        """Register system-level credentials from config file or environment variables"""
        self._add_credential(server_name, auth, "system")

    def register_user(self, server_name: str, auth: AuthConfig) -> None:
        """Register user-level credentials provided during login"""
        self._add_credential(server_name, auth, "user")

    def register_session(self, server_name: str, auth: AuthConfig) -> None:
        """Register session-level credentials injected at runtime"""
        self._add_credential(server_name, auth, "session")

    def _add_credential(self, server_name: str, auth: AuthConfig, source: str) -> None:
        """Add a credential, replacing any existing one from the same source"""
        with self._lock:
            if server_name not in self._credentials:
                self._credentials[server_name] = []

            # Remove existing credential from the same source to prevent duplicates
            self._credentials[server_name] = [
                c for c in self._credentials[server_name]
                if c.source != source
            ]

            cred = Credential(server_name=server_name, auth=auth, source=source)
            self._credentials[server_name].append(cred)

            # Invalidate cache
            self._effective_cache.pop(server_name, None)

        self._log_access(server_name, "register", source)

    def get_auth(self, server_name: str) -> Optional[AuthConfig]:
        """
        Get effective credentials for a server.

        Priority: session > user > system
        Expired credentials are skipped.
        Results are cached until invalidated by a new registration.
        """
        with self._lock:
            # Check cache first
            if server_name in self._effective_cache:
                self._log_access(server_name, "get", "cache")
                return self._effective_cache[server_name]

            creds = self._credentials.get(server_name, [])
            if not creds:
                return None

            # Sort by priority: session > user > system
            # Return the highest-priority non-expired credential
            for cred in sorted(creds, key=lambda c: self.PRIORITY_ORDER.get(c.source, 99)):
                if cred.expires_at and cred.expires_at <= datetime.now():
                    continue
                self._effective_cache[server_name] = cred.auth
                self._log_access(server_name, "get", cred.source)
                return cred.auth

            return None

    async def refresh(self, server_name: str) -> bool:
        """
        Refresh OAuth token for a server.

        Returns True if refresh succeeded, False otherwise.
        Only works for OAuth-type credentials.
        """
        auth = self.get_auth(server_name)
        if not auth or auth.type != AuthType.OAUTH:
            return False

        try:
            new_token = await self._oauth_refresh(auth)
            if new_token and "access_token" in new_token:
                auth.token = new_token["access_token"]
                expires_in = new_token.get("expires_in", 3600)
                # Update the credential's expiration
                with self._lock:
                    creds = self._credentials.get(server_name, [])
                    for cred in creds:
                        if cred.source in ("user", "session"):
                            cred.expires_at = datetime.now() + timedelta(seconds=expires_in)
                            break
                self._log_access(server_name, "refresh", "oauth")
                return True
        except Exception as e:
            logger.error(f"OAuth refresh failed for {server_name}: {e}")

        return False

    async def _oauth_refresh(self, auth: AuthConfig) -> Optional[Dict]:
        """Perform OAuth token refresh. Override for custom providers."""
        # Default implementation: use refresh_token from auth config
        if not auth.oauth_refresh_token:
            logger.warning("No OAuth refresh token available")
            return None

        import aiohttp
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": auth.oauth_refresh_token,
            "client_id": auth.oauth_client_id,
            "client_secret": auth.oauth_client_secret,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(auth.token_url or "https://oauth2.googleapis.com/token", data=payload) as resp:
                if resp.status == 200:
                    return await resp.json()
                logger.error(f"OAuth refresh request failed: {resp.status}")
                return None

    def _log_access(self, server_name: str, action: str, source: str) -> None:
        """Log credential access for audit trail"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "server": server_name,
            "action": action,
            "source": source,
        }
        self._audit_log.append(entry)

    def get_audit_log(self, server_name: Optional[str] = None) -> List[Dict]:
        """Get audit log, optionally filtered by server name"""
        if server_name:
            return [e for e in self._audit_log if e["server"] == server_name]
        return list(self._audit_log)
