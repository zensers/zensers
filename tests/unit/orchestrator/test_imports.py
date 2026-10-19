"""Test import compatibility for orchestrator modules."""
import sys


def test_execution_imports():
    """Test execution layer imports."""
    from src.core.orchestrator.execution import (
        ExecutionEngine, ExecutionConfig, ExecutionResult,
        ConcurrencyManager, RetryManager, TimeoutController,
        BackgroundExecutor, ResultValidator,
        AgentCoordinator, TaskDispatcher, ProgressTracker,
        HeartbeatMonitor, CancelManager,
    )
    assert ExecutionEngine is not None
    assert ExecutionConfig is not None
    assert ExecutionResult is not None


def test_aggregation_imports():
    """Test aggregation layer imports."""
    from src.core.orchestrator.aggregation import (
        ResultAggregator, AggregationResult,
        KnowledgeCompiler, KnowledgePage,
        WisdomRecorder, ExperienceRecord,
    )
    assert ResultAggregator is not None
    assert AggregationResult is not None
    assert KnowledgeCompiler is not None


def test_output_imports():
    """Test output layer imports."""
    from src.core.orchestrator.output import (
        ReportGenerator, ReportResult,
        DocumentGenerator, DocumentResult,
        StorageManager, StorageConfig, ResearchRecord,
    )
    assert ReportGenerator is not None
    assert ReportResult is not None
    assert DocumentGenerator is not None


def test_orchestrator_imports():
    """Test main orchestrator imports."""
    from src.core.orchestrator import (
        ResearchOrchestrator, ResearchRequirement, ResearchResult,
    )
    assert ResearchOrchestrator is not None
    assert ResearchRequirement is not None
    assert ResearchResult is not None


def test_backward_compatibility():
    """Test backward compatibility with legacy import."""
    from src.core.orchestrator.research_orchestrator import ResearchOrchestrator as LegacyOrchestrator
    from src.core.orchestrator import ResearchOrchestrator
    assert LegacyOrchestrator is ResearchOrchestrator
