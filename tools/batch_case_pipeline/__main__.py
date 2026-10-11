# -*- coding: utf-8 -*-
"""批量案例流水线入口：串行调度 + 断点续跑 + 全自动审查闭环。

用法:
  python -m tools.batch_case_pipeline                       # 跑全池
  python -m tools.batch_case_pipeline --cases humanoid_robot
  python -m tools.batch_case_pipeline --from-stage charts --cases c1
  python -m tools.batch_case_pipeline --list
"""
import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
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


async def _review_loop(ctx, cfg: BatchConfig, case: CaseConfig, case_dir: Path,
                       state: CaseState, research_result: Dict[str, Any]
                       ) -> Dict[str, Any]:
    """全自动审查闭环，返回最终 review report。"""
    rounds = 0
    report: Dict[str, Any] = {"pass": False, "score": 0, "issues": []}
    while rounds < cfg.max_review_rounds:
        rounds += 1
        report = await review.collect_issues_async(research_result, case, case_dir)
        review.save_review_report(case_dir, rounds, report)
        state.mark_done("review", {"round": rounds, "score": report["score"],
                                   "pass": report["pass"]})
        state.save()
        if report["pass"]:
            break
        high = [i for i in report["issues"] if i.get("severity") == "high"]
        if not high or rounds >= cfg.max_review_rounds:
            break
        logger.info("[%s] 第%d轮审查未过(score=%d)，修订 %d 个 high 问题",
                    case.case_id, rounds, report["score"], len(high))
        rerun = await apply_fixes(high, research_result,
                                  domain_keywords=case.domain_keywords)
        (case_dir / "research_result.json").write_text(
            json.dumps(research_result, ensure_ascii=False, indent=1, default=str),
            encoding="utf-8")
        if not rerun:
            break
        if "charts" in rerun:
            state.reset_from("charts")
            await stages.run_charts(ctx, case, case_dir, state, research_result)
        elif "render" in rerun:
            state.reset_from("render")
        if not state.is_done("render"):
            await stages.run_render(ctx, case, case_dir, state, research_result)
        state.save()
    return report


async def run_case(ctx, cfg: BatchConfig, case: CaseConfig, output_root: Path,
                   from_stage: Optional[str] = None) -> Dict[str, Any]:
    case_dir = output_root / "cases" / case.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    state = CaseState.load(case_dir / "state.json", case.case_id)
    started = time.time()
    if from_stage:
        state.reset_from(from_stage)
    state.set_case_status("running")
    state.save()
    summary: Dict[str, Any] = {"case_id": case.case_id, "status": "running",
                               "review_rounds": 0, "final_score": 0}
    try:
        # run_research 自身幂等：已有 research_result.json 则 skipped=True，不触发 ctx
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

        report = await _review_loop(ctx, cfg, case, case_dir, state,
                                    research_result)

        high_left = [i for i in report["issues"] if i.get("severity") == "high"]
        if report["pass"] or not high_left:
            state.set_case_status("done")
        else:
            state.set_case_status("needs_human")
        state.save()
        manifest = stages.run_finalize(case, case_dir, state,
                                       report["score"],
                                       state.meta("review").get("round", 0))
        state.save()
        summary.update({"status": state.case_status,
                        "review_rounds": state.meta("review").get("round", 0),
                        "final_score": report["score"],
                        "docx": manifest.get("docx", ""),
                        "seconds": round(time.time() - started, 1)})
    except Exception as exc:
        logger.exception("[%s] 案例失败", case.case_id)
        stage = state.current_stage() or "research"
        state.mark_failed(stage, str(exc))
        state.set_case_status("failed")
        state.save()
        summary.update({"status": "failed", "error": str(exc),
                        "seconds": round(time.time() - started, 1)})
    return summary


def _init_llm() -> None:
    from dotenv import load_dotenv
    load_dotenv()
    import os
    os.environ.setdefault("ZENSERS_MAX_TOTAL_SEARCHES", "60")
    from src.config.settings import settings
    from src.core.llm_client import init_llm_infrastructure
    init_llm_infrastructure(settings.llm_profiles)


async def main_async(argv=None) -> int:
    parser = argparse.ArgumentParser(description="zensers 批量案例流水线")
    parser.add_argument("--config", default=None, help="案例池 YAML 路径")
    parser.add_argument("--cases", default=None, help="逗号分隔 case_id")
    parser.add_argument("--from-stage", default=None, choices=STAGES)
    parser.add_argument("--max-review-rounds", type=int, default=None)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(argv)

    setup_logging()
    try:
        cfg = load_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("配置错误: %s", exc)
        return 2
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

    _init_llm()
    from tools.batch_case_pipeline.stages import DefaultCtx
    ctx = DefaultCtx()

    results = []
    for i, case in enumerate(selected, 1):
        logger.info("=== [%d/%d] %s: %s ===", i, len(selected),
                    case.case_id, case.topic)
        summary = await run_case(ctx, cfg, case, output_root,
                                 from_stage=args.from_stage)
        if summary["status"] == "failed":          # 失败自动重试 1 次（断点续跑）
            logger.warning("[%s] 失败，重试 1 次", case.case_id)
            summary = await run_case(ctx, cfg, case, output_root,
                                     from_stage=args.from_stage)
        results.append(summary)

    summary_path = output_root / "batch_summary.json"
    summary_path.write_text(json.dumps(
        {"finished_at": time.strftime("%Y-%m-%d %H:%M:%S"), "cases": results},
        ensure_ascii=False, indent=1), encoding="utf-8")
    ok = sum(1 for r in results if r["status"] in ("done", "needs_human"))
    logger.info("批次完成: %d/%d 成功，汇总: %s", ok, len(results), summary_path)
    return 0 if ok == len(results) else 1


def main() -> None:
    sys.exit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
