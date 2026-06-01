import re
import os
import time
from pathlib import Path
from datetime import date
from typing import Optional
from dataclasses import dataclass

import httpx

# ================================================================
# 配置
# ================================================================

_DEFAULT_VERSION_FILE = Path(__file__).resolve().parent.parent.parent / "VERSION"
VERSION_FILE = Path(os.getenv("ZENSERS_VERSION_FILE", str(_DEFAULT_VERSION_FILE)))

GITHUB_OWNER = os.getenv("GITHUB_OWNER", "YOUR_ORG")
GITHUB_REPO = os.getenv("GITHUB_REPO", "zensers")
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"

GITEE_OWNER = os.getenv("GITEE_OWNER", "")
GITEE_REPO = os.getenv("GITEE_REPO", "")
GITEE_API_URL = f"https://gitee.com/api/v5/repos/{GITEE_OWNER}/{GITEE_REPO}/releases/latest"

_REMOTE_CACHE: dict = {
    "data": None,
    "etag": None,
    "timestamp": 0,
}
CACHE_TTL = 600
REQUEST_TIMEOUT = 5


# ================================================================
# 数据模型
# ================================================================

@dataclass
class VersionInfo:
    local_version: str
    remote_version: str = ""
    build_date: str = ""
    is_latest: Optional[bool] = True
    check_error: Optional[str] = None
    changelog_url: str = "/api/v1/changelog"
    release_url: str = ""
    release_notes: str = ""
    desktop_download_url: str = ""
    published_at: str = ""

    def to_dict(self) -> dict:
        return {
            "local_version": self.local_version,
            "remote_version": self.remote_version,
            "build_date": self.build_date,
            "is_latest": self.is_latest,
            "check_error": self.check_error,
            "changelog_url": self.changelog_url,
            "release_url": self.release_url,
            "release_notes": self.release_notes,
            "desktop_download_url": self.desktop_download_url,
            "published_at": self.published_at,
        }


# ================================================================
# 版本号读取
# ================================================================

def get_local_version() -> str:
    env_ver = os.getenv("ZENSERS_VERSION")
    if env_ver:
        return env_ver

    try:
        version = VERSION_FILE.read_text(encoding="utf-8").strip()
        if re.match(r"^\d+\.\d+\.\d+", version):
            return version
    except (FileNotFoundError, OSError):
        pass

    try:
        from src import __version__
        if __version__:
            return __version__
    except (ImportError, AttributeError):
        pass

    return "0.0.0"


def get_build_date() -> str:
    return os.getenv("BUILD_DATE", date.today().isoformat())


# ================================================================
# SemVer 对比 (含 Pre-release)
# ================================================================

def _parse_prerelease(segment: str) -> list:
    if not segment:
        return [float("inf")]
    parts = []
    for p in segment.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(p)
    return parts


def _cmp_prerelease(p1: list, p2: list) -> int:
    for x in p1 + p2:
        if not isinstance(x, (int, str)):
            raise TypeError(
                f"prerelease identifiers must be int or str, got {type(x).__name__}: {x}"
            )

    max_len = max(len(p1), len(p2))
    for i in range(max_len):
        if i >= len(p1):
            return -1
        if i >= len(p2):
            return 1
        a, b = p1[i], p2[i]
        if type(a) != type(b):
            return -1 if isinstance(a, int) else 1
        if a < b:
            return -1
        if a > b:
            return 1
    return 0


def compare_versions(v1: str, v2: str) -> int:
    parts1 = v1.split("-", 1)
    parts2 = v2.split("-", 1)

    main1 = parts1[0]
    main2 = parts2[0]
    pre1 = parts1[1] if len(parts1) > 1 else ""
    pre2 = parts2[1] if len(parts2) > 1 else ""

    def parse_main(v: str) -> tuple:
        nums = []
        for p in v.split("."):
            try:
                nums.append(int(p))
            except ValueError:
                nums.append(0)
        while len(nums) < 3:
            nums.append(0)
        return tuple(nums[:3])

    t1, t2 = parse_main(main1), parse_main(main2)

    if t1 > t2:
        return 1
    if t1 < t2:
        return -1

    if not pre1 and not pre2:
        return 0
    if not pre1:
        return 1
    if not pre2:
        return -1

    return _cmp_prerelease(
        _parse_prerelease(pre1),
        _parse_prerelease(pre2),
    )


# ================================================================
# 远程版本获取 (含缓存 + 多源回退)
# ================================================================

async def _fetch_github() -> tuple:
    headers = {"Accept": "application/vnd.github.v3+json"}
    if _REMOTE_CACHE["etag"]:
        headers["If-None-Match"] = _REMOTE_CACHE["etag"]

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.get(GITHUB_API_URL, headers=headers)

            if resp.status_code == 304:
                _REMOTE_CACHE["timestamp"] = time.time()
                return _REMOTE_CACHE["data"], None

            resp.raise_for_status()
            data = resp.json()
            etag = resp.headers.get("etag", "")

            result = {
                "version": data.get("tag_name", "").lstrip("v"),
                "release_notes": (data.get("body") or "")[:500],
                "release_url": data.get("html_url", ""),
                "published_at": (data.get("published_at") or "")[:10] if data.get("published_at") else "",
                "source": "github",
            }

            _REMOTE_CACHE["data"] = result
            _REMOTE_CACHE["etag"] = etag
            _REMOTE_CACHE["timestamp"] = time.time()

            return result, None

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            if _REMOTE_CACHE["data"]:
                return _REMOTE_CACHE["data"], "rate_limited"
            return None, "rate_limited"
        return None, "network_error"
    except Exception:
        return None, "network_error"


async def _fetch_gitee() -> tuple:
    if not GITEE_OWNER or not GITEE_REPO:
        return None, "not_configured"

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.get(GITEE_API_URL)
            resp.raise_for_status()
            data = resp.json()
            result = {
                "version": data.get("tag_name", "").lstrip("v"),
                "release_notes": (data.get("body") or "")[:500],
                "release_url": data.get("html_url", ""),
                "published_at": (data.get("created_at") or "")[:10] if data.get("created_at") else "",
                "source": "gitee",
            }
            return result, None
    except Exception:
        return None, "network_error"


def _get_cached_remote() -> Optional[dict]:
    if _REMOTE_CACHE["data"] and time.time() - _REMOTE_CACHE["timestamp"] < CACHE_TTL:
        return _REMOTE_CACHE["data"]
    return None


async def fetch_remote_version() -> tuple:
    cached = _get_cached_remote()
    if cached:
        return cached, None

    github_data, github_err = await _fetch_github()
    if github_data:
        return github_data, github_err

    gitee_data, gitee_err = await _fetch_gitee()
    if gitee_data:
        return gitee_data, None

    if _REMOTE_CACHE["data"]:
        return _REMOTE_CACHE["data"], "remote_unreachable"

    return None, "remote_unreachable"


# ================================================================
# 主入口
# ================================================================

async def get_version_info() -> VersionInfo:
    local_ver = get_local_version()
    build_date = get_build_date()

    info = VersionInfo(
        local_version=local_ver,
        build_date=build_date,
    )

    remote, error = await fetch_remote_version()
    if remote:
        remote_ver = remote["version"]
        info.remote_version = remote_ver
        info.release_notes = remote.get("release_notes", "")
        info.release_url = remote.get("release_url", "")
        info.published_at = remote.get("published_at", "")

        source = remote.get("source", "github")
        if source == "gitee":
            info.desktop_download_url = (
                f"https://gitee.com/{GITEE_OWNER}/{GITEE_REPO}/"
                f"releases/download/v{remote_ver}/zensers-desktop-v{remote_ver}.zip"
            )
        else:
            info.desktop_download_url = (
                f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/"
                f"releases/download/v{remote_ver}/zensers-desktop-v{remote_ver}.zip"
            )

        cmp = compare_versions(local_ver, remote_ver)
        info.is_latest = (cmp >= 0)

        if error:
            info.check_error = error
            info.is_latest = None
    else:
        info.is_latest = None
        info.check_error = error

    return info
