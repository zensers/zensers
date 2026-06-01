"""
Validation: AI Simulation vs WVS Human Data

Compares simulated survey responses against real human data from WVS Wave 7.
Uses the SimulationCalibrator and existing benchmark data.

Usage:
    # Quick validation (100 sims, rule-based)
    python scripts/validate_simulation_vs_wvs.py --country CHN --sample-size 500 --rule-based

    # Full validation with LLM (requires API key)
    python scripts/validate_simulation_vs_wvs.py --country CHN --sample-size 500

    # Compare multiple countries
    python scripts/validate_simulation_vs_wvs.py --countries CHN,USA,DEU,GBR --sample-size 300 --rule-based
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from typing import List, Dict, Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import re  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("wvs_validation")


def load_wvs_benchmark(path: str, countries: List[str]) -> Dict[str, Any]:
    """Load WVS benchmark data and extract specified countries."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    all_countries = data.get("countries", {})
    result = {}
    for cc in countries:
        cc_upper = cc.upper()
        # Match by full key or prefix
        matched = None
        for k, v in all_countries.items():
            if k.upper() == cc_upper:
                matched = (k, v)
                break
        if not matched:
            # Partial match
            for k, v in all_countries.items():
                if k.upper().startswith(cc_upper):
                    matched = (k, v)
                    break
        if matched:
            result[matched[0]] = matched[1]
            logger.info("  Loaded %s (%s): %d respondents, %d questions",
                        matched[0], v.get("country_name", matched[0]),
                        matched[1].get("sample_size", 0),
                        len(matched[1].get("questions", {})))
        else:
            logger.warning("  Country %s not found in WVS data", cc)
    return result


# WVS question metadata
WVS_QUESTION_MAP = {
    "Q49":  {"text": "Most people can be trusted", "type": "single_choice",
             "options": [("1", "Most people can be trusted"), ("2", "Need to be very careful")]},
    "Q50":  {"text": "Satisfaction with your life", "type": "scale",
             "options": []},
    "Q221": {"text": "Confidence: Government", "type": "single_choice",
             "options": [("1", "None at all"), ("2", "Not very much"), ("3", "Quite a lot"), ("4", "A great deal")]},
    "Q222": {"text": "Confidence: Universities", "type": "single_choice",
             "options": [("1", "None at all"), ("2", "Not very much"), ("3", "Quite a lot"), ("4", "A great deal")]},
    "Q223": {"text": "Confidence: Press", "type": "single_choice",
             "options": [("1", "None at all"), ("2", "Not very much"), ("3", "Quite a lot"), ("4", "A great deal")]},
    "Q224": {"text": "Confidence: Courts", "type": "single_choice",
             "options": [("1", "None at all"), ("2", "Not very much"), ("3", "Quite a lot"), ("4", "A great deal")]},
    "Q260": {"text": "Age", "type": "single_choice", "options": []},
    "Q261": {"text": "Gender", "type": "single_choice",
             "options": [("1", "Male"), ("2", "Female")]},
    "Q262": {"text": "Education level", "type": "single_choice", "options": []},
    "Q270": {"text": "Employment status", "type": "single_choice", "options": []},
    "Q288": {"text": "Income level", "type": "single_choice", "options": []},
}


def build_survey(country_data: Dict, question_filter: str = "all") -> "Survey":
    """Build a Survey object from WVS question metadata, filtered by available questions."""
    from src.survey.models import Survey, Question, QuestionType, QuestionOption

    available = country_data.get("questions", {})
    allowed = [q.strip() for q in question_filter.split(",")] if question_filter != "all" else None

    questions = []
    for qid, qinfo in WVS_QUESTION_MAP.items():
        if qid not in available:
            continue
        if allowed and qid not in allowed:
            continue
        opts = []
        for oid, otext in qinfo.get("options", []):
            opts.append(QuestionOption(option_id=oid, text=otext))
        qtype = QuestionType.SINGLE_CHOICE if qinfo["type"] == "single_choice" else QuestionType.SCALE
        questions.append(Question(
            question_id=qid,
            text=qinfo["text"],
            question_type=qtype,
            options=opts,
        ))

    survey = Survey(
        survey_id="wvs_validation",
        title="World Values Survey (Wave 7) - Validation",
        questions=questions,
    )
    return survey


async def run_validation(country_code: str, country_data: Dict,
                         sample_size: int, llm_skill=None,
                         question_filter: str = "all"):
    """Run one country: simulate responses, calibrate against WVS benchmark."""
    from src.survey.models import Survey, SurveyResponse, Answer
    from src.survey.engine.persona_generator import PersonaGeneratorV2
    from src.survey.engine.simulation_engine import SimulationExecutor
    from src.survey.engine.calibrator import SimulationCalibrator, CalibrationReport
    from src.survey.engine.persona_models import PersonaV2
    from src.survey.engine.persona_templates import PersonaTemplateRegistry

    logger.info("\n=== %s (%s) ===", country_code, country_data.get("country_name", ""))
    logger.info("WVS sample size: %d, Sim target: %d",
                country_data.get("sample_size", 0), sample_size)

    # Step 1: Build survey from WVS questions
    survey = build_survey(country_data, question_filter)
    logger.info("Survey: %d questions", len(survey.questions))

    # Step 2: Multi-template simulation for demographic coverage
    from src.survey.engine.persona_templates import PersonaTemplateRegistry
    all_templates = PersonaTemplateRegistry.list_templates("consumer")

    # China-specific templates only (for CHN comparison)
    cn_template_ids = ["一线白领", "二三线家庭", "下沉市场用户", "Z世代学生", "高净值人群", "银发族"]
    cn_templates = [t for t in all_templates if t["id"] in cn_template_ids]
    if not cn_templates:
        cn_templates = all_templates[:4]

    per_tpl = max(2, sample_size // len(cn_templates))
    executor = SimulationExecutor(llm_skill=llm_skill, budget_limit=20.0)

    all_responses = []
    all_personas = []
    total_cost = 0.0

    for tpl in cn_templates:
        tpl_id = tpl["id"]
        try:
            result = await executor.execute(
                survey=survey,
                template_name=tpl_id,
                target_count=per_tpl,
                survey_context=f"WVS validation ({country_code})",
            )
            resp = result.get("responses", [])
            pers = result.get("personas", [])
            cost = result.get("cost_report", {}).get("total_cost", 0)
            all_responses.extend(resp)
            all_personas.extend(pers)
            total_cost += cost
            logger.info("  %s: %d responses, $%.4f", tpl_id, len(resp), cost)
        except Exception as e:
            logger.warning("  %s failed: %s", tpl_id, str(e)[:60])

    sim_responses = all_responses
    sim_personas = all_personas
    logger.info("\nTotal: %d responses from %d templates, $%.4f",
                len(sim_responses), len(cn_templates), total_cost)

    if not sim_responses:
        logger.error("No simulation responses generated!")
        return None

    # Step 4: Calibrate
    calibrator = SimulationCalibrator(
        benchmark_dir=os.path.join(os.path.dirname(__file__), "..", "data", "benchmarks"),
    )
    report = calibrator.calibrate(
        survey=survey,
        responses=sim_responses,
        benchmark_name="wvs_data",
        country=country_code,
        personas=sim_personas if sim_personas else None,
    )

    logger.info("\n=== Calibration Report ===")
    logger.info("Overall Fidelity:       %.4f  (1.0 = perfect match)", report.overall_fidelity)
    logger.info("Variance Ratio:         %.4f  (1.0 = ideal)", report.variance_ratio)
    logger.info("Distribution Overlap:   %.4f  (1.0 = identical)", report.distribution_overlap)
    logger.info("Questions matched:      %d / %d", report.question_count, len(survey.questions))
    logger.info("Simulation sample:      %d", report.sample_size)

    # Per-question breakdown (load benchmark again for display)
    try:
        bm_full = calibrator._load_benchmark("wvs_data")
        bm_questions_display = (bm_full.get("countries", {})
                                .get(country_code, {})
                                .get("questions", {}))
        logger.info("\nPer-question fidelity:")
        for q in survey.questions:
            bm = bm_questions_display.get(q.question_id)
            if not bm:
                continue
            sim_dist = calibrator._get_simulated_distribution(q, sim_responses)
            bm_dist = bm.get("distribution", {})
            if sim_dist and bm_dist:
                q_score = calibrator._distribution_similarity(sim_dist, bm_dist)
                top_human = sorted(bm_dist.items(), key=lambda x: -x[1])[:2]
                top_sim = sorted(sim_dist.items(), key=lambda x: -x[1])[:2]
                logger.info("  %-6s  f=%.3f  %s", qid, q_score, q.text[:50])
                logger.info("         human: %s  sim: %s",
                           {k: f"{v:.0%}" for k, v in top_human},
                           {k: f"{v:.0%}" for k, v in top_sim})
    except Exception as e:
        logger.debug("Per-question breakdown skipped: %s", e)

    if report.biases_detected:
        logger.info("Biases detected:       %s", ", ".join(report.biases_detected))

    if report.recommendations:
        logger.info("Recommendations:")
        for r in report.recommendations:
            logger.info("  - %s", r)

    return report


def print_comparison_table(all_reports: Dict[str, "CalibrationReport"]):
    """Print comparison table across countries."""
    print("\n" + "=" * 80)
    print("SIMULATION VS WVS HUMAN DATA - VALIDATION SUMMARY")
    print("=" * 80)
    print(f"{'Country':<10} {'Fidelity':<12} {'Var.Ratio':<12} {'Overlap':<12} {'Questions':<10} {'Sample':<10}")
    print("-" * 80)
    for cc, report in sorted(all_reports.items()):
        if report:
            print(f"{cc:<10} {report.overall_fidelity:<12.4f} {report.variance_ratio:<12.4f} "
                  f"{report.distribution_overlap:<12.4f} {report.question_count:<10} {report.sample_size:<10}")
    print("=" * 80)

    # Interpretation
    avg_fid = sum(r.overall_fidelity for r in all_reports.values() if r) / max(len(all_reports), 1)
    print(f"\nAverage Fidelity: {avg_fid:.4f}")
    print("\nFidelity Guide:")
    print("  >0.90    Excellent - Simulation closely matches human data")
    print("  0.75-0.90  Acceptable - Reasonable approximation")
    print("  0.60-0.75  Poor - Noticeable deviation")
    print("  <0.60    Not reliable - Distribution differs significantly from human responses")
    print("")
    if avg_fid < 0.60:
        print("╔" + "═" * 78 + "╗")
        print("║ Fidelity = {:.4f} — below the 0.60 threshold.                                       ║".format(avg_fid))
        print("║ Possible causes:                                                                     ║")
        print("║   1. Template mismatch (single demographic vs general population)                    ║")
        print("║   2. Small sample size (adds statistical noise)                                      ║")
        print("║   3. Genuine LLM response bias vs human responses                                    ║")
        print("║                                                                                      ║")
        print("║ To improve: use multi-template mix (--mix) or increase sample size (>200)            ║")
        print("╚" + "═" * 78 + "╝")


async def main():
    parser = argparse.ArgumentParser(
        description="Validate AI simulation against WVS human survey data"
    )
    parser.add_argument("--countries", default="CHN",
                        help="Comma-separated country codes (default: CHN)")
    parser.add_argument("--sample-size", type=int, default=500,
                        help="Simulation sample size per country (default: 500)")
    parser.add_argument("--questions", default="all",
                        help="Comma-separated question IDs (default: all, e.g. Q221,Q49)")
    parser.add_argument("--rule-based", action="store_true",
                        help="Use rule-based fallback (no LLM). Default behavior.")
    parser.add_argument("--no-llm", action="store_true",
                        help="Alias for --rule-based")
    args = parser.parse_args()

    countries = [c.strip() for c in args.countries.split(",")]

    # Load WVS benchmark
    wvs_path = os.path.join(os.path.dirname(__file__), "..", "data", "benchmarks", "wvs_data.json")
    if not os.path.exists(wvs_path):
        logger.error("WVS data not found at %s", wvs_path)
        sys.exit(1)

    logger.info("Loading WVS benchmark data...")
    wvs_data = load_wvs_benchmark(wvs_path, countries)
    if not wvs_data:
        logger.error("No matching countries found in WVS data")
        sys.exit(1)

    # Initialize LLM skill if not using rule-based fallback
    llm_skill = None
    use_llm = not args.rule_based and not args.no_llm
    if use_llm:
        try:
            from src.skills.llm_skill import LLMSkill
            llm_skill = LLMSkill()
            logger.info("LLM backend initialized: %s", llm_skill.name)
        except Exception as e:
            logger.warning("Failed to initialize LLM, falling back to rule-based: %s", e)
            use_llm = False

    logger.info("Running validation for %d countries (mode: %s)...",
                len(wvs_data), "LLM" if use_llm else "rule-based")
    all_reports = {}
    for cc, country_data in wvs_data.items():
        report = await run_validation(cc, country_data, args.sample_size,
                                      llm_skill=llm_skill if use_llm else None,
                                      question_filter=args.questions)
        all_reports[cc] = report

    print_comparison_table(all_reports)


if __name__ == "__main__":
    asyncio.run(main())
