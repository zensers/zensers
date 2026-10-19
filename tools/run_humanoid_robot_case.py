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
DOMAIN_KEYWORDS = ["机器人", "人形", "具身", "整机", "本体"]


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
    print("=" * 60, flush=True)

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
    if not report or not isinstance(report.get("sections"), list):
        print("报告内容无效")
        return None

    json_file = OUTPUT_DIR / "research_result.json"
    json_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"结果已保存: {json_file}")

    secs = report.get("sections", [])
    total_chars = sum(len(s.get("content", "")) for s in secs)
    print(f"章节: {len(secs)} | 总字符: {total_chars}")
    for s in secs:
        print(f"  [{s.get('title', '')[:20]}] {len(s.get('content', ''))}字 "
              f"dp={len(s.get('data_points', []))} charts={len(s.get('charts', []))}")
        if domain_score(s.get("content", "")) < 1.0:
            print(f"    !! 主题疑似漂移: {s.get('title', '')}")
    fc = report.get("_framework_config", {}) or {}
    print(f"框架: min_section_length={fc.get('agent_config', {}).get('content', {}).get('min_section_length')} "
          f"max_total_searches={fc.get('agent_config', {}).get('search', {}).get('max_total_searches')}")
    da = report.get("defense_audit", {}) or {}
    l3_missing = sum(1 for i in (da.get("issues") or []) if i.get("code") == "missing_source_url")
    print(f"质量: formal_complete={report.get('formal_complete')} quality_gate={report.get('quality_gate_status')} "
          f"L3缺URL={l3_missing} defense_issues={len(da.get('issues') or [])}")
    return json_file


async def main():
    r = await run_research()
    print("\n下一步: python tools/render_humanoid_case_docx.py" if r else "\n运行失败，检查日志")


if __name__ == "__main__":
    asyncio.run(main())