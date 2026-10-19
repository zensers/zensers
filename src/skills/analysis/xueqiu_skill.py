# -*- coding: utf-8 -*-
"""
XueqiuSkill — 雪球实时行情/热帖/热门股票 (A股/港股/美股)

内嵌 _XueqiuAuth (三层 Cookie 管理) 和 _XueqiuAPI (零外部依赖 API 客户端)。
所有同步 API 调用通过 asyncio.to_thread() 包装。
"""
import asyncio
import http.cookiejar
import json
import logging
import os
import re
import stat
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.skills.base import Skill

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path.home() / ".xueqiu-skill"
_COOKIE_FILE = _CONFIG_DIR / "cookies.json"
_REQUIRED_COOKIE = "xq_a_token"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
_REFERER = "https://xueqiu.com/"
_TIMEOUT = 10


def _make_private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    try:
        if os.name != "nt":
            os.chmod(path, stat.S_IRWXU)
    except OSError:
        pass
    return path


def _open_private(path: str, mode: str = "w"):
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                     stat.S_IRUSR | stat.S_IWUSR)
        if os.name != "nt":
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        return os.fdopen(fd, mode, encoding="utf-8")
    except OSError:
        handle = open(path, mode, encoding="utf-8")
        try:
            if os.name != "nt":
                os.chmod(path, 0o600)
        except OSError:
            pass
        return handle


class _XueqiuAuth:
    """三层 Cookie 管理（配置文件 → 浏览器 → 首页回退）"""

    def __init__(self, cookie_string: Optional[str] = None):
        self._jar = http.cookiejar.CookieJar()
        self._initialized = False
        self._auth_source: Optional[str] = None
        if cookie_string:
            self._inject(cookie_string)
            self._initialized = True
            self._auth_source = "constructor"

    @property
    def auth_source(self) -> Optional[str]:
        return self._auth_source

    @property
    def is_authenticated(self) -> bool:
        return any(c.name == _REQUIRED_COOKIE for c in self._jar)

    def _inject(self, cookie_str: str) -> None:
        for pair in cookie_str.split(";"):
            pair = pair.strip()
            if "=" not in pair:
                continue
            name, _, value = pair.partition("=")
            self._jar.set_cookie(
                http.cookiejar.Cookie(
                    version=0, name=name.strip(), value=value.strip(),
                    port=None, port_specified=False,
                    domain=".xueqiu.com", domain_specified=True,
                    domain_initial_dot=True, path="/", path_specified=True,
                    secure=True, expires=None, discard=True,
                    comment=None, comment_url=None, rest={},
                )
            )

    def cookie_header(self) -> str:
        return "; ".join(f"{c.name}={c.value}" for c in self._jar)

    @property
    def jar(self) -> http.cookiejar.CookieJar:
        return self._jar

    def _load_from_config(self) -> bool:
        if not _COOKIE_FILE.exists():
            return False
        try:
            with open(_COOKIE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            cookie_str = data.get("cookie_string", "")
            if not cookie_str:
                return False
            self._inject(cookie_str)
            return True
        except Exception:
            return False

    def save_cookies(self, cookie_string: str) -> None:
        _make_private_dir(_CONFIG_DIR)
        data = {"cookie_string": cookie_string}
        with _open_private(str(_COOKIE_FILE)) as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _load_from_browser(self, browser: str = "chrome") -> bool:
        try:
            import rookiepy
            browser_func = {
                "chrome": rookiepy.chrome, "firefox": rookiepy.firefox,
                "edge": rookiepy.edge, "brave": rookiepy.brave,
                "opera": rookiepy.opera,
            }.get(browser, rookiepy.chrome)
            raw = browser_func(domains=[".xueqiu.com"])
            if not any(c.get("name") == _REQUIRED_COOKIE for c in raw):
                return False
            for c in raw:
                name = c.get("name")
                value = c.get("value")
                if name and value is not None:
                    self._inject(f"{name}={value}")
            return True
        except ImportError:
            pass
        try:
            import browser_cookie3
            browser_func = {
                "chrome": browser_cookie3.chrome, "firefox": browser_cookie3.firefox,
                "edge": browser_cookie3.edge, "brave": browser_cookie3.brave,
                "opera": browser_cookie3.opera,
            }.get(browser, browser_cookie3.chrome)
            cookies = list(browser_func(domain_name=".xueqiu.com"))
            if not any(c.name == _REQUIRED_COOKIE for c in cookies):
                return False
            for c in cookies:
                self._jar.set_cookie(c)
            return True
        except (ImportError, Exception):
            return False

    def _load_from_homepage(self) -> bool:
        req = urllib.request.Request("https://xueqiu.com", headers={"User-Agent": _UA})
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._jar)
        )
        try:
            opener.open(req, timeout=_TIMEOUT)
            return len(self._jar) > 0
        except Exception:
            return False

    def ensure_cookies(self) -> str:
        if self._initialized:
            return self.cookie_header()
        if self._load_from_config():
            self._initialized = True
            self._auth_source = "config"
            return self.cookie_header()
        if self._load_from_browser():
            self._initialized = True
            self._auth_source = "browser"
            return self.cookie_header()
        self._load_from_homepage()
        self._initialized = True
        self._auth_source = "fallback"
        return self.cookie_header()

    def extract_from_browser(self, browser: str = "chrome") -> tuple:
        try:
            import rookiepy
        except ImportError:
            try:
                import browser_cookie3
            except ImportError:
                return False, "需要 rookiepy 或 browser_cookie3"
        jar = http.cookiejar.CookieJar()
        cookie_parts = []
        try:
            import rookiepy
            browser_func = {
                "chrome": rookiepy.chrome, "firefox": rookiepy.firefox,
                "edge": rookiepy.edge, "brave": rookiepy.brave,
                "opera": rookiepy.opera,
            }.get(browser, rookiepy.chrome)
            raw = browser_func(domains=[".xueqiu.com"])
            has_token = any(c.get("name") == _REQUIRED_COOKIE for c in raw)
            for c in raw:
                name = c.get("name")
                value = c.get("value")
                if name and value is not None:
                    cookie_parts.append(f"{name}={value}")
        except ImportError:
            import browser_cookie3
            browser_func = {
                "chrome": browser_cookie3.chrome, "firefox": browser_cookie3.firefox,
                "edge": browser_cookie3.edge, "brave": browser_cookie3.brave,
                "opera": browser_cookie3.opera,
            }.get(browser, browser_cookie3.chrome)
            cookies = list(browser_func(domain_name=".xueqiu.com"))
            has_token = any(c.name == _REQUIRED_COOKIE for c in cookies)
            for c in cookies:
                cookie_parts.append(f"{c.name}={c.value}")
        except Exception as e:
            return False, f"读取 {browser} Cookie 失败：{e}"
        if not cookie_parts:
            return False, f"在 {browser} 中未找到雪球 Cookie"
        if not has_token:
            return False, f"缺少 {_REQUIRED_COOKIE}，请先登录 xueqiu.com"
        cookie_string = "; ".join(cookie_parts)
        self.save_cookies(cookie_string)
        self._inject(cookie_string)
        self._initialized = True
        self._auth_source = "browser"
        return True, f"已保存 {len(cookie_parts)} 个 Cookie"


class _XueqiuAPIError(Exception):
    pass


class _XueqiuAPI:
    """雪球 API 客户端（零外部依赖，纯 stdlib）"""

    def __init__(self, cookie_string: Optional[str] = None):
        self._auth = _XueqiuAuth(cookie_string=cookie_string)
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._auth.jar)
        )

    @property
    def auth(self) -> _XueqiuAuth:
        return self._auth

    def _get_json(self, url: str) -> Any:
        self._auth.ensure_cookies()
        req = urllib.request.Request(url, headers={"User-Agent": _UA, "Referer": _REFERER})
        try:
            with self._opener.open(req, timeout=_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 400:
                body = ""
                try:
                    body = e.read().decode("utf-8", errors="replace")
                except Exception:
                    pass
                if '"error_code":"400016"' in body or '"error_code":400016' in body:
                    raise _XueqiuAPIError("400016") from e
                raise _XueqiuAPIError("HTTP 400 — Cookie 无效或已过期") from e
            raise _XueqiuAPIError(f"HTTP {e.code}: {e.reason}") from e
        except urllib.error.URLError as e:
            raise _XueqiuAPIError(f"网络错误：{e.reason}") from e

    def _screener_quote(self, symbol: str, limit: int = 50) -> Optional[dict]:
        market_map = {
            "SH": ("CN", "sh_sz"), "SZ": ("CN", "sh_sz"), "BJ": ("CN", "sh_sz"),
        }
        prefix = symbol[:2] if len(symbol) >= 2 else ""
        if prefix in market_map:
            market, stype = market_map[prefix]
        elif re.match(r"^\d{5,6}$", symbol):
            market, stype = "HK", "hk"
        elif re.match(r"^[A-Z]+$", symbol):
            market, stype = "US", "us"
        else:
            market, stype = "CN", "sh_sz"

        url = (
            f"https://xueqiu.com/service/v5/stock/screener/quote/list"
            f"?page=1&size={limit}&order=desc&order_by=market_capital"
            f"&market={market}&type={stype}"
        )
        try:
            data = self._get_json(url)
        except _XueqiuAPIError:
            return None
        items = (data.get("data") or {}).get("list") or []
        for item in items:
            if item.get("symbol") == symbol:
                return item
        return None

    def _screener_hot_stocks(self, market: str = "CN", stype: str = "sh_sz",
                             limit: int = 10) -> list:
        url = (
            f"https://xueqiu.com/service/v5/stock/screener/quote/list"
            f"?page=1&size={limit}&order=desc&order_by=percent"
            f"&market={market}&type={stype}"
        )
        try:
            data = self._get_json(url)
        except _XueqiuAPIError:
            return []
        items = (data.get("data") or {}).get("list") or []
        results = []
        for idx, item in enumerate(items[:limit], 1):
            results.append({
                "symbol": item.get("symbol", ""), "name": item.get("name", ""),
                "current": item.get("current"), "percent": item.get("percent"),
                "market_capital": item.get("market_capital"),
                "pe_ttm": item.get("pe_ttm"), "turnover_rate": item.get("turnover_rate"),
                "volume": item.get("volume"), "rank": idx,
            })
        return results

    @staticmethod
    def _strip_html(text: str) -> str:
        text = re.sub(r"<[^>]+>", "", text)
        for entity, char in (
            ("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
            ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'"),
        ):
            text = text.replace(entity, char)
        return text.strip()

    def check(self) -> tuple:
        if not self._auth.is_authenticated:
            self._auth.ensure_cookies()
        try:
            data = self._get_json(
                "https://stock.xueqiu.com/v5/stock/batch/quote.json?symbol=SH000001"
            )
            items = (data.get("data") or {}).get("items") or []
            if items:
                if self._auth.is_authenticated:
                    return "ok", "雪球 API 完整可用"
                return "warn", "API 部分可用（缺少登录 Cookie）"
            return "warn", "API 响应异常"
        except _XueqiuAPIError as e:
            if "400016" in str(e):
                try:
                    self._get_json(
                        "https://xueqiu.com/service/v5/stock/screener/quote/list"
                        "?page=1&size=1&order=desc&order_by=percent&market=CN&type=sh_sz"
                    )
                    return "warn", "Screener API 可用（无需登录，行情/K线受限）"
                except Exception:
                    return "error", "Cookie 过期且 Screener 不可用"
            return "error", str(e)
        except Exception as e:
            return "error", f"连接失败：{e}"

    def get_stock_quote(self, symbol: str) -> dict:
        try:
            data = self._get_json(
                f"https://stock.xueqiu.com/v5/stock/batch/quote.json?symbol={symbol}"
            )
            items = (data.get("data") or {}).get("items") or []
            q = (items[0].get("quote") or {}) if items else {}
            return {
                "symbol": q.get("symbol", symbol), "name": q.get("name", ""),
                "current": q.get("current"), "percent": q.get("percent"),
                "chg": q.get("chg"), "high": q.get("high"), "low": q.get("low"),
                "open": q.get("open"), "last_close": q.get("last_close"),
                "volume": q.get("volume"), "amount": q.get("amount"),
                "market_capital": q.get("market_capital"),
                "turnover_rate": q.get("turnover_rate"),
                "pe_ttm": q.get("pe_ttm"), "timestamp": q.get("timestamp"),
            }
        except _XueqiuAPIError as e:
            if "400016" in str(e):
                item = self._screener_quote(symbol)
                if item:
                    return {
                        "symbol": item.get("symbol", symbol),
                        "name": item.get("name", ""),
                        "current": item.get("current"),
                        "percent": item.get("percent"),
                        "chg": item.get("chg"),
                        "high": None, "low": None,
                        "open": None, "last_close": None,
                        "volume": item.get("volume"),
                        "amount": item.get("amount"),
                        "market_capital": item.get("market_capital"),
                        "turnover_rate": item.get("turnover_rate"),
                        "pe_ttm": item.get("pe_ttm"),
                        "timestamp": None,
                        "_source": "screener_fallback",
                    }
            raise

    def search_stock(self, query: str, limit: int = 10) -> list:
        try:
            data = self._get_json(
                f"https://xueqiu.com/stock/search.json"
                f"?code={urllib.parse.quote(query)}&size={limit}"
            )
            stocks = data.get("stocks") or []
            return [
                {"symbol": s.get("code", ""), "name": s.get("name", ""),
                 "exchange": s.get("exchange", "")}
                for s in stocks[:limit]
            ]
        except _XueqiuAPIError as e:
            if "400016" in str(e):
                return self._screener_search(query, limit)
            raise

    def _screener_search(self, query: str, limit: int = 10) -> list:
        results = []
        for market, stype in [("CN", "sh_sz"), ("HK", "hk"), ("US", "us")]:
            url = (
                f"https://xueqiu.com/service/v5/stock/screener/quote/list"
                f"?page=1&size=50&order=desc&order_by=market_capital"
                f"&market={market}&type={stype}"
            )
            try:
                data = self._get_json(url)
            except _XueqiuAPIError:
                continue
            items = (data.get("data") or {}).get("list") or []
            for item in items:
                name = item.get("name", "")
                sym = item.get("symbol", "")
                if query.upper() in sym.upper() or query in name:
                    results.append({
                        "symbol": sym, "name": name,
                        "exchange": market, "current": item.get("current"),
                    })
                if len(results) >= limit:
                    return results
        return results

    def get_hot_posts(self, limit: int = 20) -> list:
        data = self._get_json(
            "https://xueqiu.com/v4/statuses/public_timeline_by_category.json"
            "?since_id=-1&max_id=-1&count=20&category=-1"
        )
        items = data.get("list") or []
        results = []
        for item in items[:limit]:
            try:
                post = json.loads(item["data"]) if isinstance(item.get("data"), str) else {}
            except (json.JSONDecodeError, KeyError):
                post = {}
            user = post.get("user") or {}
            text = self._strip_html(post.get("text") or post.get("description") or "")
            target = post.get("target", "")
            results.append({
                "id": post.get("id", 0), "title": post.get("title") or "",
                "text": text[:200], "author": user.get("screen_name", ""),
                "likes": post.get("like_count", 0),
                "url": f"https://xueqiu.com{target}" if target else "",
            })
        return results

    def get_hot_stocks(self, limit: int = 10, stock_type: int = 10) -> list:
        try:
            data = self._get_json(
                f"https://stock.xueqiu.com/v5/stock/hot_stock/list.json"
                f"?size={limit}&type={stock_type}"
            )
            items = (data.get("data") or {}).get("items") or []
            results = []
            for idx, item in enumerate(items[:limit], 1):
                results.append({
                    "symbol": item.get("code") or item.get("symbol", ""),
                    "name": item.get("name", ""), "current": item.get("current"),
                    "percent": item.get("percent"), "rank": idx,
                })
            return results
        except _XueqiuAPIError as e:
            if "400016" in str(e):
                return self._screener_hot_stocks(limit=limit)
            raise

    def get_user_posts(self, user_id: int, limit: int = 10) -> list:
        data = self._get_json(
            f"https://xueqiu.com/v4/statuses/user_timeline.json"
            f"?user_id={user_id}&page=1&count={limit}"
        )
        statuses = data.get("list") or []
        results = []
        for s in statuses[:limit]:
            text = self._strip_html(s.get("text") or s.get("description") or "")
            results.append({
                "id": s.get("id", 0), "title": s.get("title") or "",
                "text": text[:300], "created_at": s.get("created_at"),
                "likes": s.get("like_count", 0),
                "retweets": s.get("retweet_count", 0),
            })
        return results

    def get_stock_kline(self, symbol: str, period: str = "day", count: int = 30) -> list:
        try:
            data = self._get_json(
                f"https://stock.xueqiu.com/v5/stock/chart/kline.json"
                f"?symbol={symbol}&period={period}&count={count}"
            )
        except _XueqiuAPIError as e:
            if "400016" in str(e):
                raise _XueqiuAPIError("K线数据需要登录 Cookie，Screener 无法提供历史行情") from e
            raise
        items = (data.get("data") or {}).get("item") or []
        columns = ((data.get("data") or {}).get("column") or [])
        results = []
        for item in items:
            row = dict(zip(columns, item)) if columns else {}
            results.append({
                "timestamp": row.get("timestamp"), "open": row.get("open"),
                "high": row.get("high"), "low": row.get("low"),
                "close": row.get("close"), "volume": row.get("volume"),
            })
        return results


class XueqiuSkill(Skill):
    """雪球实时行情/热帖/热门股票 Skill（A股/港股/美股）"""

    _memory_cache: Dict[tuple, Dict[str, Any]] = {}
    _last_request_time: float = 0.0
    _MIN_INTERVAL: float = 0.5

    @property
    def name(self) -> str:
        return "xueqiu"

    @property
    def description(self) -> str:
        return "雪球实时行情/热门股票/热帖/K线 (A股/港股/美股)"

    def __init__(self, config=None):
        super().__init__(config)
        self._api: Optional[_XueqiuAPI] = None

    def _init_api(self) -> _XueqiuAPI:
        return _XueqiuAPI()

    async def _rate_limited_call(self, func, *args, **kwargs):
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self._MIN_INTERVAL:
            await asyncio.sleep(self._MIN_INTERVAL - elapsed)
        self._last_request_time = time.monotonic()
        return await asyncio.to_thread(func, *args, **kwargs)

    async def execute(self, **kwargs) -> Dict[str, Any]:
        action = kwargs.get("action", "quote")

        if self._api is None:
            self._api = await asyncio.to_thread(self._init_api)

        cache_key = (action, str(sorted(kwargs.items())))
        if cache_key in self._memory_cache:
            logger.debug(f"XueqiuSkill: cache hit for {cache_key}")
            return self._memory_cache[cache_key]

        try:
            if action == "quote":
                result = await self._execute_quote(**kwargs)
            elif action == "search":
                result = await self._execute_search(**kwargs)
            elif action == "hot_posts":
                result = await self._execute_hot_posts(**kwargs)
            elif action == "hot_stocks":
                result = await self._execute_hot_stocks(**kwargs)
            elif action == "kline":
                result = await self._execute_kline(**kwargs)
            elif action == "user_posts":
                result = await self._execute_user_posts(**kwargs)
            elif action == "check":
                result = await self._execute_check(**kwargs)
            elif action == "search_and_quote":
                result = await self._execute_search_and_quote(**kwargs)
            else:
                return self._failure(f"Unsupported action: {action}")

            if result.get("success"):
                self._memory_cache[cache_key] = result
            return result
        except Exception as e:
            logger.warning(f"XueqiuSkill action '{action}' failed: {e}")
            return self._failure(f"API error: {e}")

    async def _execute_quote(self, **kwargs) -> Dict[str, Any]:
        symbol = kwargs.get("symbol", "")
        if not symbol:
            return self._failure("请提供股票代码 (symbol)，如 SH600519")
        data = await self._rate_limited_call(self._api.get_stock_quote, symbol)
        content = (f"{data.get('name', '')}({data.get('symbol', '')}): "
                   f"当前价 {data.get('current')}, 涨跌幅 {data.get('percent')}%, "
                   f"市值 {data.get('market_capital')}")
        return {"success": True, "data": data, "content": content, "symbol": symbol, "source": "xueqiu"}

    async def _execute_search(self, **kwargs) -> Dict[str, Any]:
        query = kwargs.get("query", "")
        if not query:
            return self._failure("请提供搜索关键词 (query)")
        limit = kwargs.get("limit", 10)
        data = await self._rate_limited_call(self._api.search_stock, query, limit=limit)
        return {"success": True, "data": data, "content": f"搜索到 {len(data)} 只股票", "source": "xueqiu"}

    async def _execute_hot_posts(self, **kwargs) -> Dict[str, Any]:
        limit = kwargs.get("limit", 20)
        data = await self._rate_limited_call(self._api.get_hot_posts, limit=limit)
        return {"success": True, "data": data, "content": f"获取 {len(data)} 条热帖", "source": "xueqiu"}

    async def _execute_hot_stocks(self, **kwargs) -> Dict[str, Any]:
        limit = kwargs.get("limit", 10)
        stock_type = kwargs.get("stock_type", 10)
        data = await self._rate_limited_call(self._api.get_hot_stocks, limit=limit, stock_type=stock_type)
        return {"success": True, "data": data, "content": f"获取 {len(data)} 只热门股票", "source": "xueqiu"}

    async def _execute_kline(self, **kwargs) -> Dict[str, Any]:
        symbol = kwargs.get("symbol", "")
        if not symbol:
            return self._failure("请提供股票代码 (symbol)")
        period = kwargs.get("period", "day")
        count = kwargs.get("count", 30)
        data = await self._rate_limited_call(self._api.get_stock_kline, symbol, period=period, count=count)
        return {"success": True, "data": data, "content": f"获取 {symbol} K线数据 {len(data)} 条 (周期={period})", "symbol": symbol, "source": "xueqiu"}

    async def _execute_user_posts(self, **kwargs) -> Dict[str, Any]:
        user_id = kwargs.get("user_id")
        if not user_id:
            return self._failure("请提供用户ID (user_id)")
        limit = kwargs.get("limit", 10)
        data = await self._rate_limited_call(self._api.get_user_posts, user_id, limit=limit)
        return {"success": True, "data": data, "content": f"获取用户 {user_id} 的 {len(data)} 条帖子", "source": "xueqiu"}

    async def _execute_check(self, **kwargs) -> Dict[str, Any]:
        status, message = await self._rate_limited_call(self._api.check)
        return {"success": True, "data": {"status": status, "message": message}, "content": message, "source": "xueqiu"}

    async def _execute_search_and_quote(self, **kwargs) -> Dict[str, Any]:
        query = kwargs.get("query", "")
        if not query:
            return self._failure("请提供搜索关键词 (query)")
        results = await self._rate_limited_call(self._api.search_stock, query, limit=1)
        if not results:
            return self._failure(f"未找到股票: {query}")
        symbol = results[0]["symbol"]
        quote = await self._rate_limited_call(self._api.get_stock_quote, symbol)
        content = (f"{results[0]['name']}({symbol}): 当前价 {quote.get('current')}, "
                   f"涨跌幅 {quote.get('percent')}%, "
                   f"成交量 {quote.get('volume')}, 市值 {quote.get('market_capital')}")
        return {"success": True, "data": {"search": results[0], "quote": quote}, "content": content, "symbol": symbol, "source": "xueqiu"}

    def format_data(self, data: dict, action: str, identifier: str) -> str:
        if action == "quote":
            return self._format_quote(data, identifier)
        elif action == "kline":
            return self._format_kline(data, identifier)
        elif action == "hot_stocks":
            return self._format_hot_stocks(data)
        elif action == "search_and_quote":
            return self._format_search_and_quote(data, identifier)
        elif action == "hot_posts":
            return self._format_hot_posts(data)
        elif action == "user_posts":
            return self._format_user_posts(data)
        return ""

    def _format_quote(self, data: dict, symbol: str) -> str:
        if not data or not isinstance(data, dict):
            return ""
        lines = [f"=== {data.get('name', symbol)} 实时行情 ==="]
        fields = [
            ("current", "当前价"), ("percent", "涨跌幅"), ("change", "涨跌额"),
            ("high", "最高"), ("low", "最低"), ("open", "开盘价"),
            ("volume", "成交量"), ("amount", "成交额"), ("market_capital", "市值"),
            ("pe_ttm", "PE_TTM"), ("turnover_rate", "换手率"),
        ]
        for key, label in fields:
            val = data.get(key)
            if val is not None:
                lines.append(f"{label}: {val}")
        return "\n".join(lines)

    def _format_kline(self, data: dict, symbol: str) -> str:
        if not data:
            return ""
        records = data
        if isinstance(data, dict):
            records = data.get("records", data.get("item", []))
        if not isinstance(records, list):
            return ""
        lines = [f"=== {symbol} K线数据 (最近{min(len(records), 10)}条) ==="]
        for rec in records[:10]:
            if not isinstance(rec, dict):
                continue
            date = rec.get("time", rec.get("date", ""))
            close = rec.get("close", "")
            high = rec.get("high", "")
            low = rec.get("low", "")
            lines.append(f"{date}: 收{close} 高{high} 低{low}")
        return "\n".join(lines)

    def _format_hot_stocks(self, data: dict) -> str:
        records = data
        if isinstance(data, dict):
            records = data.get("records", data.get("items", []))
        if not records or not isinstance(records, list):
            return ""
        lines = [f"=== 热门股票 TOP{min(len(records), 10)} ==="]
        for i, stock in enumerate(records[:10], 1):
            if isinstance(stock, dict):
                name = stock.get("name", stock.get("symbol", ""))
                change = stock.get("percent", stock.get("change", ""))
                lines.append(f"{i}. {name} 涨跌幅:{change}")
        return "\n".join(lines)

    def _format_search_and_quote(self, data: dict, symbol: str) -> str:
        if not data or not isinstance(data, dict):
            return ""
        quote = data.get("quote", {})
        search = data.get("search", {})
        name = search.get("name", symbol)
        lines = [f"=== {name}({symbol}) 搜索+行情 ==="]
        if quote:
            for key in ["current", "percent", "volume", "market_capital", "turnover_rate"]:
                if key in quote:
                    lines.append(f"{key}: {quote[key]}")
        return "\n".join(lines)

    def _format_hot_posts(self, data: dict) -> str:
        records = data
        if isinstance(data, dict):
            records = data.get("records", data.get("items", []))
        if not records or not isinstance(records, list):
            return ""
        lines = [f"=== 雪球热帖 TOP{min(len(records), 10)} ==="]
        for i, post in enumerate(records[:10], 1):
            if isinstance(post, dict):
                title = post.get("title", post.get("text", ""))[:50]
                lines.append(f"{i}. {title}")
        return "\n".join(lines)

    def _format_user_posts(self, data: dict) -> str:
        records = data
        if isinstance(data, dict):
            records = data.get("records", data.get("items", []))
        if not records or not isinstance(records, list):
            return ""
        lines = [f"=== 用户帖子 (最近{min(len(records), 10)}条) ==="]
        for i, post in enumerate(records[:10], 1):
            if isinstance(post, dict):
                title = post.get("title", post.get("text", ""))[:50]
                lines.append(f"{i}. {title}")
        return "\n".join(lines)
