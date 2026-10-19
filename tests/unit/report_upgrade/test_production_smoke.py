# -*- coding: utf-8 -*-
"""离线全链路冒烟：报告生成主干（write -> rescue cache -> defense rescue -> assemble）。

场景（call_llm_ex 在 chapter_writer 模块接缝处被脚本化 fake 替换，零网络）：
- 章节 A：正常章节 JSON 一次就绪（引擎对该章节只发一次传输调用）。
- 章节 B：先收到退化拒答（真实 writer 分类钩子 `_parse_with_outcome` 判为
  degenerate），第二次调用带标记格式强化（strict_json rung 的 delimiter
  契约 reinforce）+ temperature=0.1 变异后成功
  —— 引擎升级变异真实发生，不是回放。
- 章节 C：call_llm_ex 抛 LLMBudgetExhausted（预算耗尽契约）-> failed 章节
  -> rescue cache 缓存写入素材 -> Defense 轮顶部 rescue 重写交付。
- 最终三章节全部 ready，exec summary 刷新不崩溃，审计通过。

fake 不是固定回放：它驱动真实 RetryEngine + 真实 Budget.scale_to + 真实
writer 解析钩子，只有 transport 输出按脚本执行。注意：真实钩子对
"短 JSON 拒答"的分类是按 raw 长度（<30 字符 -> degenerate）；更长的
JSON 形态拒答会落进 truncated 阶梯（max_tokens 变异而非 temperature）。
"""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.fixed_agents.report_upgrade import chapter_writer as chapter_writer_module
from src.agents.fixed_agents.report_upgrade.chapter_writer import ChapterWriter
from src.agents.fixed_agents.report_upgrade.models import ChapterWriteOutput, ReviewOutput
from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager
from src.core.llm_retry import (
    Budget, CandidateDesc, Classification, LLMBudgetExhausted, LLMErrorClass,
    RetryEngine, STRICT_JSON_PREFIX,
)

_CANDIDATE = CandidateDesc(
    name="mimo", model="mimo-v2.6-flash", fallback_model="mimo-v2.5",
    max_context_tokens=131072,
)

# 章节 B 第一次调用的拒答形态：合法 JSON 信封 + 退化短拒答，raw 长度 < 30
# -> 真实 writer 钩子分类 degenerate -> DEGENERATE 阶梯第 0 rung =
# strict_json（delimiter 契约下由 prompt builder 追加标记格式强化）+ temp 0.1。
_DEGENERATE_REFUSAL = '{"content":"嗯"}'

TEXT_A = (
    "## 市场规模现状\n"
    "本章基于公开研究资料与结构化访谈素材，梳理目标市场的整体规模与增长态势。"
    "从需求侧看，下游客户对专业化服务的采购意愿持续增强，头部机构的年度预算投入保持稳定扩张，"
    "中小机构的采购行为则更加谨慎，预算持续向可验证的交付成果集中。"
    "从供给侧看，服务能力与交付质量成为竞争的主要分水岭，具备方法论沉淀与数据资产积累的服务商"
    "获得明显更高的续约率与复购意愿。综合判断，市场整体处于结构升级阶段，规模扩张与质量提升并行推进，"
    "细分赛道之间的增速差异显著，专业化程度越高的细分市场抗波动能力越强。"
    "从区域结构看，核心城市群的采购活跃度领先，区域下沉市场仍处于认知培育阶段，"
    "渠道教育与标杆案例的示范效应是打开区域市场的关键抓手，交付周期与验收标准逐步透明化，"
    "客户决策链条明显前移，专业咨询与第三方评估在采购决策中的话语权稳步上升。"
    "综合来看，规模扩张的可持续性取决于服务能力的兑现速度与交付口碑的积累效率。"
)

TEXT_B = (
    "## 竞争格局分析\n"
    "本章从市场份额、能力梯队与生态位三个维度刻画当前竞争格局。头部服务商凭借方法论沉淀、"
    "数据资产与交付网络的规模优势，持续巩固领先位置；腰部机构则在垂直行业深耕，"
    "以行业理解与定制能力换取差异化生存空间；长尾参与者的同质化竞争加剧，出清速度明显加快。"
    "能力梯队之间的流动依然存在，关键变量在于数据资产积累速度与方法论迭代周期。"
    "生态层面，平台型玩家通过开放接口与伙伴计划扩张边界，专业服务商与平台的竞合关系"
    "成为格局演变的重要观察点。综合来看，竞争重心正从资源比拼转向能力比拼，"
    "具备持续研发投入与知识管理体系的服务商有望在下一阶段扩大领先优势。"
    "从客户视角看，品牌信任度与交付确定性是选择服务商的首要考量，价格敏感度相对下降；"
    "从人才视角看，核心专家团队的稳定性直接影响交付质量与口碑传导，人才密度正在成为衡量机构竞争力的关键指标。"
)

SECTION_SPECS = [
    {"section_id": "section_a", "section_name": "市场规模现状", "section_role": "analysis"},
    {"section_id": "section_b", "section_name": "竞争格局分析", "section_role": "analysis"},
    {"section_id": "section_c", "section_name": "政策效果评估", "section_role": "analysis"},
]

TASK_STRUCTURE = {
    "topic": "中国专业服务市场研究",
    "output_format": "docx",
    "sections": [dict(spec) for spec in SECTION_SPECS],
}
FRAMEWORK = {"name": "通用市场研究报告"}


def _chapter_payload(text: str, conclusion: str) -> str:
    return json.dumps(
        {"status": "ready", "content": text, "key_conclusions": [conclusion],
         "self_check_passed": True, "self_check_issues": []},
        ensure_ascii=False,
    )


class _ScriptedExLLM:
    """chapter_writer.call_llm_ex 的脚本化替身（离线，无网络）。

    遵守真实 call_llm_ex 契约：按 task_tag 取脚本，驱动真实 RetryEngine
    （真实 Budget.scale_to / 真实 parse 钩子 / 真实变异阶梯），只有
    transport 的输出按脚本执行；记录每次传输调用的参数供断言。
    """

    def __init__(self):
        self._scripts = {}
        self._exhausted = {}
        self.calls = {}

    def script(self, task_tag, values):
        self._scripts[task_tag] = list(values)

    def exhaust(self, task_tag, error_class=LLMErrorClass.DEGENERATE):
        self._exhausted[task_tag] = error_class

    async def __call__(self, prompt_builder, *, output_contract="prose",
                       expected_output_chars=2000, budget=None, parse=None,
                       stream=False, on_token=None, routing_hint=None,
                       task_tag="", allow_prompt_compression=False, **kw):
        seen = self.calls.setdefault(task_tag, [])
        if task_tag in self._exhausted:
            error_class = self._exhausted[task_tag]
            seen.append({"exhausted": error_class.value})
            raise LLMBudgetExhausted(
                Classification(error_class, detail="scripted exhaustion"),
                attempts=4, elapsed=1.0,
                profile_notes=[f"mimo:4x{error_class.value}"],
            )
        script = list(self._scripts[task_tag])
        candidates = [_CANDIDATE]

        async def transport(candidate, *, prompt, model, max_tokens, temperature):
            seen.append({
                "prompt": prompt, "model": model,
                "max_tokens": max_tokens, "temperature": temperature,
            })
            value = script.pop(0)
            if isinstance(value, Exception):
                raise value
            return value

        engine = RetryEngine(
            transport=transport,
            candidates=lambda: candidates,
            parse=parse,
            budget=budget or Budget.scale_to(expected_output_chars),
            base_max_tokens=max(4096, int(expected_output_chars / 1.5 * 1.3)),
            task_tag=task_tag,
        )
        return await engine.run(
            prompt_builder=prompt_builder, output_contract=output_contract,
        )


def _orchestrator() -> ReportOrchestrator:
    writer = ChapterWriter(prompt_manager=PromptManager(), use_streaming=False)
    orchestrator = ReportOrchestrator(
        chapter_writer=writer,
        chapter_reviewer=MagicMock(),
        global_reviewer=MagicMock(),
        prompt_manager=PromptManager(),
    )
    orchestrator._report_progress = MagicMock()
    orchestrator._call_llm_tracked = AsyncMock(return_value={
        "success": True,
        "content": "执行摘要：市场总体保持扩张态势，政策体系不断完善，"
                   "竞争格局逐步优化，专业能力成为竞争核心变量。",
    })
    orchestrator._chapter_reviewer.review = AsyncMock(
        return_value=SimpleNamespace(passed=True, score=95.0, issues=[]),
    )
    return orchestrator


def _write_kwargs(spec):
    return dict(
        section_spec=spec,
        section_id=spec["section_id"],
        task_structure=TASK_STRUCTURE,
        framework_config=FRAMEWORK,
        chapter_data={"content": f"{spec['section_name']}分析素材。" * 20,
                      "upstream_data_points": []},
        preceding_summary="",
        raw_data_summary="无",
    )


class TestProductionSmoke:
    """write -> rescue cache -> defense rescue -> assemble 全主干冒烟。"""

    def test_full_spine_with_retry_engine(self):
        ex = _ScriptedExLLM()
        good_a = _chapter_payload(TEXT_A, "市场规模处于结构升级阶段，扩张与质量提升并行")
        good_b = _chapter_payload(TEXT_B, "竞争重心从资源比拼转向能力比拼，头部优势持续巩固")
        # 夹具契约：正常章节 raw JSON 必须 500+ 字符（真实章节形态）。
        assert len(good_a) >= 500
        assert len(good_b) >= 500
        ex.script("writer:section_a", [good_a])
        ex.script("writer:section_b", [_DEGENERATE_REFUSAL, good_b])
        ex.exhaust("writer:section_c", LLMErrorClass.DEGENERATE)

        with patch.object(chapter_writer_module, "call_llm_ex", ex):
            orchestrator = _orchestrator()
            chapter_a = asyncio.run(
                orchestrator._write_section_chapter(**_write_kwargs(SECTION_SPECS[0])))
            chapter_b = asyncio.run(
                orchestrator._write_section_chapter(**_write_kwargs(SECTION_SPECS[1])))
            chapter_c = asyncio.run(
                orchestrator._write_section_chapter(**_write_kwargs(SECTION_SPECS[2])))

        # ---- 章节 A：一次调用即就绪 ----
        assert chapter_a.status == "ready"
        assert len(chapter_a.content) > 300
        assert len(ex.calls["writer:section_a"]) == 1
        assert ex.calls["writer:section_a"][0]["temperature"] is None

        # ---- 章节 B：拒答 -> 引擎变异（标记格式强化 + temp0.1）-> 就绪 ----
        calls_b = ex.calls["writer:section_b"]
        assert len(calls_b) == 2
        assert calls_b[0]["temperature"] is None
        assert calls_b[1]["temperature"] == pytest.approx(0.1)
        # delimiter 契约下 strict_json rung 不再追加 JSON 前缀，而是由
        # prompt builder 追加标记格式强化（见 chapter_writer builders）。
        assert not calls_b[1]["prompt"].startswith(STRICT_JSON_PREFIX)
        assert calls_b[1]["prompt"].endswith("严格按上述标记格式输出，不要输出任何其他内容。")
        assert chapter_b.status == "ready"
        assert len(chapter_b.content) > 300

        # ---- 章节 C：预算耗尽 -> failed 章节 -> rescue cache 缓存素材 ----
        assert chapter_c.status == "failed"
        assert chapter_c.error == "budget_exhausted:degenerate"
        assert ex.calls["writer:section_c"][0]["exhausted"] == "degenerate"
        # 生产 phase-4 循环对 failed 章节的缓存步骤（orchestrator 写循环同款）。
        assert orchestrator._looks_like_failed_chapter(chapter_c)
        rescue_material = {
            "content": "政策效果评估基础素材：试点项目反馈、复购行为与续约意愿调研摘要，"
                       "客户对政策稳定性的预期明显改善。" * 12,
            "upstream_data_points": [],
        }
        orchestrator._cache_chapter_rescue_material(
            "section_c", SECTION_SPECS[2], rescue_material,
        )
        cached = orchestrator._chapter_rescue_cache["section_c"]
        assert cached["base_content"]
        assert cached["section_spec"]["section_id"] == "section_c"

        # ---- Defense 轮顶部 rescue：C 被重写交付 ----
        rescued_c = ChapterWriteOutput(
            chapter_id="section_c", title="政策效果评估",
            content="本节基于已有研究素材系统评估政策效果。" * 40,
            key_conclusions=["政策效果评估结论已有素材支撑"],
            self_check_passed=True, self_check_issues=[],
            status="ready", error="",
        )
        orchestrator._chapter_writer.write = AsyncMock(return_value=rescued_c)

        report = asyncio.run(orchestrator._run_defense_repair_loop(
            chapters=[chapter_a, chapter_b, chapter_c],
            review=ReviewOutput(overall_score=85.0),
            framework_config=FRAMEWORK,
            topic=TASK_STRUCTURE["topic"],
            task_structure=TASK_STRUCTURE,
            original_sources=[],
            quality_report=None,
            conflicts_summary="",
            max_rounds=3,
        ))

        orchestrator._chapter_writer.write.assert_awaited_once()

        # ---- 最终装配：三章节全部 ready ----
        sections = {s["section_id"]: s for s in report["sections"]}
        assert set(sections) == {"section_a", "section_b", "section_c"}
        for section in sections.values():
            assert section["status"] == "ready", section
            assert len(section["content"]) > 150
        assert sections["section_c"]["error"] == ""

        # ---- Defense 历史：记录了对 C 的 rescue，且审计通过 ----
        history = report["defense_loop"]["history"]
        assert len(history) == 1
        assert history[0]["rescued"], history
        assert history[0]["rescued"][0]["chapter_id"] == "section_c"
        assert report["defense_audit"]["passed"] is True

        # ---- exec summary 刷新：不崩溃、内容有效 ----
        # 注：exec summary 自引擎化迁移后走 call_llm_ex（本测不 patch 该缝，
        # 离线必然失败并落到 _deterministic_exec_summary 兜底）；不再经过
        # _call_llm_tracked（其唯一调用点已随迁移移除），故不计数。
        assert report["exec_summary"]
        assert "摘要生成失败" not in report["exec_summary"]
