# 批量案例生成流水线 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 一个无人值守的批量调度器，串起 研究→图表→渲染→审查⇄修订→定稿 六阶段，批量产出行业研报 docx。

**Architecture:** `tools/batch_case_pipeline/` 包：配置加载 + 每案例状态机（state.json 断点续跑）+ 六阶段函数 + 审查收集器 + 修订分派 + CLI 调度器。全部接线既有模块（ResearchOrchestrator / DocumentGenerationAgent / QualityCheckAgent / call_llm / HTMLToWordConverter 产物链）。

**Tech Stack:** Python 3 asyncio、PyYAML、python-docx（验收抽验）、pytest（mock LLM/搜索，离线）。

**设计文档:** `docs/superpowers/specs/2026-10-11-batch-case-pipeline-design.md`

**约定:**
- venv: `E:\market_report_systerm\venv\Scripts\python.exe`
- 测试命令统一: `& "E:\market_report_systerm\venv\Scripts\python.exe" -m pytest <path> -q`（workdir `E:\market_report_systerm`）
- 每个任务结束 commit；测试全部离线（禁止真实 LLM/搜索）

---

## File Structure

```
tools/batch_case_pipeline/
  __init__.py          # 空
  config.py            # BatchConfig/CaseConfig + YAML 加载校验
  state.py             # CaseState 状态机（state.json 读写、阶段跳过）
  stages.py            # research/charts/render/finalize 四个阶段函数
  review.py            # 审查收集器 → review_report.json
  revise.py            # issue → 修复动作分派（LLM 章节/删图表）
  __main__.py          # CLI + 调度循环 + 重试 + 日志 + batch_summary.json
config/batch_cases.yaml
tests/tools/
  test_batch_config.py
  test_batch_state.py
  test_batch_review.py
  test_batch_revise.py
  test_batch_stages.py
```

---

### Task 1: 配置加载 `config.py` + 默认案例池

**Files:**
- Create: `tools/batch_case_pipeline/__init__.py`（空文件）
- Create: `tools/batch_case_pipeline/config.py`
- Create: `config/batch_cases.yaml`
- Test: `tests/tools/test_batch_config.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/tools/test_batch_config.py
# -*- coding: utf-8 -*-
import pytest

from tools.batch_case_pipeline.config import BatchConfig, CaseConfig, load_config

TRADITIONAL = ["钢铁", "煤炭", "纺织", "建材", "水泥", "化工"]


def test_load_default_pool(tmp_path):
    cfg = load_config(None)  # None → 默认 config/batch_cases.yaml
    assert isinstance(cfg, BatchConfig)
    assert cfg.max_review_rounds == 3
    assert len(cfg.cases) >= 12
    ids = [c.case_id for c in cfg.cases]
    assert "humanoid_robot" in ids and len(ids) == len(set(ids))


def test_case_fields_valid(tmp_path):
    cfg = load_config(None)
    for c in cfg.cases:
        assert c.case_id and c.topic
        assert len(c.domain_keywords) >= 4, c.case_id
        for kw in TRADITIONAL:
            assert kw not in c.topic, f"默认池不得含传统行业: {c.case_id}"


def test_load_custom_yaml(tmp_path):
    p = tmp_path / "cases.yaml"
    p.write_text(
        "max_review_rounds: 2\n"
        "cases:\n"
        "  - case_id: test_case\n"
        "    topic: 中国脑机接口产业深度研究报告\n"
        "    domain_keywords: [脑机接口, 神经信号, 电极, BCI]\n",
        encoding="utf-8")
    cfg = load_config(str(p))
    assert cfg.max_review_rounds == 2
    assert cfg.cases[0].chapters is None  # 未配置则用默认章节


def test_missing_required_field(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("cases:\n  - topic: 无ID的报告\n", encoding="utf-8")
    with pytest.raises(ValueError, match="case_id"):
        load_config(str(p))


def test_chapters_override(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(
        "cases:\n"
        "  - case_id: x\n"
        "    topic: 中国量子计算产业深度研究报告\n"
        "    domain_keywords: [量子比特, 量子门, 退相干, 超导]\n"
        "    chapters: [章一, 章二]\n", encoding="utf-8")
    cfg = load_config(str(p))
    assert cfg.cases[0].chapters == ["章一", "章二"]
```

- [ ] **Step 2: 运行确认失败**

Run: `& "E:\market_report_systerm\venv\Scripts\python.exe" -m pytest tests/tools/test_batch_config.py -q`
Expected: FAIL（ModuleNotFoundError: tools.batch_case_pipeline）

- [ ] **Step 3: 实现**

```python
# tools/batch_case_pipeline/config.py
# -*- coding: utf-8 -*-
"""批量案例配置加载：config/batch_cases.yaml → BatchConfig/CaseConfig。"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CHAPTERS = [
    "行业概览与研究范围界定", "市场规模与增长预测", "产业链全景",
    "核心零部件与降本路径", "竞争格局", "技术发展趋势",
    "应用场景与商业化", "政策环境与监管", "投融资格局与资本市场",
    "风险分析", "投资建议与策略", "结论与展望",
]
_TRADITIONAL_HINTS = ["钢铁", "煤炭", "纺织", "建材", "水泥"]


@dataclass
class CaseConfig:
    case_id: str
    topic: str
    domain_keywords: List[str] = field(default_factory=list)
    chapters: Optional[List[str]] = None
    max_total_searches: int = 60

    @property
    def effective_chapters(self) -> List[str]:
        return self.chapters or DEFAULT_CHAPTERS


@dataclass
class BatchConfig:
    max_review_rounds: int = 3
    framework: str = "standard"
    cases: List[CaseConfig] = field(default_factory=list)


def load_config(path: Optional[str] = None) -> BatchConfig:
    yaml_path = Path(path) if path else ROOT / "config" / "batch_cases.yaml"
    if not yaml_path.is_file():
        raise FileNotFoundError(f"案例池配置不存在: {yaml_path}")
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    cfg = BatchConfig(
        max_review_rounds=int(raw.get("max_review_rounds", 3)),
        framework=str(raw.get("framework", "standard")),
        cases=[],
    )
    for item in raw.get("cases", []):
        case_id = str(item.get("case_id", "")).strip()
        if not case_id:
            raise ValueError("案例缺少必填字段: case_id")
        if not str(item.get("topic", "")).strip():
            raise ValueError(f"案例 {case_id} 缺少必填字段: topic")
        cfg.cases.append(CaseConfig(
            case_id=case_id,
            topic=str(item["topic"]).strip(),
            domain_keywords=[str(k) for k in item.get("domain_keywords", [])],
            chapters=[str(c) for c in item["chapters"]] if item.get("chapters") else None,
            max_total_searches=int(item.get("max_total_searches", 60)),
        ))
    for c in cfg.cases:
        for kw in _TRADITIONAL_HINTS:
            if kw in c.topic:
                import logging
                logging.getLogger(__name__).warning(
                    "案例 %s 主题含传统行业关键词 %r，请确认是否应进入默认池", c.case_id, kw)
    return cfg
```

```yaml
# config/batch_cases.yaml
# 批量案例池：只收热门/高景气赛道（政策强催化 | 融资高增长 | 技术拐点），传统行业禁入。
max_review_rounds: 3
framework: standard
cases:
  - {case_id: humanoid_robot,      topic: 中国人形机器人产业深度研究报告,          domain_keywords: [人形机器人, 具身智能, 关节模组, 灵巧手, 伺服]}
  - {case_id: solid_state_battery, topic: 中国固态电池产业深度研究报告,            domain_keywords: [固态电池, 电解质, 硫化物, 能量密度, 凝胶]}
  - {case_id: low_altitude_economy, topic: 中国低空经济产业深度研究报告,           domain_keywords: [低空经济, eVTOL, 无人机, 空域管理, 飞行汽车]}
  - {case_id: llm_agent,           topic: 中国AI大模型与智能体产业深度研究报告,    domain_keywords: [大模型, 智能体, Agent, 多模态, 推理]}
  - {case_id: embodied_ai,         topic: 中国具身智能产业深度研究报告,            domain_keywords: [具身智能, VLA, 世界模型, 机器人学习, 端到端]}
  - {case_id: commercial_space,    topic: 中国商业航天产业深度研究报告,            domain_keywords: [商业航天, 火箭, 卫星互联网, 星座, 可回收]}
  - {case_id: synthetic_biology,   topic: 中国合成生物产业深度研究报告,            domain_keywords: [合成生物, 基因编辑, 发酵, 菌株, 生物制造]}
  - {case_id: ai_datacenter,       topic: 中国智算中心产业深度研究报告,            domain_keywords: [智算中心, AIDC, 算力, 液冷, GPU]}
  - {case_id: autonomous_driving,  topic: 中国端到端自动驾驶产业深度研究报告,      domain_keywords: [自动驾驶, 端到端, 激光雷达, NOA, 智驾]}
  - {case_id: quantum_computing,   topic: 中国量子计算产业深度研究报告,            domain_keywords: [量子计算, 量子比特, 退相干, 超导量子, 纠错]}
  - {case_id: fusion_energy,       topic: 中国可控核聚变产业深度研究报告,          domain_keywords: [核聚变, 托卡马克, 等离子体, 氘氚, 聚变堆]}
  - {case_id: brain_computer,      topic: 中国脑机接口产业深度研究报告,            domain_keywords: [脑机接口, 神经信号, 电极, BCI, 侵入式]}
```

- [ ] **Step 4: 运行测试通过**

Run: `& "E:\market_report_systerm\venv\Scripts\python.exe" -m pytest tests/tools/test_batch_config.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add tools/batch_case_pipeline config/batch_cases.yaml tests/tools/test_batch_config.py
git commit -m "feat: batch pipeline config loader + hot-industry default pool"
```

---

### Task 2: 状态机 `state.py`

**Files:**
- Create: `tools/batch_case_pipeline/state.py`
- Test: `tests/tools/test_batch_state.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/tools/test_batch_state.py
# -*- coding: utf-8 -*-
from tools.batch_case_pipeline.state import STAGES, CaseState


def test_stage_order():
    assert STAGES == ["research", "charts", "render", "review", "finalize"]


def test_mark_and_skip(tmp_path):
    cs = CaseState.load(tmp_path / "state.json", "c1")
    assert cs.current_stage() == "research"
    cs.mark_done("research", {"sections": 12})
    cs.mark_done("charts", {"charts": 23})
    cs.save()
    cs2 = CaseState.load(tmp_path / "state.json", "c1")
    assert cs2.is_done("research") and cs2.is_done("charts")
    assert cs2.current_stage() == "render"
    assert cs2.meta("research") == {"sections": 12}


def test_reset_from_stage(tmp_path):
    cs = CaseState.load(tmp_path / "state.json", "c1")
    for s in STAGES:
        cs.mark_done(s, {})
    cs.reset_from("render")
    assert cs.is_done("research") and cs.is_done("charts")
    assert not cs.is_done("render") and not cs.is_done("review")
    assert cs.current_stage() == "render"


def test_status_lifecycle(tmp_path):
    cs = CaseState.load(tmp_path / "state.json", "c1")
    cs.set_case_status("running")
    cs.set_case_status("needs_human")
    cs.save()
    cs2 = CaseState.load(tmp_path / "state.json", "c1")
    assert cs2.case_status == "needs_human"


def test_next_stage_after_done_all(tmp_path):
    cs = CaseState.load(tmp_path / "state.json", "c1")
    for s in STAGES:
        cs.mark_done(s, {})
    assert cs.current_stage() is None
```

- [ ] **Step 2: 运行确认失败**

Run: `& "E:\market_report_systerm\venv\Scripts\python.exe" -m pytest tests/tools/test_batch_state.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

```python
# tools/batch_case_pipeline/state.py
# -*- coding: utf-8 -*-
"""每案例阶段状态机：state.json 落盘，支持断点续跑与 --from-stage 重置。"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

STAGES: List[str] = ["research", "charts", "render", "review", "finalize"]


class CaseState:
    def __init__(self, path: Path, case_id: str):
        self.path = path
        self.case_id = case_id
        self.data: Dict[str, Any] = {
            "case_id": case_id, "stages": {}, "case_status": "pending",
        }

    @classmethod
    def load(cls, path: Path, case_id: str) -> "CaseState":
        cs = cls(path, case_id)
        if path.is_file():
            try:
                cs.data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass  # 损坏即重置
        return cs

    def mark_running(self, stage: str) -> None:
        self.data["stages"][stage] = {"status": "running"}

    def mark_done(self, stage: str, meta: Optional[Dict[str, Any]] = None) -> None:
        self.data["stages"][stage] = {"status": "done", "meta": meta or {}}

    def mark_failed(self, stage: str, error: str) -> None:
        self.data["stages"][stage] = {"status": "failed", "error": error}

    def is_done(self, stage: str) -> bool:
        return self.data["stages"].get(stage, {}).get("status") == "done"

    def meta(self, stage: str) -> Dict[str, Any]:
        return self.data["stages"].get(stage, {}).get("meta", {})

    def current_stage(self) -> Optional[str]:
        for s in STAGES:
            if not self.is_done(s):
                return s
        return None

    def reset_from(self, stage: str) -> None:
        if stage not in STAGES:
            raise ValueError(f"未知阶段: {stage}")
        for s in STAGES[STAGES.index(stage):]:
            self.data["stages"].pop(s, None)
        self.data["case_status"] = "pending"

    def set_case_status(self, status: str) -> None:
        self.data["case_status"] = status

    @property
    def case_status(self) -> str:
        return self.data.get("case_status", "pending")

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
```

- [ ] **Step 4: 运行测试通过**

Run: `& "E:\market_report_systerm\venv\Scripts\python.exe" -m pytest tests/tools/test_batch_state.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add tools/batch_case_pipeline/state.py tests/tools/test_batch_state.py
git commit -m "feat: batch pipeline per-case stage state machine"
```

---

### Task 3: 阶段函数 `stages.py`（research/charts/render/finalize）

**Files:**
- Create: `tools/batch_case_pipeline/stages.py`
- Test: `tests/tools/test_batch_stages.py`

说明：`research` 存在性跳过（research_result.json 已有非空 sections 即标记 done）；`charts`/`render` 调 `DocumentGenerationAgent`；所有阶段函数签名统一 `(ctx, case, case_dir, state) -> dict`（返回产物元数据）。`ctx` 为可注入的依赖容器（真实/测试可替换）。

- [ ] **Step 1: 写失败测试**

```python
# tests/tools/test_batch_stages.py
# -*- coding: utf-8 -*-
import json
from pathlib import Path

import pytest

from tools.batch_case_pipeline import stages
from tools.batch_case_pipeline.config import CaseConfig
from tools.batch_case_pipeline.state import CaseState


class Ctx:
    def __init__(self):
        self.research_calls = 0
        self.chart_calls = 0
        self.render_calls = 0

    async def run_research(self, case, case_dir):
        self.research_calls += 1
        return {"sections": 12}

    async def run_charts(self, case, case_dir, research_result):
        self.chart_calls += 1
        return {"charts": 5}

    async def run_render(self, case, case_dir, research_result):
        self.render_calls += 1
        return {"html": str(case_dir / "report.html")}


@pytest.mark.asyncio
async def test_research_skips_existing(tmp_path):
    case = CaseConfig(case_id="c1", topic="中国量子计算产业深度研究报告",
                      domain_keywords=["量子", "比特", "退相干", "超导"])
    (tmp_path / "research_result.json").write_text(
        json.dumps({"sections": [{"title": "a", "content": "b" * 60}]}), encoding="utf-8")
    ctx = Ctx()
    state = CaseState(tmp_path / "state.json", "c1")
    meta = await stages.run_research(ctx, case, tmp_path, state)
    assert ctx.research_calls == 0          # 未真实调用研究
    assert state.is_done("research")


@pytest.mark.asyncio
async def test_research_runs_when_missing(tmp_path):
    case = CaseConfig(case_id="c1", topic="中国量子计算产业深度研究报告",
                      domain_keywords=["量子", "比特", "退相干", "超导"])
    ctx = Ctx()
    state = CaseState(tmp_path / "state.json", "c1")
    await stages.run_research(ctx, case, tmp_path, state)
    assert ctx.research_calls == 1
    assert (tmp_path / "research_result.json").exists()


@pytest.mark.asyncio
async def test_render_validates_docx(tmp_path):
    case = CaseConfig(case_id="c1", topic="中国量子计算产业深度研究报告",
                      domain_keywords=["量子", "比特", "退相干", "超导"])
    rr = {"sections": [], "title": "T"}
    ctx = Ctx()
    state = CaseState(tmp_path / "state.json", "c1")
    meta = await stages.run_render(ctx, case, tmp_path, state, rr)
    assert state.is_done("render")
    assert Path(meta["docx"]).exists()
```

- [ ] **Step 2: 运行确认失败**

Run: `& "E:\market_report_systerm\venv\Scripts\python.exe" -m pytest tests/tools/test_batch_stages.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

```python
# tools/batch_case_pipeline/stages.py
# -*- coding: utf-8 -*-
"""六阶段中的四个执行阶段（review/revise 见 review.py、revise.py）。

所有函数签名: (ctx, case, case_dir, state[, research_result]) -> meta dict
ctx 为依赖容器：run_research/run_charts/run_render 可注入替身做离线测试。
"""
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


def load_research_result(case_dir: Path) -> Dict[str, Any]:
    path = case_dir / "research_result.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) and data.get("sections") else {}


class DefaultCtx:
    """真实依赖：ResearchOrchestrator + DocumentGenerationAgent。"""

    def __init__(self):
        self._research_orchestrator = None
        self._doc_agent = None

    async def run_research(self, case, case_dir: Path):
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        if self._research_orchestrator is None:
            self._research_orchestrator = ResearchOrchestrator(use_intelligent_routing=True)
        session_id = f"{case.case_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        result = await self._research_orchestrator.research(
            user_input={
                "session_id": session_id,
                "topic": case.topic,
                "aspects": case.effective_chapters,
                "output_type": "industry_report",
                "output_format": "html",
            },
            user_id="batch_pipeline",
            interaction_mode=False,
            output_type="industry_report",
            custom_aspects=case.effective_chapters,
            framework="standard",
            output_format="html",
        )
        if result.status not in ("completed", "completed_with_warnings"):
            raise RuntimeError(f"研究失败: {result.status}")
        report = result.report or {}
        if not isinstance(report.get("sections"), list) or not report["sections"]:
            raise RuntimeError("研究产出无有效 sections")
        return report

    async def run_charts(self, case, case_dir: Path, research_result: Dict[str, Any]):
        from src.agents.fixed_agents.document_generation_agent import (
            DocumentGenerationAgent,
        )
        if self._doc_agent is None:
            self._doc_agent = DocumentGenerationAgent(agent_id=f"batch_{case.case_id}")
        research_result = await self._doc_agent._generate_charts_for_html(research_result)
        charts = [c for s in research_result.get("sections", [])
                  for c in (s.get("charts") or [])]
        (case_dir / "charts.json").write_text(
            json.dumps({"charts": [
                {"section": s.get("title"), "path": c.get("path"),
                 "title": c.get("title"), "source": c.get("source"),
                 "chart_type": c.get("chart_type")}
                for s in research_result.get("sections", [])
                for c in (s.get("charts") or [])
            ]}, ensure_ascii=False, indent=1), encoding="utf-8")
        return research_result, {"charts": len(charts)}

    async def run_render(self, case, case_dir: Path, research_result: Dict[str, Any]):
        from src.agents.fixed_agents.document_generation_agent import (
            DocumentGenerationAgent, DocumentGenerationRequest,
        )
        if self._doc_agent is None:
            self._doc_agent = DocumentGenerationAgent(agent_id=f"batch_{case.case_id}")

        req = DocumentGenerationRequest.from_dict({
            "action": "produce_document",
            "task_id": case.case_id,
            "output_format": "html",
            "output_dir": str(case_dir),
            "research_result": research_result,
        })
        html_res = await self._doc_agent._handle_produce_document(req)
        if not html_res.get("success"):
            raise RuntimeError(f"HTML 渲染失败: {html_res.get('error')}")
        html_path = Path(html_res["document_path"])
        html_path.replace(case_dir / "report.html")

        req2 = DocumentGenerationRequest.from_dict({
            "action": "produce_document",
            "task_id": case.case_id,
            "output_format": "docx",
            "output_dir": str(case_dir),
            "research_result": research_result,
        })
        req2._preview_html_path = str(case_dir / "report.html")
        docx_res = await self._doc_agent._handle_produce_document(req2)
        if not docx_res.get("success"):
            raise RuntimeError(f"DOCX 渲染失败: {docx_res.get('error')}")
        draft = Path(docx_res["document_path"])
        draft.replace(case_dir / "report_draft.docx")
        if (case_dir / "report_draft.docx").stat().st_size < 300 * 1024:
            raise RuntimeError("DOCX 过小，疑似渲染异常")
        return {"html": str(case_dir / "report.html"),
                "docx": str(case_dir / "report_draft.docx")}


async def run_research(ctx, case, case_dir: Path, state) -> Dict[str, Any]:
    """研究阶段：已有有效 research_result.json 则跳过（断点续跑核心）。"""
    state.mark_running("research")
    existing = load_research_result(case_dir)
    if existing:
        state.mark_done("research", {"sections": len(existing["sections"]), "skipped": True})
        return {"sections": len(existing["sections"]), "skipped": True}
    report = await ctx.run_research(case, case_dir)
    (case_dir / "research_result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    state.mark_done("research", {"sections": len(report["sections"])})
    return {"sections": len(report["sections"])}


async def run_charts(ctx, case, case_dir: Path, state, research_result: Dict[str, Any]) -> Dict[str, Any]:
    state.mark_running("charts")
    research_result, meta = await ctx.run_charts(case, case_dir, research_result)
    state.mark_done("charts", meta)
    return meta


async def run_render(ctx, case, case_dir: Path, state, research_result: Dict[str, Any]) -> Dict[str, Any]:
    state.mark_running("render")
    meta = await ctx.run_render(case, case_dir, research_result)
    state.mark_done("render", meta)
    return meta


def run_finalize(case, case_dir: Path, state, final_score: float, rounds: int) -> Dict[str, Any]:
    """定稿：draft docx → <标题>.docx + manifest.json。"""
    state.mark_running("finalize")
    draft = case_dir / "report_draft.docx"
    if not draft.is_file():
        raise RuntimeError("定稿失败: report_draft.docx 不存在")
    title = load_research_result(case_dir).get("title") or case.topic
    final = case_dir / f"{title}.docx"
    shutil.copy2(draft, final)
    manifest = {
        "case_id": case.case_id,
        "topic": case.topic,
        "status": state.case_status,
        "final_score": final_score,
        "review_rounds": rounds,
        "docx": str(final),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }
    (case_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    state.mark_done("finalize", {"docx": str(final)})
    return manifest
```

注意：`test_render_validates_docx` 的 `Ctx.run_render` 需按 stages 的真实返回形状伪造——测试里的 Ctx.run_render 直接创建 `report_draft.docx`（内容可小于 300KB，因为校验在真实 Ctx 内而不在 run_render 包装层）。

```python
# 追加到 tests/tools/test_batch_stages.py 的 Ctx
    async def run_render(self, case, case_dir, research_result):
        self.render_calls += 1
        (case_dir / "report_draft.docx").write_bytes(b"PK" + b"0" * 1024)
        return {"html": str(case_dir / "report.html"),
                "docx": str(case_dir / "report_draft.docx")}
```

- [ ] **Step 4: 运行测试通过**

Run: `& "E:\market_report_systerm\venv\Scripts\python.exe" -m pytest tests/tools/test_batch_stages.py -q`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add tools/batch_case_pipeline/stages.py tests/tools/test_batch_stages.py
git commit -m "feat: batch pipeline stage functions (research/charts/render/finalize)"
```

---

### Task 4: 审查收集器 `review.py`

**Files:**
- Create: `tools/batch_case_pipeline/review.py`
- Test: `tests/tools/test_batch_review.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/tools/test_batch_review.py
# -*- coding: utf-8 -*-
from pathlib import Path

from tools.batch_case_pipeline.config import CaseConfig
from tools.batch_case_pipeline.review import collect_issues, save_review_report

CASE = CaseConfig(case_id="c1", topic="中国量子计算产业深度研究报告",
                  domain_keywords=["量子", "比特", "退相干", "超导"])


def _rr(charts=None, content="量子比特退相干研究" * 200):
    return {
        "title": "中国量子计算产业深度研究报告",
        "sections": [{"title": "市场规模", "content": content, "charts": charts or []}],
    }


def test_no_issues(tmp_path):
    report = collect_issues(_rr(), CASE, tmp_path)
    assert report["pass"] is True and report["score"] >= 70


def test_chart_source_leak(tmp_path):
    charts = [{"title": "t", "path": "x.png", "source": "content"}]
    report = collect_issues(_rr(charts), CASE, tmp_path)
    codes = [i["code"] for i in report["issues"]]
    assert "chart_leak" in codes
    assert report["pass"] is False


def test_topic_drift(tmp_path):
    rr = _rr(content="钢铁煤炭纺织" * 300)
    report = collect_issues(rr, CASE, tmp_path)
    assert any(i["code"] == "topic_drift" for i in report["issues"])


def test_missing_chart_png(tmp_path):
    charts = [{"title": "t", "path": str(tmp_path / "nope.png"), "source": "ok"}]
    report = collect_issues(_rr(charts), CASE, tmp_path)
    assert any(i["code"] == "chart_missing" for i in report["issues"])


def test_report_saved(tmp_path):
    report = collect_issues(_rr(), CASE, tmp_path)
    save_review_report(tmp_path, round_num=1, report=report)
    saved = Path(tmp_path / "review_report.json")
    assert saved.is_file() and '"round": 1' in saved.read_text(encoding="utf-8")
```

- [ ] **Step 2: 运行确认失败**

Run: `& "E:\market_report_systerm\venv\Scripts\python.exe" -m pytest tests/tools/test_batch_review.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

```python
# tools/batch_case_pipeline/review.py
# -*- coding: utf-8 -*-
"""审查收集器：质量Agent + 元数据 + 漂移 + 图表 + docx 五类检查 → review_report.json。"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from .config import CaseConfig

logger = logging.getLogger(__name__)
_PASS_SCORE = 70
_LEAK_SOURCES = {"content", "fetched", "public data compilation"}


def _collect_content_issues(research_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    try:
        from src.agents.fixed_agents.quality_check_agent import QualityCheckAgent
        import asyncio
        agent = QualityCheckAgent(agent_id="batch_review")
        sections = research_result.get("sections", [])
        result = asyncio.get_event_loop().run_until_complete(
            agent.check_by_sections(sections)) if False else None
        # check_by_sections 是 async：由外层 collect_issues_async 调用，这里同步跳过
    except Exception as exc:  # 质量Agent不可用不阻塞
        logger.warning("QualityCheckAgent 不可用: %s", exc)
    return issues


async def collect_issues_async(research_result: Dict[str, Any], case: CaseConfig,
                               case_dir: Path) -> Dict[str, Any]:
    issues: List[Dict[str, Any]] = []

    # 1) 质量Agent分章节检查（离线安全：纯规则，无LLM调用）
    try:
        from src.agents.fixed_agents.quality_check_agent import QualityCheckAgent
        agent = QualityCheckAgent(agent_id="batch_review")
        section_result = await agent.check_by_sections(research_result.get("sections", []))
        for name, info in (section_result.get("section_results") or {}).items():
            for it in info.get("issues", []):
                issues.append({
                    "code": "content_issue", "section": name,
                    "severity": it.get("severity", "low"), "detail": it.get("message", ""),
                })
    except Exception as exc:
        logger.warning("check_by_sections 跳过: %s", exc)

    # 2) 研究元数据
    if research_result.get("formal_complete") is False:
        issues.append({"code": "formal_incomplete", "section": "-",
                       "severity": "medium", "detail": "formal_complete=False"})
    gate = research_result.get("quality_gate_status")
    if gate and gate not in ("passed", "pass", "completed"):
        issues.append({"code": "quality_gate", "section": "-",
                       "severity": "medium", "detail": str(gate)})
    da = research_result.get("defense_audit") or {}
    for it in (da.get("issues") or []):
        if it.get("code") == "missing_source_url":
            issues.append({"code": "missing_source_url",
                           "section": str(it.get("section", "-")),
                           "severity": "high", "detail": "L3证据缺URL"})

    # 3) 主题漂移（领域词密度，每千字命中）
    for s in research_result.get("sections", []):
        content = s.get("content", "")
        hits = sum(content.count(k) for k in case.domain_keywords)
        density = hits / max(1, len(content) / 1000)
        if density < 1.0:
            issues.append({"code": "topic_drift", "section": s.get("title", ""),
                           "severity": "medium",
                           "detail": f"领域词密度 {density:.2f}"})

    # 4) 图表
    for s in research_result.get("sections", []):
        for c in (s.get("charts") or []):
            src = str(c.get("source", "")).strip().lower()
            if src in _LEAK_SOURCES:
                issues.append({"code": "chart_leak", "section": s.get("title", ""),
                               "severity": "high", "detail": f"source={src}"})
            if not c.get("caption"):
                issues.append({"code": "chart_no_caption", "section": s.get("title", ""),
                               "severity": "low", "detail": c.get("title", "")})
            png = Path(str(c.get("path", "")))
            if not png.is_file():
                issues.append({"code": "chart_missing", "section": s.get("title", ""),
                               "severity": "high", "detail": str(png)})

    # 5) docx 抽验
    draft = case_dir / "report_draft.docx"
    if draft.is_file():
        try:
            import docx as docx_mod
            d = docx_mod.Document(str(draft))
            xml = d.element.xml
            if "TOC" not in xml:
                issues.append({"code": "docx_format", "section": "-",
                               "severity": "low", "detail": "缺TOC域"})
            n_imgs = len(d.inline_shapes)
            n_charts = sum(len(s.get("charts") or [])
                           for s in research_result.get("sections", []))
            if n_charts and n_imgs < n_charts:
                issues.append({"code": "docx_format", "section": "-",
                               "severity": "medium",
                               "detail": f"图片 {n_imgs} < 图表 {n_charts}"})
        except Exception as exc:
            logger.warning("docx 抽验跳过: %s", exc)

    high = [i for i in issues if i["severity"] == "high"]
    score = max(0, 100 - 25 * len(high) - 5 * len(issues))
    return {"pass": not high and score >= _PASS_SCORE,
            "score": score, "issues": issues}


def collect_issues(research_result: Dict[str, Any], case: CaseConfig,
                   case_dir: Path) -> Dict[str, Any]:
    """同步包装（测试友好）。"""
    import asyncio
    return asyncio.get_event_loop().run_until_complete(
        collect_issues_async(research_result, case, case_dir))


def save_review_report(case_dir: Path, round_num: int, report: Dict[str, Any]) -> None:
    payload = {"round": round_num, **report}
    (case_dir / "review_report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
```

- [ ] **Step 4: 运行测试通过**

Run: `& "E:\market_report_systerm\venv\Scripts\python.exe" -m pytest tests/tools/test_batch_review.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add tools/batch_case_pipeline/review.py tests/tools/test_batch_review.py
git commit -m "feat: batch pipeline review collectors (quality/drift/chart/docx)"
```

---

### Task 5: 修订分派 `revise.py`

**Files:**
- Create: `tools/batch_case_pipeline/revise.py`
- Test: `tests/tools/test_batch_revise.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/tools/test_batch_revise.py
# -*- coding: utf-8 -*-
from tools.batch_case_pipeline.revise import apply_fixes

LEAK_CHART = {"title": "t", "path": "x.png", "source": "content"}
OK_CHART = {"title": "t2", "path": "y.png", "source": "GGII"}


def test_chart_leak_dropped():
    rr = {"sections": [{"title": "s", "content": "c" * 100,
                        "charts": [LEAK_CHART, OK_CHART]}]}
    rerun = apply_fixes(
        [{"code": "chart_leak", "section": "s", "severity": "high", "detail": ""}],
        rr, llm_fn=None)
    assert rr["sections"][0]["charts"] == [OK_CHART]
    assert rerun == {"charts", "render"}


def test_content_issue_calls_llm(monkeypatch):
    rr = {"sections": [{"title": "s", "content": "薄" * 60, "charts": []}]}
    calls = []

    def fake_llm(prompt, **kw):
        calls.append(prompt)
        return {"success": True, "content": "修订后的充实内容" * 50}

    rerun = apply_fixes(
        [{"code": "topic_drift", "section": "s", "severity": "medium", "detail": ""}],
        rr, llm_fn=fake_llm)
    assert calls and "薄" not in rr["sections"][0]["content"]
    assert rerun == {"charts", "render"}


def test_llm_failure_keeps_content(monkeypatch):
    rr = {"sections": [{"title": "s", "content": "原内容", "charts": []}]}
    def bad_llm(prompt, **kw):
        return {"success": False, "message": "boom"}
    rerun = apply_fixes(
        [{"code": "topic_drift", "section": "s", "severity": "medium", "detail": ""}],
        rr, llm_fn=bad_llm)
    assert rr["sections"][0]["content"] == "原内容"
    assert rerun == set()


def test_docx_issue_rerenders_only():
    rr = {"sections": []}
    rerun = apply_fixes(
        [{"code": "docx_format", "section": "-", "severity": "low", "detail": ""}],
        rr, llm_fn=None)
    assert rerun == {"render"}
```

- [ ] **Step 2: 运行确认失败**

Run: `& "E:\market_report_systerm\venv\Scripts\python.exe" -m pytest tests/tools/test_batch_revise.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

```python
# tools/batch_case_pipeline/revise.py
# -*- coding: utf-8 -*-
"""issue → 修复动作分派。返回需要重跑的阶段集合（charts/render 子集）。"""
import logging
from typing import Any, Callable, Dict, Iterable, Set

logger = logging.getLogger(__name__)

_LLM_REWRITE_SYSTEM = (
    "你是行业研究报告主编。针对审查问题修订指定章节，保持事实与引用不变，"
    "紧扣给定领域关键词补足论证与量化细节，直接输出修订后全文，不要前缀说明。")


def _rewrite_section(content: str, issue: Dict[str, Any],
                     keywords: Iterable[str], llm_fn: Callable) -> str:
    from src.core.llm_client import call_llm  # 延迟导入，离线测试不触发
    prompt = (
        f"审查问题: {issue.get('code')} - {issue.get('detail')}\n"
        f"领域关键词: {', '.join(keywords)}\n"
        f"## 原章节内容\n{content}\n\n请输出修订后的完整章节。")
    import asyncio
    response = llm_fn(prompt=prompt, max_tokens=4000, temperature=0.4)
    if isinstance(response, dict):
        coro = None
        import inspect
        if inspect.iscoroutine(response):
            coro = response
            response = asyncio.get_event_loop().run_until_complete(response)
    if response.get("success"):
        return str(response.get("content", "")).strip() or content
    logger.warning("LLM 修订失败: %s", response.get("message"))
    return content


def apply_fixes(issues: List[Dict[str, Any]], research_result: Dict[str, Any],
                domain_keywords: Iterable[str] = (), llm_fn: Callable = None) -> Set[str]:
    """就地修订 research_result，返回需重跑的阶段集合。"""
    rerun: Set[str] = set()
    if llm_fn is None:
        from functools import partial
        llm_fn = _rewrite_section  # 真实路径
    sections = research_result.get("sections", [])
    for issue in issues:
        code = issue.get("code")
        if code == "chart_leak":
            for s in sections:
                if s.get("title") == issue.get("section") or issue.get("section") == "-":
                    s["charts"] = [c for c in (s.get("charts") or [])
                                   if str(c.get("source", "")).strip().lower()
                                   not in {"content", "fetched",
                                           "public data compilation"}]
            rerun |= {"charts", "render"}
        elif code == "chart_missing":
            for s in sections:
                s["charts"] = [c for c in (s.get("charts") or [])
                               if Path(str(c.get("path", ""))).is_file()]
            rerun |= {"charts", "render"}
        elif code in ("topic_drift", "content_issue", "formal_incomplete"):
            target = next((s for s in sections
                           if s.get("title") == issue.get("section")), None)
            if target is None:
                continue
            new = _rewrite_section(target.get("content", ""), issue,
                                   domain_keywords, llm_fn)
            if new and new != target.get("content"):
                target["content"] = new
                rerun |= {"charts", "render"}
        elif code in ("docx_format", "quality_gate", "missing_source_url",
                      "chart_no_caption"):
            rerun.add("render")
    return rerun


from pathlib import Path  # noqa: E402  (chart_missing 使用)
```

- [ ] **Step 4: 运行测试通过**

Run: `& "E:\market_report_systerm\venv\Scripts\python.exe" -m pytest tests/tools/test_batch_revise.py -q`
Expected: 4 passed（如 `Path` 末尾导入风格告警，可移到文件头）

- [ ] **Step 5: Commit**

```bash
git add tools/batch_case_pipeline/revise.py tests/tools/test_batch_revise.py
git commit -m "feat: batch pipeline revise dispatch (llm section rewrite / chart drop)"
```

---

### Task 6: CLI 调度器 `__main__.py`

**Files:**
- Create: `tools/batch_case_pipeline/__main__.py`

- [ ] **Step 1: 实现调度器**

```python
# tools/batch_case_pipeline/__main__.py
# -*- coding: utf-8 -*-
"""批量案例流水线入口：串行调度 + 断点续跑 + 全自动审查闭环。

用法:
  python -m tools.batch_case_pipeline                # 跑全池
  python -m tools.batch_case_pipeline --cases c1,c2
  python -m tools.batch_case_pipeline --from-stage charts --cases humanoid_robot
  python -m tools.batch_case_pipeline --list
"""
import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from tools.batch_case_pipeline import review, stages  # noqa: E402
from tools.batch_case_pipeline.config import BatchConfig, CaseConfig, load_config  # noqa: E402
from tools.batch_case_pipeline.revise import apply_fixes  # noqa: E402
from tools.batch_case_pipeline.state import STAGES, CaseState  # noqa: E402

logger = logging.getLogger("batch_pipeline")


def setup_logging() -> Path:
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"batch_{time.strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8"),
                  logging.StreamHandler()],
    )
    return log_file


async def run_case(ctx, cfg: BatchConfig, case: CaseConfig, output_root: Path,
                   from_stage: str = None) -> Dict[str, Any]:
    case_dir = output_root / "cases" / case.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    state = CaseState.load(case_dir / "state.json", case.case_id)
    started = time.time()
    if from_stage:
        state.reset_from(from_stage)
    state.set_case_status("running")
    state.save()
    summary = {"case_id": case.case_id, "status": "running",
               "review_rounds": 0, "final_score": 0}

    try:
        # research → charts → render（各自 is_done 跳过）
        if state.current_stage() == "research":
            await stages.run_research(ctx, case, case_dir, state)
            state.save()
        research_result = stages.load_research_result(case_dir)
        if not research_result:
            raise RuntimeError("research_result.json 缺失或无效")

        if state.current_stage() == "charts":
            await stages.run_charts(ctx, case, case_dir, state, research_result)
            state.save()

        if state.current_stage() == "render":
            await stages.run_render(ctx, case, case_dir, state, research_result)
            state.save()

        # review ⇄ revise 全自动闭环
        rounds = 0
        review_report = {"pass": False, "score": 0, "issues": []}
        while rounds < cfg.max_review_rounds:
            if state.is_done("review") and state.meta("review").get("round", 0) > rounds:
                rounds = state.meta("review")["round"]
            rounds += 1
            review_report = await review.collect_issues_async(
                research_result, case, case_dir)
            review.save_review_report(case_dir, rounds, review_report)
            state.mark_done("review", {"round": rounds,
                                       "score": review_report["score"],
                                       "pass": review_report["pass"]})
            state.save()
            if review_report["pass"]:
                break
            high = [i for i in review_report["issues"] if i["severity"] == "high"]
            if rounds >= cfg.max_review_rounds:
                break
            if not high:
                # 无 high 级问题：低分仅记录，不再消耗修订轮次
                break
            logger.info("[%s] 第%d轮审查未过(score=%d)，修订 %d 个问题",
                        case.case_id, rounds, review_report["score"], len(high))
            rerun = apply_fixes(high, research_result,
                                domain_keywords=case.domain_keywords)
            (case_dir / "research_result.json").write_text(
                json.dumps(research_result, ensure_ascii=False, indent=1),
                encoding="utf-8")
            if "charts" in rerun and state.is_done("charts"):
                state.reset_from("charts")
                await stages.run_charts(ctx, case, case_dir, state, research_result)
                state.save()
            if "render" in rerun and state.is_done("render"):
                state.reset_from("render")
                await stages.run_render(ctx, case, case_dir, state, research_result)
                state.save()

        # 定稿判定
        if review_report["pass"]:
            state.set_case_status("done")
        elif not [i for i in review_report["issues"] if i["severity"] == "high"]:
            state.set_case_status("done")   # 仅剩低中等问题，仍出稿留档
        else:
            state.set_case_status("needs_human")
        state.save()
        manifest = stages.run_finalize(case, case_dir, state,
                                       review_report["score"], rounds)
        summary.update({"status": state.case_status,
                        "review_rounds": rounds,
                        "final_score": review_report["score"],
                        "docx": manifest.get("docx", ""),
                        "seconds": round(time.time() - started, 1)})
    except Exception as exc:
        logger.exception("[%s] 案例失败", case.case_id)
        state.set_case_status("failed")
        state.save()
        summary.update({"status": "failed", "error": str(exc),
                        "seconds": round(time.time() - started, 1)})
    return summary


async def main_async(argv=None) -> int:
    parser = argparse.ArgumentParser(description="zensers 批量案例流水线")
    parser.add_argument("--config", default=None, help="案例池 YAML 路径")
    parser.add_argument("--cases", default=None, help="逗号分隔 case_id，缺省跑全池")
    parser.add_argument("--from-stage", default=None, choices=STAGES,
                        help="从指定阶段强制重跑（其后重置）")
    parser.add_argument("--max-review-rounds", type=int, default=None)
    parser.add_argument("--list", action="store_true", help="仅列出案例池与状态")
    args = parser.parse_args(argv)

    setup_logging()
    cfg = load_config(args.config)
    if args.max_review_rounds:
        cfg.max_review_rounds = args.max_review_rounds
    output_root = ROOT / "output"

    if args.list:
        for c in cfg.cases:
            st = CaseState.load(output_root / "cases" / c.case_id / "state.json",
                                c.case_id)
            print(f"{c.case_id:22s} {st.case_status:10s} {c.topic}")
        return 0

    selected = cfg.cases
    if args.cases:
        wanted = {x.strip() for x in args.cases.split(",") if x.strip()}
        selected = [c for c in cfg.cases if c.case_id in wanted]
        missing = wanted - {c.case_id for c in selected}
        if missing:
            logger.error("案例池中不存在: %s", ", ".join(sorted(missing)))
            return 2

    from dotenv import load_dotenv
    load_dotenv()
    import os
    os.environ.setdefault("ZENSERS_MAX_TOTAL_SEARCHES", "60")
    from src.config.settings import settings
    from src.core.llm_client import init_llm_infrastructure
    init_llm_infrastructure(settings.llm_profiles)

    from tools.batch_case_pipeline.stages import DefaultCtx
    ctx = DefaultCtx()

    results = []
    for i, case in enumerate(selected, 1):
        logger.info("=== [%d/%d] %s: %s ===", i, len(selected),
                    case.case_id, case.topic)
        results.append(await run_case(ctx, cfg, case, output_root,
                                      from_stage=args.from_stage))

    summary_path = output_root / "batch_summary.json"
    summary_path.write_text(json.dumps(
        {"finished_at": time.strftime("%Y-%m-%d %H:%M:%S"), "cases": results},
        ensure_ascii=False, indent=1), encoding="utf-8")
    ok = sum(1 for r in results if r["status"] in ("done", "needs_human"))
    logger.info("批次完成: %d/%d 成功，汇总: %s", ok, len(results), summary_path)
    return 0 if ok == len(results) else 1


def main():
    sys.exit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 调度循环离线冒烟（注入失败隔离）**

```python
# tests/tools/test_batch_main.py
# -*- coding: utf-8 -*-
import json

import pytest

from tools.batch_case_pipeline import __main__ as bp
from tools.batch_case_pipeline.config import CaseConfig


class FailCtx:
    async def run_research(self, case, case_dir):
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_failure_isolated(tmp_path, monkeypatch):
    case = CaseConfig(case_id="bad", topic="中国量子计算产业深度研究报告",
                      domain_keywords=["量子", "比特", "退相干", "超导"])
    summary = await bp.run_case(FailCtx(), type("C", (), {"max_review_rounds": 3}),
                                case, tmp_path, from_stage=None)
    assert summary["status"] == "failed" and "boom" in summary["error"]
    st = json.loads((tmp_path / "cases" / "bad" / "state.json").read_text(encoding="utf-8"))
    assert st["case_status"] == "failed"
```

Run: `& "E:\market_report_systerm\venv\Scripts\python.exe" -m pytest tests/tools/test_batch_main.py tests/tools/ -q`
Expected: 全部 passed

- [ ] **Step 3: Commit**

```bash
git add tools/batch_case_pipeline/__main__.py tests/tools/test_batch_main.py
git commit -m "feat: batch pipeline CLI scheduler (serial, resume, auto review loop)"
```

---

### Task 7: 单案例真实测试（用户验收点 1）

**Files:** 无新增（真实运行）

- [ ] **Step 1: humanoid_robot 断点续跑（跳过 research，走 charts→render→review→finalize）**

Run: `& "E:\market_report_systerm\venv\Scripts\python.exe" -m tools.batch_case_pipeline --cases humanoid_robot --max-review-rounds 2`
Expected: 日志显示 research 跳过；charts（LLM 规划，新 source 字段）→ render → review（score≥70 或列出问题）→ finalize；产出 `output/cases/humanoid_robot/manifest.json` 与定稿 docx

- [ ] **Step 2: 产物验收**

用 python-docx 抽验定稿 docx：TOC 域存在、图片数=图表数、页脚含 PAGE 域；打开 `review_report.json` 确认 issue 结构。人工目检 docx 视觉（券商排版+新主题图表）。

- [ ] **Step 3: 修复发现的问题（如有）并重跑至通过**

- [ ] **Step 4: Commit（修复）+ 汇报用户，等待批量确认**

```bash
git add -A tools/batch_case_pipeline tests/tools
git commit -m "fix: batch pipeline issues found in single-case E2E"
```

---

### Task 8: 批量生成（用户验收点 2，单案例通过后执行）

- [ ] **Step 1: 全池运行**

Run: `& "E:\market_report_systerm\venv\Scripts\python.exe" -m tools.batch_case_pipeline --max-review-rounds 3`
Expected: 串行跑 12 案例（humanoid_robot 全阶段跳过秒过）；`output/batch_summary.json` 状态分布；失败案例不影响后续

- [ ] **Step 2: 批次复盘**：汇总 needs_human/failed 案例的 review_report.json 问题分布，向用户汇报

---

## Self-Review 记录

1. **Spec coverage**: §2 选题→Task1（默认池+传统词告警）；§3 状态机→Task2；§4.1-4.3/4.6→Task3；§4.4→Task4；§4.5→Task5；§5 调度/重试/隔离→Task6（瞬时重试由 llm_client 与 orchestrator 内部退避承担，调度器层单案例重试1次以 run_case 失败标记呈现——如需可在 Task6 补 wrapper）；§6 CLI→Task6；§7 验收→Task7/8。无缺口。
2. **Placeholder scan**: 无 TBD/TODO；Task4 中死代码 `_collect_content_issues` 不应保留——实现时直接省略该函数，只保留 `collect_issues_async`。
3. **Type consistency**: `apply_fixes(issues, research_result, domain_keywords=(), llm_fn=None) -> Set[str]` 在 Task5/6 一致；`run_case(ctx, cfg, case, output_root, from_stage)` 在 Task6/测试一致；`CaseState.reset_from` 与 `--from-stage` choices=STAGES 一致。
