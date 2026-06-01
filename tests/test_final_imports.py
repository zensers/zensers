"""Final import verification."""
import sys; sys.path.insert(0, '.')
import importlib

checks = [
    ("PersonaV2", "src.survey.engine.persona_models"),
    ("PersonaTemplateRegistry", "src.survey.engine.persona_templates"),
    ("PersonaGeneratorV2", "src.survey.engine.persona_generator"),
    ("SimulationPromptBuilder", "src.survey.engine.prompt_builder"),
    ("SimulationExecutor", "src.survey.engine.simulation_engine"),
    ("LLMCostTracker", "src.survey.engine.cost_monitor"),
    ("RetryHandler", "src.survey.engine.cost_monitor"),
    ("SurveySimulationError", "src.survey.engine.errors"),
    ("BudgetExceededError", "src.survey.engine.errors"),
    ("DistributionAligner", "src.survey.engine.alignment_engine"),
    ("SimulationCalibrator", "src.survey.engine.calibrator"),
    ("FocusGroupSimulator", "src.survey.engine.focus_group"),
    ("RegionData", "src.survey.engine.data"),
    ("AISimulationBackend", "src.survey.backends.ai_simulation"),
    ("BackendFactory", "src.survey.backends.factory"),
    ("DescriptiveAnalyzer", "src.survey.analysis.descriptive"),
    ("SentimentAnalyzer", "src.survey.analysis.sentiment"),
    ("CrossTabAnalyzer", "src.survey.analysis.crosstab"),
    ("SurveyReportBuilder", "src.survey.analysis.report_builder"),
    ("SemanticIntentAnalyzer", "src.core.semantic_intent"),
    ("DynamicPhaseOrchestrator", "src.core.dynamic_orchestrator"),
]

all_ok = True
for name, module in checks:
    try:
        m = importlib.import_module(module)
        getattr(m, name)
        print(f"OK: {name:35s} <- {module}")
    except Exception as e:
        print(f"FAIL: {name}: {e}")
        all_ok = False

print()
print("ALL OK" if all_ok else "SOME FAILED")
