"""
HTTPSkill - HTTP Request Skill

Provides HTTP operations such as GET/POST, with timeout and error handling.

Security features:
- SSRF protection: blocks internal network addresses
- URL protocol whitelist: only http/https allowed
- Timeout protection
"""
import ipaddress
import socket
from typing import Any, Dict, Optional, Set
from urllib.parse import urlparse

from src.skills.base import Skill, SkillConfig


# Allowed URL schemes
ALLOWED_SCHEMES: Set[str] = {"http", "https"}


def _is_private_hostname(hostname: str) -> bool:
    """
    Check if hostname resolves to a private IP address
    
    Args:
        hostname: The hostname
        
    Returns:
        Whether it is a private address
    """
    if not hostname:
        return True
    
    try:
        # Try to resolve the hostname
        ip_str = socket.gethostbyname(hostname)
        ip = ipaddress.ip_address(ip_str)
        
        # Check if it is a private/reserved address
        return ip.is_private or ip.is_loopback or ip.is_reserved
        
    except socket.gaierror:
        # Could not resolve, possibly invalid hostname
        return False
    except ValueError:
        return False


def _validate_url(url: str) -> tuple[bool, str]:
    """
    Validate whether a URL is safe (SSRF protection)
    
    Args:
        url: The URL to validate
        
    Returns:
        (is_safe, error_message)
    """
    if not url:
        return False, "URL cannot be empty"
    
    try:
        parsed = urlparse(url)
        
        # Check scheme
        if parsed.scheme not in ALLOWED_SCHEMES:
            return False, f"Disallowed scheme: {parsed.scheme}, only {', '.join(ALLOWED_SCHEMES)} supported"
        
        # Check hostname
        if not parsed.hostname:
            return False, "URL missing hostname"
        
        # Check if private address
        if _is_private_hostname(parsed.hostname):
            return False, f"Internal network address not allowed: {parsed.hostname}"
        
        return True, ""
        
    except Exception as e:
        return False, f"URL validation failed: {str(e)}"


class HTTPSkill(Skill):
    """
    HTTP Request Skill

    Supported operations:
    - get: GET request
    - post: POST request
    
    Security features:
    - SSRF protection: blocks internal network addresses
    - URL scheme whitelist
    - Timeout protection
    """

    DEFAULT_TIMEOUT = 30
    DEFAULT_USER_AGENT = "Zensers/1.0"

    @property
    def name(self) -> str:
        return "http_skill"

    @property
    def description(self) -> str:
        return "HTTP request operations, supports GET/POST with timeout, SSRF protection and error handling"

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Execute an HTTP request

        Args:
            action: Request method (get/post)
            url: Request URL
            payload: Request body (used for post)
            headers: Custom request headers
            timeout: Timeout in seconds (default 30, max 300)
            return_json: Whether to parse JSON response (default True)

        Returns:
            Request result dictionary
        """
        action = kwargs.get("action", "")
        url = kwargs.get("url", "")
        payload = kwargs.get("payload")
        headers = kwargs.get("headers", {})
        timeout = kwargs.get("timeout", self.DEFAULT_TIMEOUT)
        return_json = kwargs.get("return_json", False)

        if action not in ("get", "post"):
            return self._failure(f"Unsupported HTTP method: {action}")

        if not url:
            return self._failure("URL cannot be empty")

        # Validate timeout parameter
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            timeout = self.DEFAULT_TIMEOUT
        elif timeout > 300:  # Max 5 minutes
            timeout = 300

        # SSRF security validation
        is_safe, error = _validate_url(url)
        if not is_safe:
            return self._failure(error, "URL security validation failed")

        try:
            return await self._request(action, url, payload, headers, timeout, return_json)
        except Exception as e:
            return self._failure(str(e), "HTTP request failed")

    async def _request(
        self,
        method: str,
        url: str,
        payload: Optional[Dict],
        headers: Dict,
        timeout: int,
        return_json: bool,
    ) -> Dict[str, Any]:
        """Execute the actual HTTP request"""
        import aiohttp

        merged_headers = {"User-Agent": self.DEFAULT_USER_AGENT, **headers}

        async with aiohttp.ClientSession() as session:
            request_method = getattr(session, method)
            kwargs = dict(headers=merged_headers, timeout=aiohttp.ClientTimeout(total=timeout))
            if method == "post" and payload is not None:
                kwargs["json"] = payload

            async with request_method(url, **kwargs) as resp:
                status = resp.status
                if return_json:
                    body = await resp.json()
                else:
                    body = await resp.text()

                if status >= 400:
                    return self._failure(
                        f"HTTP {status}",
                        f"Request failed: {url}",
                    ) | {"status_code": status}

                return self._success(
                    {"status_code": status, "body": body},
                    f"HTTP {status} OK",
                )

