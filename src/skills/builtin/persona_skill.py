"""
PersonaSkill - Persona Generation Skill

Wraps PersonaGenerationAgent, provides Skill interface.
Used for batch generating virtual respondent personas.

Usage example:
    skill = PersonaSkill()
    result = await skill.execute(
        template="white-collar worker",
        count=10,
        context="New energy vehicle purchase intention survey"
    )
"""
from typing import Any, Dict, Optional

from src.skills.base import Skill, SkillConfig
from src.agents.fixed_agents.persona_generation_agent import PersonaGenerationAgent


class PersonaSkill(Skill):
    """
    Persona Generation Skill
    
    Features:
    - Batch generate virtual respondent personas
    - Support template-based crowd generation
    - Support stratified sampling
    - Optional LLM-enhanced backstory
    """
    
    def __init__(self, config: Optional[SkillConfig] = None):
        """Initialize PersonaSkill.
        
        Args:
            config: Skill configuration
        """
        super().__init__(config)
        self._agent: Optional[PersonaGenerationAgent] = None
    
    @property
    def name(self) -> str:
        return "persona_skill"
    
    @property
    def description(self) -> str:
        return "Batch generate virtual respondent personas, supporting templates, stratified sampling and LLM enhancement"
    
    def _get_agent(self) -> PersonaGenerationAgent:
        """Get or create PersonaGenerationAgent instance."""
        if self._agent is None:
            self._agent = PersonaGenerationAgent(
                agent_id="persona_skill_agent",
                name="Persona Generation Agent",
            )
        return self._agent
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute persona generation.
        
        Args:
            template: Template name (optional, default "white-collar worker")
            count: Number to generate (required, 1-1000)
            context: Survey context (optional)
            stratify_by: Stratification dimension list (optional)
            enhance_with_llm: Whether to use LLM enhancement (optional)
        
        Returns:
            Result dict containing success, personas, total_count
        """
        # Validate required parameters
        if "count" not in kwargs:
            return self._failure("Missing required parameter 'count'", "Parameter validation failed")
        
        count = kwargs.get("count")
        if not isinstance(count, int) or count < 1:
            return self._failure("'count' must be an integer greater than 0", "Parameter validation failed")
        
        try:
            agent = self._get_agent()
            
            # Execute generation
            result = await agent.execute(kwargs)
            
            if result["success"]:
                return self._success(
                    {
                        "personas": result.get("personas", []),
                        "total_count": result.get("total_count", 0),
                        "template_used": result.get("template_used", "white-collar worker"),
                    },
                    f"Successfully generated {result.get('total_count', 0)} personas"
                )
            else:
                return self._failure(
                    result.get("error", "unknown error"),
                    "Persona generation failed"
                )
                
        except Exception as e:
            return self._failure(str(e), "Persona generation exception")
    
    def get_available_templates(self) -> list:
        """Get available template list.
        
        Returns:
            List of template names
        """
        agent = self._get_agent()
        return agent.get_available_templates()