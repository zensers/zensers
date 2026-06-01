#!/usr/bin/env python3
"""
Registries 迁移脚本

将 data/registries/registries/ 嵌套目录中的数据合并到正确的 data/registries/ 目录。

背景：
  agent_coordinator.py:558 曾错误地将 registries_dir 的值当做 storage_path
  传入 AgentSessionRegistry.save()，导致产生 data/registries/registries/ 嵌套。

用法：
  python scripts/migrate_registries.py          # 预览模式，不实际移动
  python scripts/migrate_registries.py --apply  # 执行迁移
  python scripts/migrate_registries.py --apply --cleanup  # 迁移后删除嵌套目录
"""

import json
import shutil
import sys
from pathlib import Path

REGISTRIES_DIR = Path("data/registries")
NESTED_DIR = REGISTRIES_DIR / "registries"


def get_file_info(path: Path):
    """获取文件大小和最后修改时间"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        session_count = len(data.get("child_sessions", {}))
    except Exception:
        session_count = -1
    return {
        "size_bytes": path.stat().st_size,
        "mtime": path.stat().st_mtime,
        "session_count": session_count,
    }


def migrate(dry_run: bool = True, cleanup: bool = False):
    if not NESTED_DIR.exists():
        print("[SKIP] 嵌套目录不存在，无需迁移")
        return

    top_files = {f.name: f for f in REGISTRIES_DIR.glob("*.json")}
    nested_files = {f.name: f for f in NESTED_DIR.glob("*.json")}

    # 1. 文件仅存于嵌套目录 → 复制到顶层
    only_nested = set(nested_files.keys()) - set(top_files.keys())
    for name in sorted(only_nested):
        src = nested_files[name]
        info = get_file_info(src)
        print(f"[ONLY NESTED] {name} ({info['size_bytes']/1024:.1f} KB, sessions={info['session_count']})")
        if not dry_run:
            dst = REGISTRIES_DIR / name
            shutil.copy2(src, dst)
            print(f"  -> Copied to registries/{name}")

    # 2. 文件同时在两层 → 保留较大版本
    both = set(top_files.keys()) & set(nested_files.keys())
    for name in sorted(both):
        top_f = top_files[name]
        nested_f = nested_files[name]
        top_info = get_file_info(top_f)
        nested_info = get_file_info(nested_f)

        keep_nested = nested_info["size_bytes"] > top_info["size_bytes"]
        keeper = "nested" if keep_nested else "top"

        print(
            f"[BOTH] {name}: "
            f"top={top_info['size_bytes']/1024:.1f}KB(sessions={top_info['session_count']}), "
            f"nested={nested_info['size_bytes']/1024:.1f}KB(sessions={nested_info['session_count']}) "
            f"→ keep {keeper}"
        )

        if not dry_run and keep_nested:
            dst = REGISTRIES_DIR / name
            shutil.copy2(nested_f, dst)
            print(f"  -> Overwritten registries/{name} with nested version")

    # 3. 文件仅存于顶层（信息输出）
    only_top = set(top_files.keys()) - set(nested_files.keys())
    if only_top:
        print(f"\n[ONLY TOP] {len(only_top)} files — 无嵌套副本，保持不变")
        for name in sorted(only_top):
            info = get_file_info(top_files[name])
            print(f"  {name} ({info['size_bytes']/1024:.1f} KB, sessions={info['session_count']})")

    # 汇总
    print(f"\n=== 汇总 ===")
    print(f"  Only in nested: {len(only_nested)} files")
    print(f"  Both: {len(both)} files")
    print(f"  Only in top: {len(only_top)} files")

    total_nested_size = sum(f.stat().st_size for f in NESTED_DIR.glob("*.json"))
    print(f"  Nested total: {total_nested_size / 1024 / 1024:.1f} MB")

    # 4. 清理嵌套目录
    if not dry_run and cleanup:
        shutil.rmtree(NESTED_DIR)
        print(f"\n[CLEANUP] 嵌套目录已删除: {NESTED_DIR}")
    elif not dry_run and not cleanup:
        print(f"\n嵌套目录未删除（如需清理请添加 --cleanup 参数）")
    elif dry_run:
        if only_nested or both:
            print(f"\n这是预览模式。使用 --apply 执行迁移，--apply --cleanup 迁移后清理。")


if __name__ == "__main__":
    dry_run = "--apply" not in sys.argv
    cleanup = "--cleanup" in sys.argv
    migrate(dry_run=dry_run, cleanup=cleanup)
