# -*- coding: utf-8 -*-
"""固态电池案例盯盘脚本：全量扫描 run.err.log，按严重度分级报告。
用法: venv\\Scripts\\python.exe tools/watch_solid_state_battery.py
退出码: 0=正常/仅告警, 1=进程已死, 2=发现阻塞性错误(Traceback/SSL死锁/进程僵死)"""
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "output" / "cases" / "solid_state_battery" / "run.err.log"

BLOCKING = [
    (r"Traceback \(most recent call last\)", "Python Traceback"),
    (r"SSL.*deadlock|SSLError|shared SSL", "SSL并发问题"),
    (r" クエリ|Thread.*hang|thread.*stuck", "线程挂死"),
    (r"research_result\.json.*truncat|JSON.*truncat", "JSON截断"),
    (r"research failed|研究失败", "研究失败"),
    (r"OutOfMemory|MemoryError|CUDA.*out of memory", "内存溢出"),
]
WARN = [
    (r"Failed to parse", "LLM输出解析失败"),
    (r"patch_data dropped|Skipping failed/empty data patch", "patch丢弃保原文(salvage)"),
    (r"streaming retries exhausted", "streaming耗尽走兼容路径"),
    (r"streaming call failed; retrying", "streaming重试"),
    (r"outdated value after patch", "跨章stale引用"),
    (r"Failed to parse global review", "全局评审丢失"),
    (r"Quality check failed", "质量分未达标放行"),
    (r"Unified retry exhausted", "统一重试耗尽放行"),
    (r"Harness constraint check failed", "harness约束失败"),
    (r"background refresh failed|RemoteDisconnected|Connection aborted", "后台连接抖动"),
]
INFO = [
    (r"GlobalReviewAgent", "进入全局评审"),
    (r"DATE CHECK", "日期质检提示"),
    (r"ChapterWriter", "章节写作活动"),
]


def safe(s: str, n: int = 100) -> str:
    return s[:n].encode("gbk", errors="replace").decode("gbk", errors="replace")


def main() -> int:
    if not LOG.exists():
        print("LOG MISSING: run.err.log 不存在");
        return 1
    lines = LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    mtime = datetime.fromtimestamp(LOG.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"日志行数: {len(lines)} | 最后写入: {mtime} | 现在: {now}")

    exit_code = 0
    print("\n[BLOCKING] 阻塞性错误:")
    found_blocking = False
    for pat, label in BLOCKING:
        hits = [i + 1 for i, l in enumerate(lines) if re.search(pat, l, re.I)]
        if hits:
            found_blocking = True
            print(f"  !! {label}: {len(hits)}次, 行号{hits[:5]}")
    if not found_blocking:
        print("  无")
    else:
        exit_code = 2

    print("\n[WARN] 告警(计数+最后出现行):")
    for pat, label in WARN:
        hits = [i + 1 for i, l in enumerate(lines) if re.search(pat, l)]
        if hits:
            print(f"  -- {label}: {len(hits)}次, 末行#{hits[-1]}: {safe(lines[hits[-1]-1])}")

    print("\n[INFO] 进度信号:")
    for pat, label in INFO:
        hits = [i + 1 for i, l in enumerate(lines) if re.search(pat, l)]
        if hits:
            print(f"  ++ {label}: {len(hits)}次, 末行#{hits[-1]}")

    print("\n[TAIL] 最后5行:")
    for l in lines[-5:]:
        print(f"  {safe(l, 160)}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
