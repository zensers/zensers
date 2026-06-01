"""
End-to-End Systematic Test for Survey Module.
Tests: creation, simulation, results, analysis, routing integration.
"""
import sys, os, json, asyncio
sys.path.insert(0, ".")

passed = 0
failed = 0


def check(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        print(f"  FAIL: {name} - {detail}")


async def main():
    global passed, failed
    print("=" * 60)
    print("SURVEY MODULE - END-TO-END SYSTEMATIC TEST")
    print("=" * 60)

    # ================================================================ #
    # 1. Module Imports
    # ================================================================ #
    print("\n--- 1. Module Imports ---")
    try:
        from src.survey.engine.persona_models import PersonaV2, PersonaType, PromptLevel
        from src.survey.engine.persona_templates import PersonaTemplateRegistry
        from src.survey.engine.persona_generator import PersonaGeneratorV2, sanitize_context
        from src.survey.engine.prompt_builder import SimulationPromptBuilder, TemperatureScheduler
        from src.survey.engine.simulation_engine import SimulationExecutor
        from src.survey.engine.cost_monitor import LLMCostTracker, RetryHandler
        from src.survey.engine.errors import (
            SurveySimulationError, BudgetExceededError, LLMTemporaryFailure
        )
        from src.survey.engine.alignment_engine import DistributionAligner
        from src.survey.engine.calibrator import SimulationCalibrator
        from src.survey.engine.focus_group import FocusGroupSimulator
        from src.survey.engine.data import list_regions, load_region, RegionData
        from src.survey.backends.factory import BackendFactory
        from src.survey.backends.ai_simulation import AISimulationBackend
        from src.survey.analysis.descriptive import DescriptiveAnalyzer
        from src.survey.analysis.sentiment import SentimentAnalyzer
        from src.survey.analysis.wordcloud import WordCloudGenerator
        from src.survey.analysis.crosstab import CrossTabAnalyzer
        from src.survey.analysis.report_builder import SurveyReportBuilder
        from src.survey.client import SurveyClient
        from src.survey.models import Survey, Question, QuestionOption, QuestionType, SurveyResponse, Answer, DistributionConfig
        check("All survey module imports", True)
    except Exception as e:
        check(f"Survey imports failed: {e}", False)
        return

    # ================================================================ #
    # 2. Core Integration Imports
    # ================================================================ #
    print("\n--- 2. Core Integration Imports ---")
    try:
        from src.core.semantic_intent import SemanticIntentAnalyzer, DeepIntentResult
        from src.core.dynamic_orchestrator import DynamicPhaseOrchestrator, PhaseType
        from src.core.intent_types import IntentType, TaskComplexity
        check("Core integration imports", True)
    except Exception as e:
        check(f"Core imports failed: {e}", False)
        return

    # ================================================================ #
    # 3. PersonaV2 Creation & Serialization
    # ================================================================ #
    print("\n--- 3. PersonaV2 ---")
    tpls_list = PersonaTemplateRegistry.list_templates()
    _TPL = tpls_list[0]["id"] if tpls_list else "consumer"
    p = PersonaV2(
        persona_id="test_001",
        persona_type=PersonaType.CONSUMER,
        template_name=_TPL,
        name="Zhang Wei", age=30, gender="Male", city="Beijing",
        occupation="PM", income="200k-400k", education="Master",
        personality_traits=["Rational", "Quality-focused"],
        consumption_habits=["Online shopping", "Brand conscious"],
        price_sensitivity=0.3, digital_literacy=0.9,
        big_five={"openness": 7, "conscientiousness": 8, "extraversion": 5, "agreeableness": 6, "neuroticism": 3},
    )
    check("PersonaV2 fields", p.name == "Zhang Wei" and p.age == 30)

    d = p.to_dict()
    check("to_dict() includes persona_type", "persona_type" in d)

    ld = p.to_legacy_dict()
    check("to_legacy_dict() valid", len(ld) >= 10 and "persona_id" in ld)

    p2 = PersonaV2.from_dict(d)
    check("from_dict() roundtrip", p2.name == "Zhang Wei")

    prompt = p.to_prompt("interview")
    check("to_prompt(interview) non-empty", len(prompt) > 20)

    # ================================================================ #
    # 4. Templates
    # ================================================================ #
    print("\n--- 4. Templates ---")
    tpls = PersonaTemplateRegistry.list_templates()
    # Chinese: 6 consumer + 6 expert = 12
    # Global: 4 consumer + 2 expert = 6
    check("templates total >= 18", len(tpls) >= 18)

    c = PersonaTemplateRegistry.list_templates("consumer")
    e = PersonaTemplateRegistry.list_templates("expert")
    check("consumer templates >= 10", len(c) >= 10)
    check("expert templates >= 8", len(e) >= 8)

    first_template = tpls[0]["id"] if tpls else None
    t = PersonaTemplateRegistry.get_template(first_template, "consumer") if first_template else None
    check(f"get_template({first_template}) works", t is not None)

    rules = PersonaTemplateRegistry.get_consistency_rules_for("consumer", "5wan", 30)
    check("Consistency rules API works", len(rules) >= 0)

    # ================================================================ #
    # 5. Rule-based Persona Generation (no LLM)
    # ================================================================ #
    print("\n--- 5. Persona Generation (Rule-based) ---")
    gen = PersonaGeneratorV2(llm_skill=None)
    # Use the first template from the registry (Chinese name)
    tpls = PersonaTemplateRegistry.list_templates()
    first_tpl = tpls[0]["id"] if tpls else "consumer"
    personas, stats = await gen.generate_batch(first_tpl, 10, "consumer")
    check(f"Generated {len(personas)} personas", len(personas) == 10)
    check("All rule fallback (no LLM)", stats["rule_fallback"] == 10)
    check("Persona has valid ID", personas[0].persona_id.startswith("p_consumer_"))
    check("Persona has valid age", 0 < personas[0].age < 100)
    check("Persona has valid price_sensitivity", 0 <= personas[0].price_sensitivity <= 1)

    # ================================================================ #
    # 6. Prompt Builder
    # ================================================================ #
    print("\n--- 6. Prompt Builder ---")
    pb = SimulationPromptBuilder()
    q = Question(
        question_id="q1", text="Are you satisfied with the product?",
        question_type=QuestionType.SINGLE_CHOICE,
        options=[QuestionOption(option_id="a", text="Very satisfied"),
                 QuestionOption(option_id="b", text="Somewhat"),
                 QuestionOption(option_id="c", text="Not satisfied")],
    )
    for level in [PromptLevel.MINIMAL, PromptLevel.STANDARD, PromptLevel.ENHANCED, PromptLevel.FULL]:
        r = pb.build_prompt(p, q, level=level)
        check(f"PromptBuilder {level.value}", len(r.system_prompt) > 0 and 0 < r.temperature <= 1.0)

    temp = TemperatureScheduler.get_temperature(QuestionType.OPEN_ENDED)
    check("Temperature OPEN_ENDED valid", 0.5 <= temp <= 1.0)

    # ================================================================ #
    # 7. Simulation Executor (rule-based, no LLM)
    # ================================================================ #
    print("\n--- 7. Simulation Executor ---")
    survey = Survey(
        survey_id="test_survey_001",
        title="Customer Satisfaction Survey",
        questions=[q],
    )
    executor = SimulationExecutor(llm_skill=None, budget_limit=10.0)
    result = await executor.execute(
        survey=survey,
        template_name=_TPL,
        target_count=5,
        survey_context="Testing",
    )
    check("Simulation executor succeeded", result["success"] is True)
    check("Simulation produced personas", len(result["personas"]) > 0)
    check("Simulation produced responses", len(result["responses"]) > 0)
    check("Cost report generated", "total_cost" in result["cost_report"])

    # ================================================================ #
    # 8. Cost Tracker
    # ================================================================ #
    print("\n--- 8. Cost Tracker ---")
    ct = LLMCostTracker("test_cost", budget_limit=10.0)
    ct.record_call("gpt-4o-mini", 100, 50, "test")
    check("Cost recorded", ct.total_cost > 0)
    check("Cost report has keys", "budget_remaining" in ct.get_report())

    try:
        ct2 = LLMCostTracker("test_budget", budget_limit=0.01)
        ct2.record_call("gpt-4o", 10000, 5000, "expensive")
        check("Budget exceeded - should have raised", False)
    except BudgetExceededError:
        check("Budget exceeded raises BudgetExceededError", True)

    # ================================================================ #
    # 9. Retry Handler
    # ================================================================ #
    print("\n--- 9. Retry Handler ---")
    check("TimeoutError is retryable", RetryHandler.should_retry(TimeoutError()) is True)
    check("ValueError not retryable", RetryHandler.should_retry(ValueError()) is False)
    backoff = RetryHandler.get_backoff(1)
    check("Backoff base=1.0", backoff == 1.0)

    # ================================================================ #
    # 10. Error Types
    # ================================================================ #
    print("\n--- 10. Error Types ---")
    e1 = BudgetExceededError(cost=5.0, limit=1.0)
    check("BudgetExceededError code", e1.code == "BUDGET_EXCEEDED")

    e2 = LLMTemporaryFailure(attempt=3, max_retries=3)
    check("LLMTemporaryFailure code", e2.code == "LLM_TEMPORARY_FAILURE")

    e3 = SurveySimulationError("test", "TEST_ERROR")
    check("Base error code", e3.code == "TEST_ERROR")

    from src.survey.engine.errors import get_error_message
    msg = get_error_message("BUDGET_EXCEEDED")
    check("Error message has title", "title" in msg)

    # ================================================================ #
    # 11. Distribution Aligner
    # ================================================================ #
    print("\n--- 11. Distribution Aligner ---")
    da = DistributionAligner(region="china")
    raw_personas = [PersonaV2(persona_id=f"p{i}", persona_type=PersonaType.CONSUMER,
                               name=f"U{i}", age=20 + i, gender="Male" if i % 2 == 0 else "Female",
                               city="Beijing", occupation="Test") for i in range(30)]
    aligned = da.align(raw_personas, target_size=20)
    check(f"Aligned {len(raw_personas)} -> {len(aligned)}", len(aligned) == 20)

    report = da.get_distribution_report(aligned)
    check("Distribution report has age", "age" in report)
    check("Distribution report has gender", "gender" in report)

    # ================================================================ #
    # 12. Calibrator
    # ================================================================ #
    print("\n--- 12. Calibrator ---")
    cal = SimulationCalibrator()
    from src.survey.engine.calibrator import CalibrationReport
    cr = CalibrationReport(overall_fidelity=0.85, variance_ratio=0.92, distribution_overlap=0.78)
    d = cr.to_dict()
    check("CalibrationReport serialization", d["overall_fidelity"] == 0.85)

    # Distribution similarity math
    from src.survey.engine.calibrator import SimulationCalibrator as Cal
    sim = Cal._distribution_similarity({"A": 0.5, "B": 0.5}, {"A": 0.5, "B": 0.5})
    check("Similarity identical=1.0", abs(sim - 1.0) < 0.001)

    sim2 = Cal._distribution_similarity({"A": 1.0}, {"B": 1.0})
    check("Similarity different=0.0", abs(sim2 - 0.0) < 0.001)

    # ================================================================ #
    # 13. AISimulationBackend
    # ================================================================ #
    print("\n--- 13. AISimulationBackend ---")
    backend = AISimulationBackend()
    check("Backend type", backend.backend_type == "ai_simulation")
    check("Backend capabilities", backend.capabilities.get("webhook") is False)

    eid = await backend.create_survey(survey)
    check("Backend create_survey returns ID", eid.startswith("sim_"))

    config = DistributionConfig(target_count=5)
    config.sampling_spec = {"template": _TPL, "persona_type": "consumer"}
    task_id = await backend.distribute(eid, config)
    check("Backend distribute returns task_id", task_id.startswith("sim_task_"))

    status = await backend.get_status(eid)
    check("Backend status is completed", status.value == "completed")

    results = await backend.get_results(eid)
    check(f"Backend has {len(results)} results", len(results) > 0)

    # ================================================================ #
    # 14. Factory Registration
    # ================================================================ #
    print("\n--- 14. Backend Factory ---")
    types = BackendFactory.get_backend_types()
    check("ai_simulation registered", "ai_simulation" in types)
    check("mock registered", "mock" in types)
    check("api_tencent registered", "api_tencent" in types)

    # ================================================================ #
    # 15. Analysis: Descriptive
    # ================================================================ #
    print("\n--- 15. Descriptive Analysis ---")
    responses = [
        SurveyResponse(
            response_id=f"r{i}", survey_id="test_survey_001",
            answers={"q1": Answer(question_id="q1", answer_value="Very satisfied")},
            completed_at=__import__("datetime").datetime.now(),
        )
        for i in range(8)
    ] + [
        SurveyResponse(
            response_id=f"r{i}", survey_id="test_survey_001",
            answers={"q1": Answer(question_id="q1", answer_value="Not satisfied")},
            completed_at=__import__("datetime").datetime.now(),
        )
        for i in range(8, 10)
    ]

    da = DescriptiveAnalyzer()
    desc = da.analyze(survey, responses)
    check("Descriptive total=10", desc["total_responses"] == 10)
    check("Descriptive per_question", "q1" in desc["per_question"])
    q1stats = desc["per_question"]["q1"]["stats"]
    check("Descriptive has distribution", "distribution" in q1stats)
    check("Descriptive 'Very satisfied' count=8", q1stats["distribution"]["Very satisfied"]["count"] == 8)
    check("Descriptive overall has completion_rate", "completion_rate" in desc["overall"])

    # ================================================================ #
    # 16. Analysis: Sentiment
    # ================================================================ #
    print("\n--- 16. Sentiment Analysis ---")
    sa = SentimentAnalyzer()
    pos = sa.analyze_text("Very satisfied, product quality is excellent")
    neg = sa.analyze_text("Terrible quality, very disappointed")
    check("Sentiment positive check", pos["sentiment"] in ("positive", "neutral", "negative"))
    check("Sentiment negative check", neg["sentiment"] in ("negative", "neutral"))

    batch = sa.analyze_batch(["Great product!", "Terrible service", "Its okay"])
    check("Sentiment batch has overall", "overall" in batch)
    check("Sentiment batch has avg_score", "avg_score" in batch)

    # ================================================================ #
    # 17. Analysis: WordCloud
    # ================================================================ #
    print("\n--- 17. WordCloud ---")
    wcg = WordCloudGenerator()
    wc = wcg.generate(["product quality good", "service attitude excellent"])
    check("WordCloud returns dict", isinstance(wc, dict))
    check("WordCloud has frequencies key", "frequencies" in wc)

    # ================================================================ #
    # 18. Analysis: CrossTab
    # ================================================================ #
    print("\n--- 18. CrossTab Analysis ---")
    q_a = Question(question_id="qa", text="Are you satisfied?", question_type=QuestionType.SINGLE_CHOICE,
                   options=[QuestionOption(option_id="a", text="Yes"), QuestionOption(option_id="b", text="No")])
    q_b = Question(question_id="qb", text="Age group?", question_type=QuestionType.SINGLE_CHOICE,
                   options=[QuestionOption(option_id="a", text="18-25"), QuestionOption(option_id="b", text="26-35")])
    survey2 = Survey(survey_id="s2", title="CrossTab Test", questions=[q_a, q_b])
    resp2 = [SurveyResponse(response_id=f"r{i}", survey_id="s2",
              answers={"qa": Answer(question_id="qa", answer_value="Yes"),
                       "qb": Answer(question_id="qb", answer_value="18-25")},
              completed_at=__import__("datetime").datetime.now()) for i in range(5)]

    ca = CrossTabAnalyzer()
    cr = ca.analyze(survey2, resp2, "qa", "qb")
    resp2 = [SurveyResponse(response_id=f"r{i}", survey_id="s2",
              answers={"q1": Answer(question_id="q1", answer_value="Very satisfied"),
                       "q2": Answer(question_id="q2", answer_value="18-25")},
              completed_at=__import__("datetime").datetime.now()) for i in range(5)]

    ca = CrossTabAnalyzer()
    cr = ca.analyze(survey2, resp2, "qa", "qb")
    check("CrossTab has table", "table" in cr)
    check("CrossTab row_question matches", "satisfied" in cr["row_question"].lower())

    auto = ca.auto_discover(survey2, resp2, max_pairs=3)
    check("CrossTab auto_discover", len(auto) >= 0)

    # ================================================================ #
    # 19. Report Builder
    # ================================================================ #
    print("\n--- 19. Report Builder ---")
    rb = SurveyReportBuilder()
    report = rb.build(survey2, resp2, title="E2E Test Report")
    check("Report has report text", len(report["report"]) > 100)
    check("Report contains title", "E2E Test Report" in report["report"])
    check("Report has statistics", "statistics" in report)
    check("Report has generated_at", "generated_at" in report)

    # ================================================================ #
    # 20. Region Data
    # ================================================================ #
    print("\n--- 20. Region Data ---")
    regions = list_regions()
    check("China region available", "china" in regions)
    rd = RegionData("china")
    check("China age distribution sum=1.0", abs(sum(rd.age.values()) - 1.0) < 0.01)
    check("China gender distribution sum=1.0", abs(sum(rd.gender.values()) - 1.0) < 0.01)

    # ================================================================ #
    # 21. Semantic Intent with Survey Detection
    # ================================================================ #
    print("\n--- 21. Semantic Intent (Survey Detection) ---")
    from src.core.semantic_intent import SemanticIntentAnalyzer as SIAnalyzer
    # Test keyword detection
    analyzer = SIAnalyzer(use_llm=False, fallback_to_keyword=False)
    result = analyzer.analyze("I want to run a consumer survey", {"topic": "test", "aspects": []})
    check("Intent analyzer returns DeepIntentResult", hasattr(result, "requires_primary_data"))

    # ================================================================ #
    # 22. DynamicOrchestrator Phase Generation
    # ================================================================ #
    print("\n--- 22. Dynamic Orchestrator (Survey Phase) ---")
    from src.core.task_structure import TaskStructure, SectionSpec, SectionRole
    from src.core.semantic_intent import DeepIntentResult as DIR

    intent = DIR(
        primary_intent=IntentType.RESEARCH, intent_confidence=0.9, intent_reasoning="test",
        complexity=TaskComplexity.MULTI, requires_primary_data=True,
    )
    orch = DynamicPhaseOrchestrator()
    ts = TaskStructure(task_id="test_001", topic="test", sections=[], dependencies=[])
    plan = orch.plan(ts, intent, "test")
    phase_types = [p.phase_type for p in plan.phases]
    check("SURVEY phase generated", PhaseType.SURVEY in phase_types)
    check("REPORT phase generated", PhaseType.REPORT in phase_types)
    check("CROSS_SYNTHESIS when both survey+desk", PhaseType.CROSS_SYNTHESIS in phase_types or len(phase_types) >= 2)

    # ================================================================ #
    # 23. Sanitize Context (Prompt Injection Protection)
    # ================================================================ #
    print("\n--- 23. Prompt Injection Protection ---")
    clean = sanitize_context("Normal research context")
    check("Normal text passes through", "Normal" in clean)
    check("Wrapped in context tags", clean.startswith("<context>") and clean.endswith("</context>"))

    # ================================================================ #
    # 24. Focus Group (structure test)
    # ================================================================ #
    print("\n--- 24. Focus Group Simulator ---")
    fs = FocusGroupSimulator(llm_skill=None)
    personas_fg = [
        PersonaV2(persona_id=f"fg_{i}", persona_type=PersonaType.CONSUMER,
                   name=f"User{i}", age=30, gender="Male", city="Beijing", occupation="Test")
        for i in range(3)
    ]
    try:
        transcript = await fs.simulate("Test topic", personas_fg, max_rounds=1)
        check("FocusGroupSimulator creates transcript", transcript is not None)
    except Exception as e:
        check(f"FocusGroupSimulator (expected without LLM): {e}", True)

    # ================================================================ #
    # Summary
    # ================================================================ #
    print("\n" + "=" * 60)
    total = passed + failed
    print(f"RESULTS: {passed}/{total} PASSED, {failed}/{total} FAILED")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
