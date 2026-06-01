"""
DataBus - 数据总线

统一的数据查询入口，提供缓存、路由、回退机制。
"""
import hashlib
import json
from datetime import datetime, timedelta
from typing import Any, Dict, Optional


class DataBus:
    """
    数据总线

    功能:
    - 统一注册/查询多个 DataProvider
    - 内存缓存（可配置 TTL）
    - 查询失败时自动回退到备用 Provider
    - 统计信息（请求数、缓存命中率）
    """

    def __init__(self, cache_ttl_seconds: int = 300):
        self._providers: Dict[str, Any] = {}
        self._cache: Dict[str, Dict] = {}
        self._cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self._stats = {
            "total_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "errors": 0,
        }

    def register_provider(self, source_id: str, provider: Any) -> None:
        """注册数据 Provider"""
        self._providers[source_id] = provider

    def unregister_provider(self, source_id: str) -> bool:
        """取消注册"""
        if source_id in self._providers:
            del self._providers[source_id]
            return True
        return False

    async def query(
        self,
        source: str,
        params: Dict[str, Any],
        fallback_source: Optional[str] = None,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """
        查询数据

        Args:
            source: 数据来源 ID
            params: 查询参数
            fallback_source: 回退来源 ID（可选）
            use_cache: 是否使用缓存（默认 True）

        Returns:
            查询结果字典
        """
        self._stats["total_requests"] += 1

        if source not in self._providers:
            self._stats["errors"] += 1
            return {
                "success": False,
                "error": f"未注册的数据来源: {source}",
            }

        # 检查缓存
        cache_key = self._make_cache_key(source, params)
        if use_cache:
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                self._stats["cache_hits"] += 1
                return {**cached, "cached": True}

        self._stats["cache_misses"] += 1

        # 调用主 Provider
        try:
            provider = self._providers[source]
            data = await provider.fetch(params)
            result = {"success": True, "data": data, "source": source}
            if use_cache:
                self._put_to_cache(cache_key, result)
            return result

        except Exception as primary_err:
            # 尝试回退
            if fallback_source and fallback_source in self._providers:
                try:
                    fallback = self._providers[fallback_source]
                    data = await fallback.fetch(params)
                    result = {
                        "success": True,
                        "data": data,
                        "source": fallback_source,
                        "fallback_used": True,
                    }
                    return result
                except Exception as fallback_err:
                    self._stats["errors"] += 1
                    return {
                        "success": False,
                        "error": f"主: {primary_err}; 备: {fallback_err}",
                    }

            self._stats["errors"] += 1
            return {"success": False, "error": str(primary_err)}

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        total = self._stats["total_requests"]
        hits = self._stats["cache_hits"]
        return {
            **self._stats,
            "cache_hit_rate": round(hits / total, 3) if total > 0 else 0.0,
            "registered_providers": list(self._providers.keys()),
        }

    def clear_cache(self) -> int:
        """清空缓存，返回清除条目数"""
        count = len(self._cache)
        self._cache.clear()
        return count

    # ------------------------------------------------------------------
    # 私有方法
    # ------------------------------------------------------------------

    def _make_cache_key(self, source: str, params: Dict) -> str:
        """生成缓存 Key"""
        raw = json.dumps({"source": source, "params": params}, sort_keys=True)
        return hashlib.md5(raw.encode()).hexdigest()

    def _get_from_cache(self, key: str) -> Optional[Dict]:
        """从缓存获取"""
        entry = self._cache.get(key)
        if entry is None:
            return None
        if datetime.now() > entry["expires_at"]:
            del self._cache[key]
            return None
        return entry["data"]

    def _put_to_cache(self, key: str, data: Dict) -> None:
        """写入缓存"""
        self._cache[key] = {
            "data": data,
            "expires_at": datetime.now() + self._cache_ttl,
        }
