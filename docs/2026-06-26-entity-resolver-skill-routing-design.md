# 主体级实体解析与 Skill 路由设计

> 日期：2026-06-27（修订）
> 状态：修订版，已修复可行性审查发现的硬伤

## 1. 问题

当前 `stock_data`（akshare）skill 的加载依赖 **aspect 关键词匹配**，不检查研究对象是否为上市公司。导致：

- 用户研究"比亚迪竞争格局"，aspect="竞争格局"不含财务关键词 → stock_data 不加载
- 研究涉及多个主体（如"新能源汽车行业"含比亚迪、宁德时代、华为），无法区分哪些是上市公司
- `keyword_mappings.yaml` 的 `listed_company_indicators.names` 包含华为、字节等**非上市企业**，会误判
- `_extract_stock_symbol()` 中 `_is_likely_company_name()` 基于硬编码名单，新公司无法覆盖

## 2. 设计原则

1. **逐主体判断，非整体分类**：一个 topic 可能包含多个主体，每个主体独立判断是否上市公司
2. **尝试解析，而非预分类**：不维护硬编码名单，直接问 akshare"你有没有这个主体的数据"
3. **一次解析，结果传播**：在 `decompose()` 入口解析一次，结果通过 `pre_resolved_entities` 参数和 `context["entities"]` 向下游传递，避免重复查询
4. **结构化优先，搜索补充**：上市公司优先用 stock_data 获取年报/财务数据，不足部分用搜索补充
5. **异步优先，不阻塞事件循环**：全 async 设计，akshare 同步调用通过 `run_in_executor` 执行
6. **离线可用，渐进降级**：磁盘缓存 → 过期缓存 → keyword_registry，网络不可用时仍可基本工作

## 3. 核心流程

```
topic + aspect
    ↓
decompose() 入口：await EntityResolver.resolve(topic)  ← 一次解析
    ├── 提取主体列表：["比亚迪", "华为", "宁德时代"]
    │   ├── 后缀模式匹配
    │   └── Aho-Corasick 自动机反向扫描（O(text_length)）
    ├── 逐个解析（await _resolve_to_code）：
    │   ├── "比亚迪"   → 缓存表精确命中 → 002594 (上市)
    │   ├── "华为"     → 缓存表未命中 → None (非上市)
    │   └── "宁德时代" → 缓存表精确命中 → 300750 (上市)
    ↓
EntityInfo 列表序列化为 dict，写入 context + 传递给下游函数
    ↓
skill 推断函数读取 pre_resolved_entities：
    ├── 有上市主体 → 注入 stock_data
    └── 无上市主体 → 不注入
    ↓
agent 执行时（from_dict 反序列化）：
    ├── 上市主体 → _fetch_structured_data() 直接用 resolved_code
    ├── 非上市主体 → 搜索补充
    └── 结构化数据不足 → 生成补充搜索查询
```

## 4. 新增模块：`src/core/entity_resolver.py`

### 4.1 数据结构

```python
@dataclass
class EntityInfo:
    name: str                    # 主体名，如"比亚迪"
    stock_code: Optional[str]    # 股票代码，如"002594"；非上市为 None
    is_listed: bool              # 是否上市公司

    @property
    def data_source_type(self) -> str:
        return "structured" if self.is_listed else "search"
    
    @property
    def resolved_code(self) -> Optional[str]:
        """返回有效的股票代码（排除降级标记和无效值）"""
        if isinstance(self.stock_code, str) and self.stock_code != "__keyword_registry__":
            return self.stock_code
        return None

    def to_dict(self) -> Dict[str, Any]:
        """序列化为 dict，用于 context 传递和持久化"""
        return {
            "name": self.name,
            "stock_code": self.stock_code,
            "is_listed": self.is_listed,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EntityInfo":
        """从 dict 反序列化"""
        return cls(
            name=d["name"],
            stock_code=d.get("stock_code"),
            is_listed=d.get("is_listed", False),
        )
```

> **设计说明**：`EntityInfo` 必须支持 `to_dict()`/`from_dict()` 序列化，因为 `AgentSpec.context` 可能经过 JSON 序列化（消息队列分发、持久化存储等场景）。dataclass 对象在 JSON 反序列化后会退化为 dict，消费方需通过 `from_dict()` 恢复。

### 4.2 EntityResolver 类

```python
import asyncio
import json
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
_CACHE_TTL_SECONDS = 24 * 3600  # 24小时
_MIN_FUZZY_MATCH_LEN = 3         # 包含匹配最小长度阈值，避免"东方"等短名误匹配


class EntityResolver:
    """主体解析器：从文本中提取主体，逐个判断是否上市公司
    
    线程模型：全异步设计，使用 asyncio.Lock 保护共享状态。
    akshare 的同步网络调用通过 run_in_executor 执行，不阻塞事件循环。
    """

    _instance: Optional["EntityResolver"] = None

    _stock_name_table: Dict[str, str] = {}
    _table_loaded: bool = False
    _table_loading: bool = False
    _lock = None  # asyncio.Lock，首次使用时初始化（避免模块级 import 时无事件循环）

    _resolve_cache: Dict[str, Optional[str]] = {}
    _full_resolve_cache: Dict[str, List["EntityInfo"]] = {}

    _automaton = None  # ahocorasick 自动机，用于反向匹配

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def resolve(self, text: str) -> List["EntityInfo"]:
        """从文本中提取主体，逐个判断是否上市公司
        
        结果按文本级缓存，同一文本多次调用直接返回缓存。
        """
        if text in self._full_resolve_cache:
            return self._full_resolve_cache[text]

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
        """从文本中提取主体名
        
        策略（按优先级）：
        1. 匹配中文公司名后缀模式（XX公司/XX集团/XX股份/XX有限）
        2. 用 Aho-Corasick 自动机在文本中扫描已知 A 股公司名（O(text_length)）
        3. 不提取通用中文片段，避免"行业""分析"等非主体词污染
        
        注意：反向匹配仅在自动机可用时执行，否则跳过（依赖 _resolve_to_code 的
        包含匹配兜底）。反向匹配结果做边界检查，要求匹配串前后为非中文字符或
        字符串边界，避免"新能源汽车"误匹配"新能源科技"等子串。
        """
        entities = []

        # 1. 匹配中文公司名后缀模式：XX公司、XX集团、XX股份、XX有限
        #    提取完整匹配（如"比亚迪股份有限公司"→"比亚迪"）
        suffix_pattern = re.compile(
            r'([\u4e00-\u9fff]+(?:公司|集团|股份|有限))'
        )
        for m in suffix_pattern.finditer(text):
            core = re.sub(r'(公司|集团|股份|有限).*$', '', m.group(1))
            if core and core not in entities:
                entities.append(core)

        # 2. 用 Aho-Corasick 自动机反向匹配（O(text_length)，非 O(5000×N)）
        #    在已知 A 股公司名中搜索是否出现在文本中
        #    仅在无后缀匹配结果时执行，且自动机已构建
        if not entities and self._automaton is not None:
            for end_idx, (table_name, table_code) in self._automaton.iter(text):
                start_idx = end_idx - len(table_name) + 1
                # 边界检查：匹配串前后必须为非中文字符或字符串边界
                before_ok = (start_idx == 0) or (
                    not re.match(r'[\u4e00-\u9fff]', text[start_idx - 1])
                )
                after_ok = (end_idx == len(text) - 1) or (
                    not re.match(r'[\u4e00-\u9fff]', text[end_idx + 1])
                )
                if before_ok and after_ok and table_name not in entities:
                    entities.append(table_name)

        # 3. 去重，保持顺序
        return entities

    async def _resolve_to_code(self, name: str) -> Optional[str]:
        """将主体名解析为股票代码（查询缓存表）"""
        if name in self._resolve_cache:
            return self._resolve_cache[name]

        await self._ensure_table_loaded()

        # 1. 精确匹配
        code = self._stock_name_table.get(name)
        if code:
            self._resolve_cache[name] = code
            return code

        # 2. 包含匹配（仅 name in table_name 方向，最小长度 ≥ _MIN_FUZZY_MATCH_LEN）
        #    "比亚迪" 能匹配 "比亚迪股份"；"宁德时代" 能匹配 "宁德时代"
        #    "东方"（2字）不触发包含匹配，避免误判
        #    注意：不做 table_name in name（反向），避免短名误匹配长文本
        if len(name) >= _MIN_FUZZY_MATCH_LEN:
            best_match = None
            best_len = 0
            for table_name, table_code in self._stock_name_table.items():
                if name in table_name and len(table_name) > best_len:
                    best_match = table_code
                    best_len = len(table_name)
            if best_match:
                self._resolve_cache[name] = best_match
                return best_match

        # 3. 降级到 keyword_registry（akshare 表未加载或查不到时）
        #    返回特殊标记 "__keyword_registry__"，表示"判断为上市但代码未知"
        #    EntityInfo.stock_code = "__keyword_registry__"，resolved_code 返回 None
        #    agent 执行时通过 _extract_stock_symbol() 延迟解析代码
        if not self._table_loaded:
            try:
                from src.core.intent.keyword_registry import get_registry
                if get_registry().is_listed_company_topic(name):
                    self._resolve_cache[name] = "__keyword_registry__"
                    return "__keyword_registry__"
            except Exception:
                pass

        # 4. 未命中 → 缓存 None，避免重复查询
        self._resolve_cache[name] = None
        return None

    async def _ensure_table_loaded(self):
        """确保 A 股公司名表已加载（异步安全，不阻塞事件循环）
        
        加载优先级：
        1. 内存中已加载 → 直接返回
        2. 磁盘缓存未过期 → 加载磁盘缓存
        3. 磁盘缓存已过期但存在 → 加载旧缓存 + 后台异步刷新
        4. 无磁盘缓存 → 从 akshare 在线加载
        5. akshare 不可用 → 降级到 keyword_registry
        """
        if self._table_loaded:
            return

        lock = self._get_lock()
        async with lock:
            if self._table_loaded or self._table_loading:
                return
            self._table_loading = True
            try:
                loaded = self._try_load_disk_cache()
                if loaded:
                    self._table_loaded = True
                    self._build_automaton()
                    # 缓存过期时后台刷新（不阻塞当前请求）
                    if self._is_cache_expired():
                        asyncio.ensure_future(self._refresh_table_async())
                    return

                # 无磁盘缓存或缓存损坏 → 在线加载
                await self._load_table_from_akshare()
                if self._table_loaded:
                    self._build_automaton()
                    self._save_disk_cache()
            finally:
                self._table_loading = False

    def _try_load_disk_cache(self) -> bool:
        """尝试从磁盘加载缓存，返回是否成功"""
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
        """检查磁盘缓存是否过期"""
        ts = getattr(self, "_cache_timestamp", 0)
        return (time.time() - ts) > _CACHE_TTL_SECONDS

    async def _load_table_from_akshare(self):
        """从 akshare 在线加载 A 股公司名表（通过 run_in_executor 避免阻塞事件循环）"""
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
        """同步函数：调用 akshare 获取 A 股公司名表（在 executor 中执行）"""
        import akshare as ak
        return ak.stock_zh_a_spot_em()

    def _save_disk_cache(self):
        """将公司名表保存到磁盘"""
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
        """构建 Aho-Corasick 自动机用于反向匹配（O(text_length) 扫描）"""
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
        """后台异步刷新公司名表（缓存过期时调用）
        
        不设置 _table_loaded = False，避免其他协程触发重复加载。
        先在新 dict 中构建完整数据，再原子替换旧表。
        """
        try:
            new_table: Dict[str, str] = {}
            old_table = dict(self._stock_name_table)
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
                # 原子替换：先构建新自动机，再一次性替换
                self._stock_name_table = new_table
                self._cache_timestamp = time.time()
                self._build_automaton()
                self._save_disk_cache()
                self._resolve_cache.clear()  # 新数据，旧缓存失效
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
        """强制刷新 A 股公司名表（可定时调用，如每24小时）"""
        self._table_loaded = False
        self._stock_name_table.clear()
        self._resolve_cache.clear()
        self._full_resolve_cache.clear()
        self._automaton = None
        await self._ensure_table_loaded()


def get_entity_resolver() -> EntityResolver:
    """获取全局 EntityResolver 单例"""
    if EntityResolver._instance is None:
        EntityResolver._instance = EntityResolver()
    return EntityResolver._instance
```

> **依赖说明**：`pyahocorasick` 为可选依赖，未安装时反向匹配自动禁用，不影响精确匹配和包含匹配。建议加入 `requirements-optional.txt`：
> ```
> pyahocorasick>=0.9.0  # 可选：EntityResolver 反向匹配加速
> ```

### 4.3 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 公司名表来源 | akshare `stock_zh_a_spot_em()` | 实时、完整、免维护，新增上市公司自动覆盖 |
| 加载时机 | 首次调用时惰性加载 | 不影响启动速度，只在需要时才查询 |
| 网络不可用应对 | 磁盘缓存 + TTL + 过期后异步刷新 + 旧缓存兜底 | 实测 `ak.stock_zh_a_spot_em()` 在网络受限环境下返回 ConnectionError，必须有离线降级路径 |
| 缓存策略 | 解析结果永久缓存（含 None）；文本级缓存避免重复解析 | 同一次研究会话内公司名不会变，无需过期；`_full_resolve_cache` 避免同一文本多次调用 `_extract_entities()` |
| `_infer_skills` 职责 | 仅补充 `ASPECT_SKILL_MAP` 未覆盖的场景 | `ASPECT_SKILL_MAP` 已定义 `"Financial Analysis" → stock_analysis`，主体解析仅在如"竞争格局"等未覆盖场景注入 |
| `decompose()` 签名 | 改为 `async def`（路径A） | 调用方 `research_api.py` 本身在 async 上下文中；基类和所有子类需同步更新；同步方案（路径B）在有事件循环时不可行 |
| 反向匹配算法 | Aho-Corasick 自动机 + 边界检查 | A股约5000+公司，线性扫描 O(5000×N) 不可接受；自动机 O(text_length)；边界检查避免"新能源汽车"误匹配"新能源科技" |
| 模糊匹配 | 单向包含匹配（name in table_name），取最长匹配，最小长度 ≥ 3 | "比亚迪" 能匹配 "比亚迪股份"；"宁德时代" 能匹配 "宁德时代"；"东方"（2字）不触发，避免误判 |
| 非上市企业 | 查不到即视为非上市 | 无需维护排除名单，akshare 查不到华为自然返回 None |
| 降级标记 | `__keyword_registry__` 字符串（非 bool `True`） | `True` 会破坏 `Optional[str]` 类型一致性；`__keyword_registry__` 是 str 子类型，不破坏类型；`resolved_code` 排除该标记返回 None |
| 序列化 | `EntityInfo.to_dict()`/`from_dict()` | `AgentSpec.context` 可能经 JSON 序列化（消息队列、持久化），dataclass 对象会退化为 dict |
| async/sync 边界 | `resolve()` 为 async，`_get_data_collection_skills()` 保持同步 | `_get_data_collection_skills()` 被 `dynamic_orchestrator.py:134` 同步调用，不能改 async；异步 resolve 仅在 `decompose()` 入口调用，结果通过 `pre_resolved_entities` 传递给同步函数 |
| 一次解析 | `decompose()` 入口 async 调用一次，`pre_resolved_entities` 传递给下游同步函数 | 避免三处独立调用 `resolve()` 导致重复正则匹配和反向扫描；async/sync 边界在 `decompose()` 处 |

## 5. 修改点

### 5.1 `src/core/decomposition/strategies.py` — `_get_data_collection_skills()`

**当前逻辑**：仅根据 aspect 关键词匹配决定是否注入 stock_data

**约束**：`_get_data_collection_skills()` 被同步调用（`strategies.py:528`、`dynamic_orchestrator.py:134`），不能直接改为 async。

**修改后**（保持同步签名，通过 `pre_resolved_entities` 接收上游异步结果）：

```python
def _get_data_collection_skills(
    aspect: str,
    topic: str = "",
    intent_result: Any = None,
    pre_resolved_entities: Optional[List[EntityInfo]] = None,
) -> List[str]:
    db_skills: List[str] = []
    web_skills: List[str] = []
    llm_skills: List[str] = []

    base_skills = ["search_skill", "news_search", "llm_skill"]
    aspect_skills: List[str] = []
    aspect_lower = aspect.lower()

    # === 新增：基于主体解析注入 stock_data ===
    # 使用上游已解析的结果（一次解析，结果传播），避免重复调用 resolve()
    listed_entities = []
    if pre_resolved_entities:
        listed_entities = [e for e in pre_resolved_entities if e.is_listed]
    if listed_entities:
        if "stock_data" not in aspect_skills:
            aspect_skills.append("stock_data")

    # 原有关键词匹配保留（补充维度）
    for keyword, extra_skills in DATA_SOURCE_SKILL_MAP.items():
        if keyword in aspect_lower:
            aspect_skills.extend(extra_skills)

    # 原有 intent 判断保留
    if intent_result:
        primary_type = getattr(intent_result, 'primary_research_type', None)
        if primary_type and getattr(primary_type, 'value', '') in (
            "company_research", "investment", "competitive_analysis"
        ):
            if "stock_data" not in aspect_skills:
                aspect_skills.append("stock_data")

    all_unique = list(dict.fromkeys(aspect_skills + base_skills))
    for skill in all_unique:
        tier = SKILL_PRIORITY_MAP.get(skill, "web_search")
        if tier == "structured_db":
            db_skills.append(skill)
        elif tier == "llm":
            llm_skills.append(skill)
        else:
            web_skills.append(skill)
    return db_skills + web_skills + llm_skills
```

**变化**：
1. 函数保持同步签名（`def`，非 `async def`），不破坏现有调用方
2. 新增 `pre_resolved_entities` 参数：接收上游 `decompose()` 中异步解析的结果
3. 不在函数内部调用 `resolver.resolve()`（异步调用必须在上游完成）

### 5.2 `src/core/decomposition/strategies.py` — 分解时传递 EntityInfo

**约束**：`IndustryResearchStrategy.decompose()` 是同步函数，但 `EntityResolver.resolve()` 是异步的。解决方案：在 `decompose()` 入口用 `asyncio.run()` 或检查事件循环状态来调用异步 `resolve()`。

> **重要**：在实际运行环境中，`decompose()` 被 `research_api.py` 的 async 上下文调用，因此可以用 `await` 包装。但基类签名是同步的，改动需要同时更新基类。具体实现时需评估两种路径：
>
> **路径A（推荐）**：将 `TaskDecompositionStrategy.decompose()` 改为 `async def`，所有子类和调用方同步更新。这是最干净的方案，因为调用方（`research_api.py`）本身就在 async 上下文中。
>
> **路径B（最小改动）**：保持 `decompose()` 同步，在函数内部通过 `asyncio.get_running_loop().run_until_complete()` 或缓存预热的方式获取结果。但这在有事件循环时不可行（会抛出 RuntimeError）。
>
> 以下按**路径A**展示：

```python
# 基类改为 async（所有子类和调用方需同步更新）
class TaskDecompositionStrategy(ABC):
    @abstractmethod
    async def decompose(
        self, 
        requirement: Any, 
        intent_result: Any,
        framework_config: Any
    ) -> DecompositionPlan:
        pass

# IndustryResearchStrategy.decompose() 同步更新
async def decompose(self, requirement, intent_result, framework_config):
    topic = getattr(requirement, 'topic', '') or ''
    
    # === 一次解析，结果传播 ===
    resolved_entities: List[EntityInfo] = []
    if topic:
        try:
            from src.core.entity_resolver import get_entity_resolver
            resolver = get_entity_resolver()
            resolved_entities = await resolver.resolve(topic)
        except Exception:
            pass

    # ... 原有分解逻辑 ...

    # 在创建 DATA_COLLECTION phase 的 AgentSpec 时，传递已解析的实体
    for aspect in normal_aspects:
        skills = _get_data_collection_skills(
            aspect, topic, intent_result,
            pre_resolved_entities=resolved_entities,  # 传入已解析结果
        )
        spec = AgentSpec(
            ...,
            context={
                "aspect": aspect,
                "topic": topic,
                "entities": [e.to_dict() for e in resolved_entities],  # 序列化为 dict
                ...
            },
        )
```

> **调用方更新**：`research_api.py` 等调用 `decompose()` 的地方需加 `await`。`dynamic_orchestrator.py:134` 的 `_get_data_collection_skills(aspect, topic)` 同步调用不受影响（`_get_data_collection_skills` 保持同步）。

**关键设计**：
1. `resolve()` 仅在 `decompose()` 入口调用一次（异步）
2. 结果通过 `pre_resolved_entities` 参数传递给 `_get_data_collection_skills()`（同步），避免函数内部需要异步
3. 写入 `context` 时使用 `to_dict()` 序列化，消费方通过 `from_dict()` 反序列化

### 5.3 `src/core/task_structure.py` — `_infer_skills()`

**注意**：`_infer_skills()` 负责 DEEP_ANALYSIS 阶段的 skill 推断，而 `ASPECT_SKILL_MAP` 已覆盖常见场景（如 `"Financial Analysis" → stock_analysis`）。主体解析仅补充 `ASPECT_SKILL_MAP` 未覆盖的场景，避免职责重叠。

**约束**：`_infer_skills()` 是同步函数，被 `_analyze_with_rules()` 同步调用。通过 `pre_resolved_entities` 参数接收上游已解析结果。

```python
def _infer_skills(
    self,
    aspect: str,
    role: SectionRole,
    intent: DeepIntentResult,
    pre_resolved_entities: Optional[List[Dict]] = None,
) -> List[str]:
    skills = {"llm_skill"}

    if role == SectionRole.DATA_COLLECTION:
        skills.add("search_skill")

    if role == SectionRole.ANALYSIS:
        skills.add("search_skill")
        aspect_lower = aspect.lower()

        # === 新增：基于主体解析注入 stock 相关 skill ===
        # 仅当 ASPECT_SKILL_MAP 未覆盖时才注入，避免职责重叠
        if pre_resolved_entities:
            from src.core.decomposition.strategies import get_skills_for_aspect
            from src.core.entity_resolver import EntityInfo
            aspect_skills_set = set(get_skills_for_aspect(aspect))
            has_stock_skill = "stock_analysis" in aspect_skills_set

            if not has_stock_skill:
                entities = [EntityInfo.from_dict(e) for e in pre_resolved_entities]
                if any(e.is_listed for e in entities):
                    skills.add("stock_analysis")
                    skills.add("data_analysis")

        # 原有关键词匹配逻辑保留...
        if any(kw in aspect_lower for kw in ["财务", "估值", "financial", "营收", "利润", "市值"]):
            skills.add("stock_analysis")
            skills.add("data_analysis")
        ...
```

> **调用方更新**：`_analyze_with_rules()` 需新增 `pre_resolved_entities` 参数，由上游 async 上下文传入。

### 5.4 `src/core/agents/generic_agent.py` — 利用 context 中的 EntityInfo

**当前问题**：`_extract_stock_symbol()` 和 `_resolve_company_to_code()` 在运行时重新解析，重复查询

**修改**：优先从 context 中读取已解析的 EntityInfo（通过 `from_dict()` 反序列化）：

```python
async def _fetch_structured_data(self, stock_skill, topic, aspect, skill_name="stock_data"):
    result = {"data_points": [], "sources": [], "canonical_metrics": {}}
    try:
        # 优先从 context 获取已解析的股票代码（支持多主体）
        symbols = []
        raw_entities = (self._context or {}).get("entities", [])
        if raw_entities:
            from src.core.entity_resolver import EntityInfo
            entities = [
                EntityInfo.from_dict(e) if isinstance(e, dict) else e
                for e in raw_entities
            ]
            listed = [e for e in entities if e.is_listed and e.resolved_code]
            if listed:
                symbols = [e.resolved_code for e in listed]

        # 兜底：原有解析逻辑（单主体）
        if not symbols:
            symbol = self._extract_stock_symbol(topic)
            if symbol:
                symbols = [symbol]

        if not symbols:
            return result

        # 对每个上市主体分别获取数据
        for symbol in symbols:
            actions = self._infer_stock_actions(aspect)
            for action in actions:
                try:
                    skill_result = await stock_skill.execute(
                        action=action, symbol=symbol,
                    )
                    # ... 后续逻辑不变
```

**关键设计**：
1. `context["entities"]` 中的数据可能是 dict（经 JSON 序列化/反序列化）或 EntityInfo 对象，通过 `isinstance(e, dict)` 判断后选择 `from_dict()` 或直接使用
2. 仅使用 `resolved_code`（排除降级标记 `True`），降级场景走原有 `_extract_stock_symbol()` 兜底

### 5.5 `src/core/agents/generic_agent.py` — 增强搜索补充

当 stock_data 返回数据不足时，针对上市/非上市主体生成不同的补充查询：

```python
# 在 _generate_structured_fallback_queries() 中增强
def _generate_structured_fallback_queries(self, topic, aspect):
    queries = []
    raw_entities = (self._context or {}).get("entities", [])

    if raw_entities:
        from src.core.entity_resolver import EntityInfo
        entities = [
            EntityInfo.from_dict(e) if isinstance(e, dict) else e
            for e in raw_entities
        ]
        for entity in entities:
            if entity.is_listed:
                queries.extend([
                    f"{entity.name} 年度报告 年报",
                    f"{entity.name} 研究报告 券商",
                ])
            else:
                queries.extend([
                    f"{entity.name} 最新动态 行业分析",
                    f"{entity.name} 深度分析",
                ])

    # 原有基于 aspect 的查询保留...
    ...
    return queries
```

### 5.6 `config/keyword_mappings.yaml` — 修正名单

```yaml
listed_company_indicators:
  suffixes:
    - "公司"
    - "集团"
    - "股份"
    - "有限"
  names:
    - "比亚迪"
    - "腾讯"
    - "阿里巴巴"
    # 移除 "华为" — 非上市
    # 移除 "字节" — 非上市
    - "茅台"
    - "宁德"
    - "万科"
    - "蔚来"
    - "小鹏"
    - "理想"
    - "京东"
    - "拼多多"
    - "美团"
    - "小米"
    - "网易"
    - "百度"
    - "中芯"
    - "海尔"
    - "格力"
```

> 注意：此名单仅作为 `_is_likely_company_name()` 的后备判断。主体级判断以 EntityResolver 为准。

### 5.7 `requirements.txt` — 声明依赖

```
akshare>=1.18.0
```

### 5.8 `requirements-optional.txt` — 可选依赖

```
pyahocorasick>=0.9.0  # 可选：EntityResolver 反向匹配加速（O(text_length) vs O(5000×N)）
```

> **说明**：akshare 已在运行时使用但未声明为依赖，必须加入 `requirements.txt`。`pyahocorasick` 为可选依赖，未安装时反向匹配自动禁用，不影响精确匹配和包含匹配。

## 6. 数据流完整示例

**输入**："新能源汽车行业竞争格局分析"

```
1. decompose() 入口：await resolver.resolve("新能源汽车行业竞争格局分析")
   → _extract_entities:
     ├── 后缀模式：无匹配（"新能源汽车"不含"公司/集团/股份/有限"）
     └── Aho-Corasick 自动机：扫描文本，无 A 股公司名完整匹配
        （"新能源"不是公司名，边界检查排除子串误匹配）
   → resolved_entities = []

2. _get_data_collection_skills(aspect="竞争格局", pre_resolved_entities=[])
   → 无上市主体，不注入 stock_data
   → DATA_SOURCE_SKILL_MAP 中 "竞争" 无映射
   → 使用搜索获取数据

3. agent 执行：
   → context["entities"] = []
   → _fetch_structured_data: 无已解析代码，走 _extract_stock_symbol 兜底
   → 搜索结果中发现提及"比亚迪"、"宁德时代"
   → 触发 _extract_stock_symbol → _resolve_company_to_code
   → 解析成功，后续子查询使用 stock_data
```

**输入**："比亚迪财务与估值分析"

```
1. decompose() 入口：await resolver.resolve("比亚迪财务与估值分析")
   → _extract_entities:
     ├── 后缀模式：无匹配
     └── Aho-Corasick 自动机：扫描到"比亚迪"（边界检查通过）
   → _resolve_to_code("比亚迪"): "002594"  (akshare 缓存表精确匹配)
   → resolved_entities = [EntityInfo("比亚迪", "002594", is_listed=True)]

2. _get_data_collection_skills(aspect="财务与估值", pre_resolved_entities=[...])
   → 有上市主体 → 注入 stock_data
   → DATA_SOURCE_SKILL_MAP 匹配 "财务"→stock_data（去重）
   → skills = ["stock_data", "search_skill", "news_search", "llm_skill"]

3. agent 执行：
   → context["entities"] = [{"name":"比亚迪", "stock_code":"002594", "is_listed":True}]
   → _fetch_structured_data: EntityInfo.from_dict() → resolved_code="002594"
   → 直接用 "002594" 获取年报、财务报表、关键指标
   → 不足部分补充搜索："比亚迪 年度报告 年报", "比亚迪 研究报告 券商"
```

**输入**："华为与苹果技术路线对比"

```
1. decompose() 入口：await resolver.resolve("华为与苹果技术路线对比")
   → _extract_entities:
     ├── 后缀模式：无匹配
     └── Aho-Corasick 自动机：无匹配
        （华为非A股上市，苹果为美股上市，均不在A股缓存表中）
   → resolved_entities = []

2. _get_data_collection_skills(aspect="技术路线", pre_resolved_entities=[])
   → 无上市主体 → 不注入 stock_data → 全部走搜索
   → 补充查询："华为 最新动态 行业分析", "苹果 最新动态 行业分析"
   → 后续可扩展：增加港股/美股缓存表覆盖腾讯、苹果等
```

**网络不可用场景**："比亚迪财务分析"（akshare 离线）

```
1. 首次启动（无磁盘缓存）：
   → _ensure_table_loaded: akshare ConnectionError
   → _table_loaded = False
   → _resolve_to_code("比亚迪"): 降级到 keyword_registry
   → keyword_registry.is_listed_company_topic("比亚迪") = True
   → 返回 "__keyword_registry__"（特殊标记，表示上市但代码未知）
   → EntityInfo("比亚迪", stock_code="__keyword_registry__", is_listed=True)
   → resolved_code = None（isinstance("__keyword_registry__", str) 为 True，但 resolved_code 检查 "__keyword_registry__" 不为有效代码）
   → _fetch_structured_data: 无 resolved_code，走 _extract_stock_symbol 兜底
   → _extract_stock_symbol 同样依赖 akshare → 失败 → 纯搜索模式

2. 二次启动（有磁盘缓存，未过期）：
   → _ensure_table_loaded: 从 ~/.cache/market_report/stock_name_table.pkl 加载
   → _table_loaded = True（毫秒级）
   → _resolve_to_code("比亚迪"): "002594"（精确匹配）
   → 正常使用 stock_data

3. 缓存过期（>24h）：
   → 加载旧缓存 + 后台异步刷新（asyncio.ensure_future）
   → 当前请求使用旧缓存正常响应
   → 刷新成功：更新内存表 + 保存新缓存
   → 刷新失败：保留旧缓存，下次重试
```

## 7. 修改文件清单

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `src/core/entity_resolver.py` | **新增** | 主体解析器，A股公司名缓存表，磁盘缓存，Aho-Corasick 自动机 |
| `src/core/decomposition/strategies.py` | 修改 | `_get_data_collection_skills()` 新增 `pre_resolved_entities` 参数（保持同步）；`decompose()` 改为 async，入口调用一次 `resolve()` |
| `src/core/task_structure.py` | 修改 | `_infer_skills()` 加入 `pre_resolved_entities` 参数，仅补充 `ASPECT_SKILL_MAP` 未覆盖场景 |
| `src/core/agents/generic_agent.py` | 修改 | 优先从 context 读 EntityInfo（`from_dict()` 反序列化）；增强搜索补充查询 |
| `config/keyword_mappings.yaml` | 修改 | 移除非上市企业 |
| `requirements.txt` | 修改 | 新增 `akshare>=1.18.0` |
| `requirements-optional.txt` | **新增** | `pyahocorasick>=0.9.0`（可选反向匹配加速） |

## 8. 风险与应对

| 风险 | 严重度 | 应对 |
|------|--------|------|
| akshare 首次加载公司名表耗时（约5-10秒） | 中 | 惰性加载，不阻塞启动；通过 `run_in_executor` 不阻塞事件循环；加载前用 keyword_registry 作后备 |
| akshare 不可用（未安装/网络问题） | **高** | 三级降级：(1) 磁盘缓存（pickle，TTL 24h），(2) 过期缓存 + 后台异步刷新，(3) keyword_registry 硬编码名单；agent 兜底走 `_extract_stock_symbol()` |
| `threading.Lock` 阻塞事件循环 | **高** | 使用 `asyncio.Lock` + `run_in_executor`；akshare 同步调用在 executor 中执行 |
| `decompose()` 改为 async 影响面 | **高** | 基类 `TaskDecompositionStrategy.decompose()` + 5个子类（Industry/Company/Competitor/Fix/Evaluation）+ 所有调用方（`research_api.py`等）需同步更新；`dynamic_orchestrator.py` 的 `to_decomposition_plan()` 也调用 `_get_data_collection_skills` 但不受影响（该函数保持同步） |
| `_get_data_collection_skills()` 同步/异步 | **高** | 保持同步签名，不破坏 `dynamic_orchestrator.py:134` 的同步调用；异步 `resolve()` 仅在 `decompose()` 入口调用，结果通过 `pre_resolved_entities` 传递 |
| 反向匹配性能 O(5000×N) | **高** | Aho-Corasick 自动机 O(text_length)；可选依赖 `pyahocorasick`，未安装时禁用反向匹配 |
| 反向匹配误匹配（如"新能源汽车"匹配"新能源科技"） | 中 | Aho-Corasick 边界检查：匹配串前后必须为非中文字符或字符串边界 |
| 包含匹配短名误判（如"东方"匹配"东方财富"） | 中 | 最小匹配长度阈值 `_MIN_FUZZY_MATCH_LEN = 3`，2字短名不触发包含匹配 |
| EntityInfo 不可序列化 | 中 | `to_dict()`/`from_dict()` 序列化方法；写入 context 时序列化为 dict，消费方反序列化 |
| 多处重复调用 `resolve()` | 中 | `decompose()` 入口一次解析 + `pre_resolved_entities` 参数传递 + 文本级缓存 `_full_resolve_cache` |
| `_infer_skills()` 与 `ASPECT_SKILL_MAP` 职责重叠 | 低 | 主体解析仅补充 `ASPECT_SKILL_MAP` 未覆盖场景（如"竞争格局"） |
| 港股/美股上市公司未覆盖 | 低 | 当前仅覆盖 A 股，后续可扩展 akshare 港股/美股接口 |
| 同一主体在不同 aspect 下需要不同数据 | 低 | EntityInfo 按主体维度，不按 aspect 维度；具体数据由 agent 的 `_infer_stock_actions(aspect)` 决定 |
| `pyahocorasick` C 扩展安装失败 | 低 | 可选依赖，未安装时反向匹配禁用；精确匹配和包含匹配不受影响；可 pip install pyahocorasick 或 conda install |
