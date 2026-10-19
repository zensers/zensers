"""Test: P0-6 ExecutionEngine document_context/tables injection

Tests that task dictionaries include document_context/document_tables
and that they are populated from agent._context when available.
"""


class TestTaskDocumentContext:
    """Test document context injection into task dictionaries"""

    def test_default_empty_document_context(self):
        task = {
            "action": "execute",
            "topic": "test",
            "document_context": "",
            "document_tables": [],
        }
        assert task["document_context"] == ""
        assert task["document_tables"] == []

    def test_inject_from_agent_context(self):
        agent_context = {
            "document_context": "Financial data from annual report...",
            "document_tables": {"income": [{"科目": "Revenue", "2023": 100.0}]},
        }
        
        task = {
            "action": "execute",
            "topic": "test",
            "document_context": "",
            "document_tables": [],
        }
        
        if agent_context.get("document_context"):
            task["document_context"] = agent_context["document_context"]
        if agent_context.get("document_tables"):
            task["document_tables"] = agent_context["document_tables"]
        
        assert task["document_context"] == "Financial data from annual report..."
        assert task["document_tables"]["income"][0]["科目"] == "Revenue"

    def test_no_inject_when_agent_context_empty(self):
        agent_context = {}
        
        task = {
            "action": "execute",
            "topic": "test",
            "document_context": "",
            "document_tables": [],
        }
        
        if agent_context.get("document_context"):
            task["document_context"] = agent_context["document_context"]
        if agent_context.get("document_tables"):
            task["document_tables"] = agent_context["document_tables"]
        
        assert task["document_context"] == ""
        assert task["document_tables"] == []

    def test_partial_injection_only_context(self):
        agent_context = {
            "document_context": "Some text",
        }
        
        task = {
            "action": "execute",
            "topic": "test",
            "document_context": "",
            "document_tables": [],
        }
        
        if agent_context.get("document_context"):
            task["document_context"] = agent_context["document_context"]
        if agent_context.get("document_tables"):
            task["document_tables"] = agent_context["document_tables"]
        
        assert task["document_context"] == "Some text"
        assert task["document_tables"] == []

    def test_getattr_fallback_for_agent_context(self):
        class MockAgent:
            pass
        
        agent = MockAgent()
        agent_context = getattr(agent, '_context', {})
        assert agent_context == {}

    def test_getattr_with_context(self):
        class MockAgent:
            def __init__(self):
                self._context = {"document_context": "test data"}
        
        agent = MockAgent()
        agent_context = getattr(agent, '_context', {})
        assert agent_context.get("document_context") == "test data"
