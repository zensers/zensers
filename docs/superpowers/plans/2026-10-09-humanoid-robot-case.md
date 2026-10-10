# 人形机器人宣传案例 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline, recommended for this plan — 长时间运行的研究任务，需上下文连续) or superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 zensers 真实研究管线产出《中国人形机器人产业深度研究报告》Word 成品（>40 页、≥12 张真嵌入图表、证据链零缺口），并按 用户审查→修订→通知定稿 流程交付。

**Architecture:** 三段式——①管线小修（搜索配额 env 覆盖 + 图表输出持久化）②定制运行脚本（真 ResearchOrchestrator 12 章研究）+ 渲染脚本（锚点插图→德勤模板→HTMLToWordConverter）③人工审查/修订循环。研究数据 100% 来自真 LLM+真搜索+真技能，禁止任何编造。

**Tech Stack:** Python venv · ResearchOrchestrator（src/core/orchestrator/orchestrator.py）· anysearch 搜索网关 · matplotlib ChartGenerator · python-docx（HTMLToWordConverter）·德勤模板 templates/professional_report.html

**偏离说明:** 本计划不做 git commit（用户未授权提交；README 规定运行产物不入库）。运行类脚本以"执行+验证"代替单元测试。

**Spec:** docs/superpowers/specs/2026-10-09-humanoid-robot-case-design.md

---

## Task 1: 环境连通性预检（只读）

**Files:** Create: `temp/probe_env.py`（临时探针）

- [ ] **Step 1.1: 写探针脚本**

```python
# -*- coding: utf-8 -*-
"""预检: LLM 连通性 + anysearch 搜索连通性（各 1 次真实调用）"""
from dotenv import load_dotenv
load_dotenv()
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def probe_llm():
    from src.config.settings import settings
    from src.core.llm_client import init_llm_infrastructure
    init_llm_infrastructure(settings.llm_profiles)
    from src.core.llm_client import call_llm_sync
    r = call_llm_sync(prompt="回答一个字：好", max_tokens=16)
    print("LLM OK:", bool(r), str(r)[:80])

async def probe_search():
    from src.skills.search_skill import SearchSkill
    s = SearchSkill()
    res = await s.execute(query="中国人形机器人 2026 市场规模", max_results=3)
    items = res.get("results", res) if isinstance(res, dict) else res
    print("SEARCH OK: results=", len(items) if hasattr(items, "__len__") else "?")

if __name__ == "__main__":
    probe_llm()
    asyncio.run(probe_search())
```

（若 `call_llm_sync`/`SearchSkill.execute` 签名与实际不符，以 src/core/llm_client.py 与 src/skills/search_skill.py 的真实签名为准修正探针——只改探针，不改 src。）

- [ ] **Step 1.2: 执行探针**

Run: `venv\Scripts\python.exe -X utf8 temp\probe_env.py`
Expected: 两行 OK（LLM OK: True… / SEARCH OK: results=3）。任一失败 → 停止，修复配置（检查 .env / 网络）后重试。

---

## Task 2: 搜索配额 env 覆盖（代码变更 + 测试）

**Files:**
- Modify: `src/core/research_framework_manager.py:23-27`（imports）、`:43-47`（SearchConfig.__post_init__）
- Test: `tests/unit/test_search_quota_env_override.py`

- [ ] **Step 2.1: 写失败测试**

```python
# -*- coding: utf-8 -*-
"""ZENSERS_MAX_TOTAL_SEARCHES 环境变量覆盖运行时搜索配额上限"""
import importlib


def _make(queries=5, total=100):
    from src.core.research_framework_manager import SearchConfig
    cfg = SearchConfig(max_queries_per_section=queries, max_total_searches=total)
    return cfg


def test_default_ceiling_30(monkeypatch):
    monkeypatch.delenv("ZENSERS_MAX_TOTAL_SEARCHES", raising=False)
    importlib.reload(__import__("src.core.research_framework_manager", fromlist=["SearchConfig"]))
    from src.core.research_framework_manager import SearchConfig
    assert _make(queries=5, total=100).max_total_searches == 30


def test_env_override_raises_ceiling(monkeypatch):
    monkeypatch.setenv("ZENSERS_MAX_TOTAL_SEARCHES", "60")
    importlib.reload(__import__("src.core.research_framework_manager", fromlist=["SearchConfig"]))
    from src.core.research_framework_manager import SearchConfig
    assert _make(queries=5, total=100).max_total_searches == 60


def test_env_below_floor_keeps_min(monkeypatch):
    monkeypatch.setenv("ZENSERS_MAX_TOTAL_SEARCHES", "3")
    importlib.reload(__import__("src.core.research_framework_manager", fromlist=["SearchConfig"]))
    from src.core.research_framework_manager import SearchConfig
    assert _make(queries=5, total=100).max_total_searches >= 5
```

- [ ] **Step 2.2: 验证测试失败**

Run: `venv\Scripts\python.exe -m pytest tests/unit/test_search_quota_env_override.py -v`
Expected: FAIL（环境变量未实现，ceiling 恒为 30）

- [ ] **Step 2.3: 最小实现**

`src/core/research_framework_manager.py` 顶部 imports 增加（若 os 未导入）：

```python
import os
```

`SearchConfig.__post_init__`（现 43-47 行）替换为：

```python
    def __post_init__(self):
        # Framework YAMLs are user-editable and historically contain larger
        # values. Enforce the quota-safe ceiling at the runtime boundary.
        self.max_queries_per_section = min(max(int(self.max_queries_per_section), 3), 5)
        try:
            ceiling = int(os.environ.get("ZENSERS_MAX_TOTAL_SEARCHES", "30"))
        except (TypeError, ValueError):
            ceiling = 30
        ceiling = max(ceiling, self.max_queries_per_section)
        self.max_total_searches = min(max(int(self.max_total_searches), self.max_queries_per_section), ceiling)
```

- [ ] **Step 2.4: 验证测试通过 + 回归**

Run: `venv\Scripts\python.exe -m pytest tests/unit/test_search_quota_env_override.py -v`
Run: `venv\Scripts\python.exe -m pytest tests/unit -q -k "framework or search_quota" --tb=short`
Expected: 全部 PASS

---

## Task 3: 图表输出持久化（两处构造点）

**Files:** Modify: `src/core/orchestrator/orchestrator.py`（模块常量区 + 两处 `ChartGenerator()` 构造）

- [ ] **Step 3.1: 增加模块级常量**

在 orchestrator.py import 区之后（import 与首个类/常量定义之间，选择 imports 结束的空行处）加：

```python
_CHART_OUTPUT_DIR = Path(__file__).resolve().parents[3] / "data" / "html_reports" / "charts"
```

（若文件顶部已有 `from pathlib import Path` 则直接使用；orchestrator.py 已大量使用 Path，直接引用即可。）

- [ ] **Step 3.2: 替换两处构造（1709 与 3233 行，两处代码完全相同）**

oldString（replaceAll，两处相同）：

```python
                    chart_generator=ChartGenerator(),
```

newString：

```python
                    chart_generator=ChartGenerator(output_dir=str(_CHART_OUTPUT_DIR)),
```

- [ ] **Step 3.3: 编译验证**

Run: `venv\Scripts\python.exe -m py_compile src\core\orchestrator\orchestrator.py src\core\research_framework_manager.py`
Expected: 无输出（成功）

- [ ] **Step 3.4: 相关单测回归（report_upgrade 图表相关）**

Run: `venv\Scripts\python.exe -m pytest tests/unit -q -k "chart and (orchestrator or planner)" --tb=short`
Expected: PASS（若存在因 output_dir 断言 temp 路径的用例，改断言而非删用例——预期不存在）

---

## Task 4: 案例运行脚本（真管线入口）

**Files:** Create: `tools/run_humanoid_robot_case.py`

- [ ] **Step 4.1: 完整脚本**

```python
# -*- coding: utf-8 -*-
"""
人形机器人宣传案例：真实完整研究流程
真 ResearchOrchestrator + 真 anysearch 搜索 + 真技能取数。
产出 research_result.json（含证据链）后由 render_humanoid_case_docx.py 出 Word。
"""
from dotenv import load_dotenv
load_dotenv()

import os
os.environ.setdefault("ZENSERS_MAX_TOTAL_SEARCHES", "60")

import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config.settings import settings
from src.core.llm_client import init_llm_infrastructure

init_llm_infrastructure(settings.llm_profiles)

TOPIC = "中国人形机器人产业深度研究报告"
CHAPTERS = [
    "行业概览与研究范围界定",
    "市场规模与增长预测",
    "产业链全景",
    "核心零部件与降本路径",
    "竞争格局",
    "技术发展趋势",
    "应用场景与商业化",
    "政策环境与监管",
    "投融资与资本市场",
    "风险分析",
    "投资建议与策略",
    "结论与展望",
]
OUTPUT_DIR = ROOT / "output" / "cases" / "humanoid_robot"
DOMAIN_KEYWORDS = ["机器人", "人形", "具身", "机器人产业", "整机", "本体"]


def domain_score(content: str) -> float:
    """主题锁定粗检: 领域词密度（每千字命中次数），<1.0 视为疑似漂移"""
    hits = sum(content.count(k) for k in DOMAIN_KEYWORDS)
    return hits / max(1, len(content) / 1000)


async def run_research():
    from src.core.orchestrator.orchestrator import ResearchOrchestrator

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    session_id = f"humanoid_robot_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print("=" * 60)
    print(f"主题: {TOPIC}")
    print(f"章节: {len(CHAPTERS)}")
    print(f"输出: {OUTPUT_DIR}")
    print(f"搜索配额: {os.environ['ZENSERS_MAX_TOTAL_SEARCHES']}")
    print("=" * 60)

    orchestrator = ResearchOrchestrator(use_intelligent_routing=True)
    result = await orchestrator.research(
        user_input={
            "session_id": session_id,
            "topic": TOPIC,
            "aspects": CHAPTERS,
            "output_type": "industry_report",
            "output_format": "html",
        },
        user_id="commercial_demo",
        interaction_mode=False,
        output_type="industry_report",
        custom_aspects=CHAPTERS,
        framework="standard",
        output_format="html",
    )
    if result.status not in ("completed", "completed_with_warnings"):
        print(f"研究失败: {result.status} / {getattr(result, 'summary', '')}")
        return None

    report = result.report
    json_file = OUTPUT_DIR / "research_result.json"
    json_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"结果已保存: {json_file}")

    secs = report.get("sections", [])
    print(f"章节: {len(secs)} | 总字符: {sum(len(s.get('content', '')) for s in secs)}")
    for s in secs:
        print(f"  [{s.get('title', '')[:20]}] {len(s.get('content', ''))}字 "
              f"dp={len(s.get('data_points', []))} charts={len(s.get('charts', []))}")
        if domain_score(s.get("content", "")) < 1.0:
            print(f"    !! 主题疑似漂移: {s.get('title', '')}")
    return json_file


async def main():
    r = await run_research()
    print("\n下一步: python tools/render_humanoid_case_docx.py" if r else "\n运行失败，检查日志")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4.2: 语法验证**

Run: `venv\Scripts\python.exe -m py_compile tools\run_humanoid_robot_case.py`
Expected: 无输出

---

## Task 5: Word 渲染脚本（锚点插图 + 模板 + 转换 + 验收）

**Files:** Create: `tools/render_humanoid_case_docx.py`

- [ ] **Step 5.1: 完整脚本**

```python
# -*- coding: utf-8 -*-
"""
读 research_result.json（真实研究结果）→ Markdown转HTML → 锚点插入真实图表
→ 德勤模板 professional_report.html → HTMLToWordConverter → docx + 页数/证据验收。
图表 PNG 均来自持久目录（data/html_reports/charts），并汇总拷贝到案例目录。
"""
from dotenv import load_dotenv
load_dotenv()

import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CASE_DIR = ROOT / "output" / "cases" / "humanoid_robot"
JSON_FILE = CASE_DIR / "research_result.json"
CHART_COPY_DIR = CASE_DIR / "charts"


def md_to_html(text: str) -> str:
    lines, out, in_table, rows = text.split("\n"), [], False, []

    def flush():
        nonlocal in_table, rows
        if len(rows) < 2:
            for r in rows:
                out.append("<p>" + "|".join(r) + "</p>")
        else:
            header = rows[0]
            n = len(header)
            body = []
            for r in rows[1:]:
                if all(set(c.strip()) <= set("- :") for c in r if c.strip()):
                    continue
                r = (r + [""] * n)[:n]
                body.append("<tr>" + "".join(f"<td>{re.sub(r'\\*\\*(.+?)\\*\\*', r'\\1', c.strip())}</td>" for c in r) + "</tr>")
            out.append("<table><thead><tr>" + "".join(f"<th>{re.sub(r'\\*\\*(.+?)\\*\\*', r'\\1', c.strip())}</th>" for c in header)
                       + "</tr></thead><tbody>" + "".join(body) + "</tbody></table>")
        in_table, rows = False, []

    for line in lines:
        s = line.strip()
        if not s:
            if in_table:
                flush()
            out.append("")
            continue
        if s.startswith("|") and s.endswith("|"):
            in_table = True
            rows.append([c.strip() for c in s.split("|")[1:-1]])
            continue
        if in_table:
            flush()
        if s.startswith("#"):
            lvl = len(s) - len(s.lstrip("#"))
            t = s.lstrip("#").strip()
            if lvl == 1:
                out.append(f'<h2 class="section-title">{t}</h2>')
            elif lvl == 2:
                out.append(f'<h3 class="subsection-title">{t}</h3>')
            elif lvl == 3:
                out.append(f'<h4 class="sub-subsection-title">{t}</h4>')
            else:
                out.append(f"<p>{t}</p>")
            continue
        m_num = re.match(r"^(\d+)[.、]\s*(.+)$", s)
        m_bullet = re.match(r"^[-*]\s+(.+)$", s)
        if m_num:
            out.append("<li>" + m_num.group(2) + "</li>")
            continue
        if m_bullet:
            out.append("<li>" + m_bullet.group(1) + "</li>")
            continue
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"\*(.+?)\*", r"<em>\1</em>", s)
        out.append(f"<p>{s}</p>")
    if in_table:
        flush()
    return "\n".join(out)


def insert_charts(html: str, sections: list) -> tuple:
    """按 insertion_anchor/anchor_type 将真实图表插入章节 HTML，返回 (html, 嵌入数)"""
    count = 0
    for sec in sections:
        h1 = f'<h1 class="chapter-title">{sec.get("order", 0):02d} {sec.get("title", "")}</h1>'
        idx = html.find(h1)
        chunk = html[idx:] if idx >= 0 else html
        end = chunk.find('<h1 class="chapter-title">', len(h1))
        body = chunk if end < 0 else chunk[:end]
        new_body = body
        for ch in sec.get("charts", []):
            src = ch.get("path", "")
            if not src or not Path(src).exists():
                print(f"  !! 图缺失跳过: {ch.get('title', '')}")
                continue
            fig = (f'<figure class="chart-block"><img src="{src}" alt="{ch.get("title", "")}"/>'
                   f'<figcaption><strong>{ch.get("title", "")}</strong>'
                   f'{("：" + ch.get("subtitle", "")) if ch.get("subtitle") else ""} {ch.get("caption", "")}</figcaption></figure>')
            anchor = ch.get("insertion_anchor", "")
            if anchor and anchor in new_body:
                pos = new_body.find("</p>", new_body.find(anchor))
                pos = pos + 4 if pos >= 0 else len(new_body)
            else:
                pos = new_body.find("</p>") + 4
            new_body = new_body[:pos] + fig + new_body[pos:]
            count += 1
        html = html.replace(body, new_body)
    return html, count


def main():
    report = json.loads(JSON_FILE.read_text(encoding="utf-8"))
    sections = report.get("sections", [])
    topic = report.get("topic", report.get("title", ""))
    template = (ROOT / "templates" / "professional_report.html").read_text(encoding="utf-8")

    toc, body, order = [], [], 0
    for i, sec in enumerate(sections, 1):
        sec["order"] = i
        order = i
        toc.append(f'<li class="toc-item"><span class="chapter-num">{i:02d}</span>'
                   f'<span class="chapter-title">{sec.get("title", "")}</span>'
                   f'<span class="chapter-page">{i + 2}</span></li>')
        body.append(f'<h1 class="chapter-title">{i:02d} {sec.get("title", "")}</h1>')
        body.append(f'<div class="section-content">{md_to_html(sec.get("content", ""))}</div>')

    findings = report.get("key_findings", [])
    kf = ""
    if findings:
        kf = '<div class="key-findings"><h2>关键发现</h2><ul>'
        for f in findings:
            kf += "<li>" + re.sub(r"\*\*", "", f) + "</li>"
        kf += "</ul></div>"

    html = template.replace("{{title}}", topic)
    html = html.replace("{{subtitle}}", "行业深度研究报告")
    html = html.replace("{{date}}", datetime.now().strftime("%Y年%m月"))
    html = html.replace("{{report_type}}", "行业深度研究")
    html = html.replace("{{toc_items}}", "\n".join(toc))
    html = html.replace("{{content}}", kf + "\n".join(body))
    html = html.replace("{{page_num}}", "1")

    html, embedded = insert_charts(html, sections)
    (CASE_DIR / "report.html").write_text(html, encoding="utf-8")

    CHART_COPY_DIR.mkdir(parents=True, exist_ok=True)
    for sec in sections:
        for ch in sec.get("charts", []):
            p = Path(ch.get("path", ""))
            if p.exists():
                shutil.copy2(p, CHART_COPY_DIR / p.name)

    from src.converters.html_to_word import HTMLToWordConverter
    conv = HTMLToWordConverter().convert(
        html=html, output_path=str(CASE_DIR / "中国人形机器人产业深度研究报告.docx"))
    if not conv.success:
        print(f"转换失败: {conv.error}")
        sys.exit(1)

    from docx import Document
    doc = Document(str(CASE_DIR / "中国人形机器人产业深度研究报告.docx"))
    import docx.oxml.ns as ns
    chars = sum(len(p.text) for p in doc.paragraphs) + sum(len(c.text) for t in doc.tables for r in t.rows for c in r.cells)
    imgs = len(doc.element.body.findall(".//" + ns.qn("a:blip")))
    pages = max(1, chars // 2000) + imgs // 2

    src_cnt = len(report.get("sources", []))
    no_url = sum(1 for dp in (d for s in sections for d in s.get("data_points", [])) if not dp.get("source_url"))
    print("=" * 60)
    print(f"DOCX: {conv.output_path} ({conv.file_size/1024:.0f} KB, 转换估页 {conv.pages_estimate})")
    print(f"自检: 字符 {chars} | 图表嵌入 {embedded}/{imgs} | 表格 {len(doc.tables)}")
    print(f"自检: 估算页数 {pages} | 数据点缺URL {no_url} | 源 {src_cnt} | 章节数 {len(sections)} | 结论字数 {order}")
    print(f"验收: 页数>40 {'PASS' if pages > 40 else 'FAIL'} | 图>=12 {'PASS' if imgs >= 12 else 'FAIL'} "
          f"| formal_complete={report.get('formal_complete')} | 质量门={report.get('quality_gate_status')}")
    print("=" * 60)


if __name__ == "__main__":
    main()
```

（实现说明：md_to_html 的列表分支以真实 Python 语法为准；写完先 `py_compile`，再以 NEV 的 research_result.json 做一次干跑（输出到临时 case 目录），验证锚点插图/表格转换无误后，再用于本案例。）

- [ ] **Step 5.2: 语法 + NEV 干跑验证（用真实 NEV 数据测渲染器，不改其数据）**

Run: `venv\Scripts\python.exe -m py_compile tools\render_humanoid_case_docx.py`
Run: 临时将 CASE_DIR/JSON_FILE 指向 `output/full_research/research_result.json` 的副本目录（复制 NEV json 到 temp/dry_run/ 并用环境变量或临时改路径），执行脚本。
Expected: 成功生成 docx；`图表嵌入 0/13（NEV 的 PNG 在 Temp 已丢失，属预期）`；`formal_complete=False（NEV 实况，属预期）`。验证点仅是：表格转换出 HTML `<table>`、封面/目录渲染、docx 能打开。干跑产物留在 temp/dry_run/，不进入交付目录。

---

## Task 6: 正式运行（后台 + 轮询）

- [ ] **Step 6.1: 清空配额，后台启动**

```powershell
New-Item -ItemType Directory -Force -Path output\cases\humanoid_robot | Out-Null
Start-Process -FilePath "venv\Scripts\python.exe" -ArgumentList "-X","utf8","tools\run_humanoid_robot_case.py" -WorkingDirectory "E:\market_report_systerm" -RedirectStandardOutput "output\cases\humanoid_robot\run.log" -RedirectStandardError "output\cases\humanoid_robot\run.err.log" -NoNewWindow
```

- [ ] **Step 6.2: 轮询（每 5-10 分钟）**

Run: `Get-Content output\cases\humanoid_robot\run.log -Tail 20; Get-Content output\cases\humanoid_robot\run.err.log -Tail 5`
Expected: 章节推进日志；1-2 小时后出现"结果已保存"。

- [ ] **Step 6.3: 若中断/漂移 → 断点续跑**

orchestrator 具备章节级 checkpoint（checkpoint_dir=output_dir_path）。重跑同一脚本即可从已完成章节恢复；若某章反复失败，将其从 CHAPTERS 中暂摘除单独跑（脚本内临时修改），完成后合并。

---

## Task 7: 自动验收（脚本已内置于 Task 5 输出）

- [ ] **Step 7.1: 核对 Task 5 自检行**

Expected 达标线: 页数>40（估算≥45 更佳）、图表嵌入≥12/13、数据点缺URL=0、章节=12、formal_complete=true（或 completed_with_warnings 且 L3 缺 URL=0）

- [ ] **Step 7.2: 证据链抽验（脚本）**

```python
# -*- coding: utf-8 -*-
"""证据抽验: 随机抽 10 个 data_points 验证 source_url 可达域名可信"""
import json, random
from pathlib import Path
from urllib.parse import urlparse

report = json.loads((Path("output/cases/humanoid_robot/research_result.json")).read_text(encoding="utf-8"))
dps = [dp for s in report["sections"] for dp in s.get("data_points", []) if dp.get("source_url")]
random.seed(42)
print(f"带URL数据点: {len(dps)}/{sum(len(s.get('data_points', [])) for s in report['sections'])}")
for dp in random.sample(dps, min(10, len(dps))):
    dom = urlparse(dp["source_url"]).netloc
    print(f"  [{dp['metric'][:18]}] {dp['value']}{dp['unit']} <- {dom}  ev={dp.get('evidence_id', '')[:12]}")
```

Expected: ≥10 条样本全部有真实域名与 evidence_id；T3 L3 issue=0（`report['defense_audit']['issues']` 中 code=missing_source_url 计数为 0）。

- [ ] **Step 7.3: 框架配置运行时核对**

```python
fc = report.get("_framework_config", {})
print("min_section_length =", fc.get("agent_config", {}).get("content", {}).get("min_section_length"))
print("max_total_searches =", fc.get("agent_config", {}).get("search", {}).get("max_total_searches"))
```

Expected: min_section_length ≥ 5000（industry_report YAML 已内置，是章节字数的真实约束源）；max_total_searches=60���Task 2 的 env 覆盖生效）。
（Spec §3 说明: word_count_target 不是约束链的实扣点——章节字数由 YAML min_section_length=5000 + Writer max_tokens=8192 + 收敛循环共同决定，故不改 agents.yaml。）

---

## Task 8: 人工审查（我执行，产出修订意见清单）

**Files:** Create: `docs/superpowers/specs/2026-10-09-humanoid-robot-review-issues.md`

- [ ] **Step 8.1: 全文通读 docx（分块）**：章节完整性、逻辑连贯、主题一致性、口径声明、占位句、failed 章节
- [ ] **Step 8.2: 数据抽验**：Task 7 样本之外再抽 10 个关键数字，用 sources 的原文 excerpt 与 URL 核对（数值一致±10%、口径/期间匹配、无跨期错配）
- [ ] **Step 8.3: 图表审查**：每图 title/caption/source 与 data_points 对应关系、图型选择合理性
- [ ] **Step 8.4: 排版审查**：封面/目录/页码/表格样式/图注、错字乱码
- [ ] **Step 8.5: 产出结构化修订清单**（编号、位置、严重级 P0/P1/P2、修订方式）

---

## Task 9: 修订执行 + 复验

按清单分类执行（全部走系统机制）：
- 数据缺陷/漂移章 → Task 6.3 断点续跑重写该章（摘除-单跑-合并），自动过 Writer→Reviewer 收敛与 L1-L5 审计
- 证据缺失 → 系统 EvidenceAcquisition/DataRepair 循环自动补；不足处由续跑轮补齐
- 图表问题 → 更正计划在渲染前重跑 `_plan_and_render_charts` 对应章（续跑即触发）或修正渲染脚本映射
- 排版/字号/目录 → 改渲染脚本渲染分支，重新转换 docx

- [ ] **Step 9.1: 执行修订**（按清单逐条）
- [ ] **Step 9.2: 重跑 Task 5 渲染 + Task 7 验收** → 全部 PASS
- [ ] **Step 9.3: 更新修订清单**：每条 issue 标注 resolved

---

## Task 10: 通知用户定稿

- [ ] **Step 10.1: 交付清单**：docx 路径、页数/字数/图表/表格统计、证据链指标（sources/evidence/data_points、L3=0、formal_complete）、修订清单关闭状态
- [ ] **Step 10.2: 等待用户最终确认** → 定稿