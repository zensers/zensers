# v3 修正增量

> 基于 v2 的 5 项增量修正。仅列出变更部分，未提及的与 v2 完全一致。

---

## 修正 A — _collect_new_files 快速预过滤

**问题**: v2 将所有文件丢给 `import_file(skip_if_imported=True)`，后者做完整 MD5 读取。对含 10,000 个已导入 PDF 的目录，每 5 分钟触发 10,000 次 MD5。

**修复**: 用 mtime+size 快照做预过滤，仅扫描有变更的文件。

```python
# dream_scheduler.py

class DreamModeScheduler:
    def __init__(self, ...):
        # ... 已有代码 ...
        self._scan_snapshots: Dict[str, Set[tuple]] = {}  # dir → {(name, mtime, size)}

    def _collect_new_files(self, source_dir: Path) -> List[str]:
        """收集新增或变更的文件（基于 mtime+size 快照，不做 MD5）"""
        supported_ext = {'.md', '.txt', '.csv', '.json', '.pdf', '.docx', '.xlsx', '.xls'}
        current_snapshot: Set[tuple] = set()
        new_files: List[str] = []

        dir_key = str(source_dir.resolve())
        prev_snapshot = self._scan_snapshots.get(dir_key, set())

        for f in sorted(source_dir.rglob("*")):
            if not f.is_file() or f.suffix.lower() not in supported_ext:
                continue
            stat = f.stat()
            entry = (f.name, stat.st_mtime, stat.st_size)
            current_snapshot.add(entry)
            if entry not in prev_snapshot:
                new_files.append(str(f))

        self._scan_snapshots[dir_key] = current_snapshot
        return new_files
```

**对比**:

| 指标 | v2 | v3（修正后） |
|------|----|-------------|
| 10,000 文件扫描 | 10,000 次 MD5 + import_file | 10,000 次 stat（毫秒级）+ 0 次 import_file |
| 新增 1 个文件 | 10,001 次 MD5 + 1 次 import_file | 10,001 次 stat + 1 次 import_file |
| 文件删除处理 | 忽略（manifest 残留） | 忽略（manifest 残留，同上） |

---

## 修正 B — DreamModeConfig.from_env()

**问题**: v2 在 `main.py` 中手写 `os.getenv`，打破了 `KnowledgeConfig.from_env()` 的配置加载模式。

**修复**: 给 `DreamModeConfig` 增加 `from_env()` 方法。

```python
# dream_scheduler.py

@dataclass
class DreamModeConfig:
    # ... 所有字段 ...

    @classmethod
    def from_env(cls) -> "DreamModeConfig":
        """从环境变量加载配置

        环境变量前缀: DREAM_ （区别于 KnowledgeConfig 的 KNOWLEDGE_ 前缀）
        """
        import os

        def _env(key: str, default: str) -> str:
            return os.getenv(f"DREAM_{key}", default)

        def _env_int(key: str, default: int) -> int:
            val = os.getenv(f"DREAM_{key}")
            return int(val) if val else default

        def _env_bool(key: str, default: bool) -> bool:
            val = os.getenv(f"DREAM_{key}")
            if val is None:
                return default
            return val.lower() in ("true", "1", "yes")

        raw_dirs = os.getenv("DREAM_SOURCE_DIRS", "")

        return cls(
            trigger_after_task=_env_bool("TRIGGER_AFTER_TASK", True),
            trigger_on_idle_seconds=_env_int("TRIGGER_ON_IDLE_SECONDS", 30),
            trigger_on_pending_threshold=_env_int("TRIGGER_ON_PENDING_THRESHOLD", 10),
            batch_size=_env_int("BATCH_SIZE", 10),
            max_duration_seconds=_env_int("MAX_DURATION_SECONDS", 300),
            min_interval_seconds=_env_int("MIN_INTERVAL_SECONDS", 60),
            max_concurrent_tasks=_env_int("MAX_CONCURRENT_TASKS", 1),
            idle_check_interval=_env_int("IDLE_CHECK_INTERVAL", 10),
            knowledge_auto_import=_env_bool("AUTO_IMPORT", True),
            knowledge_scan_interval=_env_int("SCAN_INTERVAL", 300),
            knowledge_source_dirs=tuple(
                d.strip() for d in raw_dirs.split(",") if d.strip()
            ),
            knowledge_store_to_bank=_env_bool("STORE_TO_BANK", True),
            import_max_workers=_env_int("IMPORT_MAX_WORKERS", 2),
        )
```

**main.py 同步简化**:

```python
# src/api/main.py

_dream_cfg = DreamModeConfig.from_env()
_dream_scheduler = DreamModeScheduler(
    knowledge_bank=_knowledge_manager.knowledge_bank,
    raw_data_store=RawResearchDataStore(),
    config=_dream_cfg,
)
if _dream_cfg.knowledge_source_dirs:
    _dream_scheduler.start_background()
```

**环境变量文档**:

| 变量 | 默认 | 说明 |
|------|------|------|
| `DREAM_SOURCE_DIRS` | "" (空) | 逗号分隔的源目录列表 |
| `DREAM_SCAN_INTERVAL` | 300 | 扫描间隔（秒） |
| `DREAM_AUTO_IMPORT` | true | 是否启用自动导入 |
| `DREAM_STORE_TO_BANK` | true | 是否写入 SQLite |
| `DREAM_IMPORT_MAX_WORKERS` | 2 | 导入并发数 |
| `DREAM_TRIGGER_AFTER_TASK` | true | 主任务完成后触发 |
| `DREAM_IDLE_CHECK_INTERVAL` | 10 | 空闲检查间隔（秒） |

---

## 修正 C — compiled_knowledge 提前赋值

**问题**: `result.compiled_knowledge = knowledge` 放在 `save_knowledge()` 之后。若文件系统写入失败抛出异常，编译结果丢失。

**修复**: 赋值移到 `save_knowledge()` 之前。

```python
# importer.py — import_file() 方法

knowledge = self.compiler.compile_research(
    raw_content=content,
    source_info=source_info or {
        "title": Path(file_path).stem,
        "type": "imported_file",
        "path": file_path,
    },
)
result.compiled_knowledge = knowledge  # ← 移至此处，先于 save_knowledge

self.compiler.save_knowledge(knowledge)  # 即使失败，compiled_knowledge 已保存

stats = knowledge.get_stats()
result.pages_created = stats["total"]
result.entities_extracted = stats["entities"]
```

同样适用于 `import_url()`:

```python
# importer.py — import_url() 方法

knowledge = self.compiler.compile_research(...)
result.compiled_knowledge = knowledge  # ← 提前
self.compiler.save_knowledge(knowledge)
```

---

## 修正 D — per-directory 锁

**问题**: 类级 `_save_lock` 导致不同知识库目录的写入互相阻塞。

**修复**: 使用 per-directory 锁字典。

```python
# compiler.py

class KnowledgeCompiler:
    _save_locks: Dict[str, threading.Lock] = {}
    _lock_lock = threading.Lock()  # 保护锁字典本身

    def _get_lock(self) -> threading.Lock:
        """获取当前 knowledge_root 的专用锁"""
        key = str(self.knowledge_root.resolve())
        with self._lock_lock:
            if key not in self._save_locks:
                self._save_locks[key] = threading.Lock()
            return self._save_locks[key]

    def save_knowledge(self, knowledge: CompiledKnowledge):
        lock = self._get_lock()
        with lock:
            for page in knowledge.concepts:
                self._save_page(page, "concepts")
            for page in knowledge.entities:
                self._save_page(page, "entities")
            for page in knowledge.relations:
                self._save_page(page, "relations")
```

---

## 修正 E — 修复现有 bug: _store_to_knowledge_bank 移除无效参数

**问题**: 现有 `knowledge_extraction_phase.py:422` 传入 `confidence=entity.get("confidence", 0.8)` 给 `add_entity()`，但 `EntityStore.add_entity` 不接受此参数 → `TypeError`。

**修复**: 移除 `confidence` 参数。

```python
# knowledge_extraction_phase.py:421-427

# 修复前
self.knowledge_bank.entities.add_entity(
    entity_type=entity_type,
    name=name,
    description=entity.get("description", ""),
    confidence=entity.get("confidence", 0.8)  # ← TypeError
)

# 修复后
self.knowledge_bank.entities.add_entity(
    entity_type=entity_type,
    name=name,
    description=entity.get("description", ""),
)
```

**影响范围**: 仅 `knowledge_extraction_phase.py`。此 bug 意味着 EntityExtractor 提取的所有实体在写入 SQLite 时都会抛出 TypeError，生产环境可能从未实际存储过实体。修复后可恢复正常存储。

---

## 变更矩阵（终版）

| 文件 | 变更 | 行数 |
|------|------|------|
| `dream_scheduler.py` | `DreamModeConfig.from_env()` + 扫描过滤 + per-dir snapshot | +50 |
| `compiler.py` | per-directory 锁 | +10 |
| `importer.py` | compiled_knowledge 提前赋值 | +2 |
| `knowledge_extraction_phase.py` | 移除无效 confidence 参数 | -1 |
| `knowledge_bank.py` | （同 v2，无需修改） | 0 |
| `knowledge_manager.py` | （同 v2，无需修改） | 0 |
| `main.py` | 使用 `DreamModeConfig.from_env()` | -5 |
| **净变更** | | **~56** |

v2 的 ~275 行 + v3 修正 ~56 行 = **总变更约 280 行**。

```
v2 ──────→ v3
  DreamModeConfig.from_env() ← 新增
  _collect_new_files 预过滤   ← 新增
  per-directory 锁            ← 新增
  compiled_knowledge 提前      ← 修正
  移除 confidence 参数         ← 新增（修复现有 bug）
  其他同 v2                    ← 不变
```
