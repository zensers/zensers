"""
SimulationSkill - Survey Simulation Skill

Wraps SimulatedResponseAgent, provides Skill interface.
Used to have personas answer survey questions, generating simulated responses.

Usage example:
    skill = SimulationSkill()
    result = await skill.execute(
        survey=survey.to_dict(),
        personas=personas,
        parallel=True
    )
"""
from typing import Any, Dict, Optional

from src.skills.base import Skill, SkillConfig
from src.agents.fixed_agents.simulated_response_agent import SimulatedResponseAgent


class SimulationSkill(Skill):
    """
    Survey Simulation Skill
    
    Features:
    - Have personas answer surveys
    - Support batch simulation
    - Support parallel execution
    - Support LLM-generated responses
    """
    
    def __init__(self, config: Optional[SkillConfig] = None):
        """Initialize SimulationSkill.
        
        Args:
            config: Skill configuration
        """
        super().__init__(config)
        self._agent: Optional[SimulatedResponseAgent] = None
    
    @property
    def name(self) -> str:
        return "simulation_skill"
    
    @property
    def description(self) -> str:
        return "Have personas answer surveys, generate simulated responses, support parallel execution and LLM generation"
    
    def _get_agent(self) -> SimulatedResponseAgent:
        """Get or create SimulatedResponseAgent instance."""
        if self._agent is None:
            self._agent = SimulatedResponseAgent(
                agent_id="simulation_skill_agent",
                name="Simulation Response Agent",
            )
        return self._agent
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute survey simulation.
        
        Args:
            survey: Survey data (Survey.to_dict() format, required)
            personas: List of personas (required)
            parallel: Whether to execute in parallel (optional, default True)
            max_concurrent: Maximum concurrency (optional, default 10)
        
        Returns:
            Result dict containing success, responses, total_count
        """
        # Validate required parameters
        if "survey" not in kwargs:
            return self._failure("Missing required parameter 'survey'", "Parameter validation failed")
        
        if "personas" not in kwargs:
            return self._failure("Missing required parameter 'personas'", "Parameter validation failed")
        
        survey = kwargs.get("survey")
        if not isinstance(survey, dict):
            return self._failure("'survey' must be a dict type", "Parameter validation failed")
        
        personas = kwargs.get("personas")
        if not isinstance(personas, list):
            return self._failure("'personas' must be a list type", "Parameter validation failed")
        
        try:
            agent = self._get_agent()
            
            # Use async execution method
            result = await agent.execute(kwargs)
            
            if result["success"]:
                return self._success(
                    {
                        "responses": result.get("responses", []),
                        "total_count": result.get("total_count", 0),
                    },
                    f"Successfully generated {result.get('total_count', 0)} simulated responses"
                )
            else:
                return self._failure(
                    result.get("error", "unknown error"),
                    "Survey simulation failed"
                )
                
        except Exception as e:
            return self._failure(str(e), "Survey simulation exception")