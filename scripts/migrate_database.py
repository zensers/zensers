# -*- coding: utf-8 -*-
"""
数据库迁移脚本 - 7个数据库合并为1个

将分散的知识管理数据库整合为单一数据库文件。

使用方式：
    # 模拟运行（默认，安全）
    python scripts/migrate_database.py --user-id user_001 --dry-run
    
    # 实际迁移
    python scripts/migrate_database.py --user-id user_001
    
    # 指定数据目录
    python scripts/migrate_database.py --user-id user_001 --data-dir ./data

安全措施：
    1. 默认 dry_run=True，仅打印SQL不执行
    2. 自动备份所有源数据库
    3. 验证备份完整性
    4. 验证迁移后数据完整性
    5. 保留备份30天
"""

import os
import sys
import sqlite3
import shutil
import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any


def get_source_databases(base_path: str, user_id: str) -> List[Tuple[str, str]]:
    """
    获取源数据库列表
    
    Returns:
        [(名称, 路径), ...]
    """
    data_dir = Path(base_path)
    
    databases = [
        ("temporal", f"knowledge_bank_{user_id}_temporal.db"),
        ("provenance", f"knowledge_bank_{user_id}_provenance.db"),
        ("learning", f"knowledge_bank_{user_id}_learning.db"),
        ("errors", f"knowledge_bank_{user_id}_errors.db"),
        ("feature_requests", f"knowledge_bank_{user_id}_feature_requests.db"),
        ("contradictions", f"knowledge_bank_{user_id}_contradictions.db"),
    ]
    
    result = []
    for name, filename in databases:
        path = data_dir / filename
        if path.exists():
            result.append((name, str(path)))
    
    return result


def get_all_tables(db_path: str) -> List[str]:
    """获取数据库中的所有表名"""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()
    return tables


def get_table_schema(db_path: str, table_name: str) -> str:
    """获取表的创建语句"""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def count_rows(db_path: str, table_name: str) -> int:
    """统计表中的行数"""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(f"SELECT COUNT(*) FROM {table_name}")
    count = cursor.fetchone()[0]
    conn.close()
    return count


def verify_file_integrity(source: str, backup: str) -> bool:
    """验证文件备份完整性"""
    if not os.path.exists(source) or not os.path.exists(backup):
        return False
    source_size = os.path.getsize(source)
    backup_size = os.path.getsize(backup)
    return source_size == backup_size


def copy_table(source_conn: sqlite3.Connection, target_conn: sqlite3.Connection, table_name: str):
    """复制表结构和数据"""
    # 获取表结构
    cursor = source_conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    row = cursor.fetchone()
    if not row or not row[0]:
        print(f"  [SKIP] No schema for table {table_name}")
        return
    
    schema = row[0]
    
    # 在目标数据库创建表
    try:
        target_conn.execute(schema)
    except sqlite3.OperationalError as e:
        if "already exists" not in str(e):
            print(f"  [ERROR] Failed to create table {table_name}: {e}")
            return
    
    # 获取列名
    cursor = source_conn.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    
    if not columns:
        return
    
    # 复制数据
    placeholders = ", ".join(["?" for _ in columns])
    column_names = ", ".join(columns)
    
    cursor = source_conn.execute(f"SELECT {column_names} FROM {table_name}")
    
    for row in cursor:
        try:
            target_conn.execute(
                f"INSERT OR IGNORE INTO {table_name} ({column_names}) VALUES ({placeholders})",
                row
            )
        except sqlite3.IntegrityError:
            # 忽略重复键
            pass


def migrate_to_single_db(
    user_id: str,
    data_dir: str = "data",
    dry_run: bool = True,
    backup_days: int = 30
) -> Dict[str, Any]:
    """
    迁移到单一数据库
    
    Args:
        user_id: 用户ID
        data_dir: 数据目录
        dry_run: 是否仅模拟运行
        backup_days: 备份保留天数
    
    Returns:
        迁移结果
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(data_dir, f"backup_{timestamp}")
    
    main_db_path = os.path.join(data_dir, f"knowledge_bank_{user_id}.db")
    source_dbs = get_source_databases(data_dir, user_id)
    
    result = {
        "user_id": user_id,
        "dry_run": dry_run,
        "timestamp": timestamp,
        "source_databases": [],
        "tables_migrated": [],
        "errors": [],
        "success": False
    }
    
    print(f"\n{'='*60}")
    print(f"数据库迁移脚本")
    print(f"{'='*60}")
    print(f"用户ID: {user_id}")
    print(f"数据目录: {data_dir}")
    print(f"模拟运行: {dry_run}")
    print(f"备份目录: {backup_dir}")
    print(f"{'='*60}\n")
    
    if not source_dbs:
        print("[INFO] 没有需要迁移的源数据库")
        result["success"] = True
        return result
    
    # ========== 1. 统计源数据库 ==========
    print("[STEP 1] 统计源数据库...")
    for name, path in source_dbs:
        tables = get_all_tables(path)
        row_counts = {t: count_rows(path, t) for t in tables}
        result["source_databases"].append({
            "name": name,
            "path": path,
            "tables": tables,
            "row_counts": row_counts
        })
        print(f"  - {name}: {len(tables)} 表, 总计 {sum(row_counts.values())} 行")
    
    if dry_run:
        print("\n[DRY_RUN] 模拟运行模式，以下操作不会实际执行：")
        for name, path in source_dbs:
            print(f"  - 迁移 {path} -> {main_db_path}")
        print(f"\n要执行实际迁移，请使用: --no-dry-run")
        result["success"] = True
        return result
    
    # ========== 2. 备份 ==========
    print("\n[STEP 2] 创建备份...")
    os.makedirs(backup_dir, exist_ok=True)
    
    for name, path in source_dbs:
        backup_path = os.path.join(backup_dir, os.path.basename(path))
        shutil.copy2(path, backup_path)
        print(f"  - 备份 {path} -> {backup_path}")
    
    # 备份主数据库
    if os.path.exists(main_db_path):
        backup_path = os.path.join(backup_dir, f"knowledge_bank_{user_id}.db")
        shutil.copy2(main_db_path, backup_path)
        print(f"  - 备份主数据库 -> {backup_path}")
    
    # ========== 3. 验证备份 ==========
    print("\n[STEP 3] 验证备份完整性...")
    for name, path in source_dbs:
        backup_path = os.path.join(backup_dir, os.path.basename(path))
        if not verify_file_integrity(path, backup_path):
            error_msg = f"备份验证失败: {path}"
            result["errors"].append(error_msg)
            print(f"  [ERROR] {error_msg}")
            return result
    print("  - 所有备份验证通过")
    
    # ========== 4. 执行迁移 ==========
    print("\n[STEP 4] 执行迁移...")
    target_conn = sqlite3.connect(main_db_path)
    target_conn.execute("PRAGMA foreign_keys = OFF")
    
    for name, path in source_dbs:
        print(f"\n  迁移 {name}...")
        source_conn = sqlite3.connect(path)
        source_conn.row_factory = sqlite3.Row
        
        tables = get_all_tables(path)
        for table in tables:
            row_count = count_rows(path, table)
            print(f"    - {table}: {row_count} 行")
            try:
                copy_table(source_conn, target_conn, table)
                result["tables_migrated"].append(f"{name}.{table}")
            except Exception as e:
                error_msg = f"迁移失败 {name}.{table}: {e}"
                result["errors"].append(error_msg)
                print(f"      [ERROR] {error_msg}")
        
        source_conn.close()
    
    target_conn.commit()
    target_conn.close()
    
    # ========== 5. 验证迁移 ==========
    print("\n[STEP 5] 验证迁移结果...")
    target_conn = sqlite3.connect(main_db_path)
    
    for db_info in result["source_databases"]:
        for table, expected_count in db_info["row_counts"].items():
            actual_count = count_rows(main_db_path, table)
            if actual_count >= expected_count:
                print(f"  - {table}: {actual_count} 行 (预期 {expected_count}) [OK]")
            else:
                error_msg = f"{table} 数据不完整: {actual_count} < {expected_count}"
                result["errors"].append(error_msg)
                print(f"  - {table}: {actual_count} 行 (预期 {expected_count}) [FAIL]")
    
    target_conn.close()
    
    # ========== 6. 创建清理脚本 ==========
    cleanup_script = os.path.join(backup_dir, "cleanup_instructions.txt")
    cleanup_date = datetime.now().replace(day=datetime.now().day + backup_days)
    
    with open(cleanup_script, "w") as f:
        f.write(f"""# 数据库迁移备份清理说明

备份时间: {timestamp}
备份目录: {backup_dir}
保留天数: {backup_days} 天

请在 {cleanup_date.strftime('%Y-%m-%d')} 之后执行以下命令清理备份：

# Windows
rmdir /s /q "{backup_dir}"

# Linux/Mac
rm -rf "{backup_dir}"

迁移的数据库：
""")
        for name, path in source_dbs:
            f.write(f"  - {path}\n")
    
    print(f"\n[STEP 6] 清理说明已创建: {cleanup_script}")
    
    # ========== 7. 结果 ==========
    result["success"] = len(result["errors"]) == 0
    
    print(f"\n{'='*60}")
    print(f"迁移完成")
    print(f"{'='*60}")
    print(f"状态: {'成功' if result['success'] else '失败'}")
    print(f"迁移表数: {len(result['tables_migrated'])}")
    print(f"错误数: {len(result['errors'])}")
    print(f"备份位置: {backup_dir}")
    print(f"{'='*60}\n")
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description="知识管理数据库迁移脚本 - 7个数据库合并为1个"
    )
    parser.add_argument(
        "--user-id",
        required=True,
        help="用户ID"
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="数据目录（默认: data）"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="模拟运行（默认: True）"
    )
    parser.add_argument(
        "--no-dry-run",
        action="store_true",
        help="执行实际迁移（禁用 dry-run）"
    )
    parser.add_argument(
        "--backup-days",
        type=int,
        default=30,
        help="备份保留天数（默认: 30）"
    )
    
    args = parser.parse_args()
    
    dry_run = not args.no_dry_run
    
    result = migrate_to_single_db(
        user_id=args.user_id,
        data_dir=args.data_dir,
        dry_run=dry_run,
        backup_days=args.backup_days
    )
    
    # 保存结果
    result_path = os.path.join(
        args.data_dir,
        f"migration_result_{args.user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"迁移结果已保存: {result_path}")
    
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
