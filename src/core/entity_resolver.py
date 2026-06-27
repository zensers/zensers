# -*- coding: utf-8 -*-
"""EntityResolver — per-entity listed company detection and skill routing.

Resolves research subjects to stock codes via akshare cache table,
enabling structured data (stock_data skill) to be loaded for listed companies.
"""

import asyncio
import logging
import os
import pickle
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_AHOCORASICK_AVAILABLE = False
try:
    import ahocorasick
    _AHOCORASICK_AVAILABLE = True
except ImportError:
    ahocorasick = None

_CACHE_DIR = Path(os.path.expanduser("~/.cache/market_report"))
_CACHE_FILE = _CACHE_DIR / "stock_name_table.pkl"
_CACHE_TTL_SECONDS = 24 * 3600
_MIN_FUZZY_MATCH_LEN = 3


@dataclass
class EntityInfo:
    name: str
    stock_code: Optional[str]
    is_listed: bool

    @property
    def data_source_type(self) -> str:
        return "structured" if self.is_listed else "search"

    @property
    def resolved_code(self) -> Optional[str]:
        if isinstance(self.stock_code, str) and self.stock_code != "__keyword_registry__":
            return self.stock_code
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "stock_code": self.stock_code,
            "is_listed": self.is_listed,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EntityInfo":
        return cls(
            name=d["name"],
            stock_code=d.get("stock_code"),
            is_listed=d.get("is_listed", False),
        )


class EntityResolver:
    _instance: Optional["EntityResolver"] = None

    def __init__(self):
        self._stock_name_table: Dict[str, str] = {}
        self._table_loaded: bool = False
        self._table_loading: bool = False
        self._lock = None

        self._resolve_cache: Dict[str, Optional[str]] = {}
        self._full_resolve_cache: Dict[str, List[EntityInfo]] = {}

        self._automaton = None
        self._cache_timestamp: float = 0.0

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def resolve(self, text: str) -> List[EntityInfo]:
        if text in self._full_resolve_cache:
            return self._full_resolve_cache[text]

        await self._ensure_table_loaded()

        entities = self._extract_entities(text)
        results = []
        for name in entities:
            code = await self._resolve_to_code(name)
            results.append(EntityInfo(
                name=name,
                stock_code=code if isinstance(code, str) else None,
                is_listed=code is not None,
            ))
        self._full_resolve_cache[text] = results
        return results

    def _extract_entities(self, text: str) -> List[str]:
        entities = []

        suffix_pattern = re.compile(
            r'([\u4e00-\u9fff]+(?:公司|集团|股份|有限))'
        )
        for m in suffix_pattern.finditer(text):
            core = re.sub(r'(公司|集团|股份|有限).*$', '', m.group(1))
            if core and core not in entities:
                entities.append(core)

        if not entities and self._automaton is not None:
            for end_idx, (table_name, table_code) in self._automaton.iter(text):
                start_idx = end_idx - len(table_name) + 1
                before_ok = (start_idx == 0) or (
                    not re.match(r'[\u4e00-\u9fff]', text[start_idx - 1])
                )
                after_ok = (end_idx == len(text) - 1) or (
                    not re.match(r'[\u4e00-\u9fff]', text[end_idx + 1])
                )
                if before_ok and after_ok and table_name not in entities:
                    entities.append(table_name)

        if not entities and self._stock_name_table:
            for table_name in self._stock_name_table:
                if len(table_name) < _MIN_FUZZY_MATCH_LEN:
                    continue
                if table_name in text and table_name not in entities:
                    entities.append(table_name)

        return entities

    async def _resolve_to_code(self, name: str) -> Optional[str]:
        if name in self._resolve_cache:
            return self._resolve_cache[name]

        await self._ensure_table_loaded()

        code = self._stock_name_table.get(name)
        if code is not None:
            self._resolve_cache[name] = code
            return code

        if len(name) >= _MIN_FUZZY_MATCH_LEN:
            best_match = None
            best_len = 0
            for table_name, table_code in self._stock_name_table.items():
                if name in table_name and len(table_name) > best_len:
                    best_match = table_code
                    best_len = len(table_name)
                elif len(table_name) >= _MIN_FUZZY_MATCH_LEN and table_name in name and len(table_name) > best_len:
                    best_match = table_code
                    best_len = len(table_name)
            if best_match:
                self._resolve_cache[name] = best_match
                return best_match

        if not self._table_loaded:
            try:
                from src.core.intent.keyword_registry import get_registry
                if get_registry().is_listed_company_topic(name):
                    self._resolve_cache[name] = "__keyword_registry__"
                    return "__keyword_registry__"
            except Exception:
                pass

        self._resolve_cache[name] = None
        return None

    async def _ensure_table_loaded(self):
        if self._table_loaded:
            return

        lock = self._get_lock()
        async with lock:
            if self._table_loaded:
                return
            self._table_loading = True
            try:
                loaded = self._try_load_disk_cache()
                if loaded:
                    self._table_loaded = True
                    self._build_automaton()
                    if self._is_cache_expired():
                        asyncio.ensure_future(self._refresh_table_async())
                    return

                await self._load_table_from_akshare()
                if self._table_loaded:
                    self._build_automaton()
                    self._save_disk_cache()
            finally:
                self._table_loading = False

    def _try_load_disk_cache(self) -> bool:
        try:
            if not _CACHE_FILE.exists():
                return False
            with open(_CACHE_FILE, "rb") as f:
                data = pickle.load(f)
            if not isinstance(data, dict):
                return False
            if "table" not in data or "timestamp" not in data:
                return False
            self._stock_name_table = data["table"]
            self._cache_timestamp = data["timestamp"]
            logger.info(
                f"EntityResolver: loaded {len(self._stock_name_table)} "
                f"names from disk cache (age: "
                f"{(time.time() - data['timestamp'])/3600:.1f}h)"
            )
            return True
        except Exception as e:
            logger.warning(f"EntityResolver: disk cache load failed: {e}")
            return False

    def _is_cache_expired(self) -> bool:
        ts = getattr(self, "_cache_timestamp", 0)
        return (time.time() - ts) > _CACHE_TTL_SECONDS

    async def _load_table_from_akshare(self):
        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is None:
                df = self._fetch_akshare_table()
            else:
                df = await loop.run_in_executor(None, self._fetch_akshare_table)
            if df is not None and not df.empty:
                name_col = None
                code_col = None
                for col in df.columns:
                    col_str = str(col)
                    if "名称" in col_str:
                        name_col = col
                    if "代码" in col_str:
                        code_col = col
                if name_col and code_col:
                    for _, row in df.iterrows():
                        stock_name = str(row[name_col]).strip()
                        stock_code = str(row[code_col]).strip()
                        if stock_name and stock_code:
                            self._stock_name_table[stock_name] = stock_code
                    self._table_loaded = True
                    self._cache_timestamp = time.time()
                    logger.info(
                        f"EntityResolver: loaded {len(self._stock_name_table)} "
                        f"A-share company names from akshare"
                    )
        except ImportError:
            logger.warning("EntityResolver: akshare not installed, stock detection disabled")
        except Exception as e:
            logger.warning(f"EntityResolver: failed to load stock name table: {e}")

    @staticmethod
    def _fetch_akshare_table():
        import akshare as ak
        return ak.stock_zh_a_spot_em()

    def _save_disk_cache(self):
        try:
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            data = {
                "table": self._stock_name_table,
                "timestamp": getattr(self, "_cache_timestamp", time.time()),
            }
            tmp_file = _CACHE_FILE.with_suffix(".tmp")
            with open(tmp_file, "wb") as f:
                pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
            tmp_file.replace(_CACHE_FILE)
            logger.info(f"EntityResolver: saved disk cache to {_CACHE_FILE}")
        except Exception as e:
            logger.warning(f"EntityResolver: disk cache save failed: {e}")

    def _build_automaton(self):
        if not _AHOCORASICK_AVAILABLE:
            logger.info("EntityResolver: ahocorasick not installed, reverse matching disabled")
            self._automaton = None
            return
        try:
            auto = ahocorasick.Automaton()
            for name, code in self._stock_name_table.items():
                auto.add_word(name, (name, code))
            auto.make_automaton()
            self._automaton = auto
            logger.info(
                f"EntityResolver: built Aho-Corasick automaton with "
                f"{len(self._stock_name_table)} patterns"
            )
        except Exception as e:
            logger.warning(f"EntityResolver: automaton build failed: {e}")
            self._automaton = None

    async def _refresh_table_async(self):
        try:
            new_table: Dict[str, str] = {}
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is None:
                df = self._fetch_akshare_table()
            else:
                df = await loop.run_in_executor(None, self._fetch_akshare_table)
            if df is not None and not df.empty:
                name_col = None
                code_col = None
                for col in df.columns:
                    col_str = str(col)
                    if "名称" in col_str:
                        name_col = col
                    if "代码" in col_str:
                        code_col = col
                if name_col and code_col:
                    for _, row in df.iterrows():
                        stock_name = str(row[name_col]).strip()
                        stock_code = str(row[code_col]).strip()
                        if stock_name and stock_code:
                            new_table[stock_name] = stock_code
            if new_table:
                self._stock_name_table = new_table
                self._cache_timestamp = time.time()
                self._build_automaton()
                self._save_disk_cache()
                self._resolve_cache.clear()
                self._full_resolve_cache.clear()
                logger.info(
                    f"EntityResolver: refreshed {len(new_table)} "
                    f"A-share company names"
                )
            else:
                logger.info("EntityResolver: online refresh failed, keeping stale cache")
        except Exception as e:
            logger.warning(f"EntityResolver: background refresh failed: {e}")

    async def refresh_table(self):
        self._table_loaded = False
        self._stock_name_table.clear()
        self._resolve_cache.clear()
        self._full_resolve_cache.clear()
        self._automaton = None
        await self._ensure_table_loaded()


def get_entity_resolver() -> EntityResolver:
    if EntityResolver._instance is None:
        EntityResolver._instance = EntityResolver()
    return EntityResolver._instance
