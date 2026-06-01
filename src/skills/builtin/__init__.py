"""
Built-in Skills Module

Provides pre-built Skills, including:
1. LangChain Tools integration (search, academic, encyclopedia, analysis)
2. Custom basic Skills (document, file, LLM, HTTP)
3. Survey Skills (persona generation, simulation response, survey management)

Usage examples:
    from src.skills.builtin import get_research_tools
    
    # Get commonly used research Tools
    tools = get_research_tools()
    
    # Execute search
    result = await tools["web_search"].execute(query="AI market size")
    
    # Use survey Skills
    from src.skills.builtin import PersonaSkill, SimulationSkill, SurveySkill
    
    persona_skill = PersonaSkill()
    result = await persona_skill.execute(template="frontline white-collar", count=10)
    
    # Use survey management Skill
    survey_skill = SurveySkill()
    result = await survey_skill.execute(action="create", title="Market Survey", questions=[...])
"""

from .langchain_tools import (
    get_research_tools,
    RESEARCH_TOOLS,
    create_tavily_search_skill,
    create_arxiv_search_skill,
    create_wikipedia_search_skill,
    create_python_repl_skill,
)

from .persona_skill import PersonaSkill
from .simulation_skill import SimulationSkill
from .survey_skill import SurveySkill

__all__ = [
    "get_research_tools",
    "RESEARCH_TOOLS",
    "create_tavily_search_skill",
    "create_arxiv_search_skill",
    "create_wikipedia_search_skill",
    "create_python_repl_skill",
    "PersonaSkill",
    "SimulationSkill",
    "SurveySkill",
]
