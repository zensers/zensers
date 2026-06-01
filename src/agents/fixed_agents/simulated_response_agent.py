"""
Simulated Response Agent
========================

Makes personas answer survey questions, generating simulated responses.

Responsibilities:
1. Receive survey and personas
2. Call SimulationEngine to execute simulation
3. Return simulation results

Input:
{
    "survey": dict,             # Survey data (Survey.to_dict() format)
    "personas": List[Persona],  # Persona list
    "parallel": bool,           # Whether to execute in parallel (optional, default True)
    "max_concurrent": int,      # Max concurrent executions (optional, default 10)
}

Output:
{
    "success": bool,
    "responses": List[dict],    # Simulated response list
    "total_count": int,         # Total response count
    "agent_id": str,
    "agent_name": str,
    "agent_version": str,
}
"""

from typing import Any, Dict, List, Optional
import asyncio

from .base_fixed_agent import FixedAgent
from src.core.agents.base import AgentState
from src.survey.models import Survey
from src.survey.services.simulation_engine import SimulationEngine
from src.survey.services.persona_factory import Persona


class SimulatedResponseAgent(FixedAgent):
    """Simulated Response Agent.
    
    Responsible for making personas answer surveys, generating simulated responses.
    Core component of the survey system's AI simulation mode.
    """
    
    agent_type = "simulated_response"
    version = "1.0.0"
    capabilities = [
        "Simulate survey responses",
        "Batch persona processing",
        "Concurrent response generation",
        "LLM-integrated responses",
        "Rule-based responses",
    ]
    
    def __init__(
        self,
        agent_id: str,
        name: str = "Simulated Response Agent",
        description: str = "Make personas answer surveys, generating simulated responses",
        storage_path: Optional[str] = None,
        llm_skill: Optional[Any] = None,
    ):
        """Initialize Simulated Response Agent.
        
        Args:
            agent_id: Agent unique identifier
            name: Agent name
            description: Agent description
            storage_path: Storage path
            llm_skill: LLM Skill instance (optional)
        """
        super().__init__(agent_id, name=name, description=description, storage_path=storage_path)
        self.llm_skill = llm_skill
        self._simulation_engine: Optional[SimulationEngine] = None
    
    def _get_simulation_engine(self) -> SimulationEngine:
        """Get or create SimulationEngine instance."""
        if self._simulation_engine is None:
            self._simulation_engine = SimulationEngine(llm_skill=self.llm_skill)
        return self._simulation_engine
    
    def validate_input(self, task_input: Dict[str, Any]) -> tuple[bool, str]:
        """Validate input parameters."""
        valid, error = super().validate_input(task_input)
        if not valid:
            return valid, error
        
        # Check required fields
        if "survey" not in task_input:
            return False, "Missing required 'survey' field"
        
        if "personas" not in task_input:
            return False, "Missing required 'personas' field"
        
        # Validate survey type
        survey = task_input["survey"]
        if not isinstance(survey, dict):
            return False, "'survey' must be a dictionary type (Survey.to_dict() format)"
        
        # Validate personas type
        personas = task_input["personas"]
        if not isinstance(personas, list):
            return False, "'personas' must be a list type"
        
        # Validate elements in personas
        for i, persona in enumerate(personas):
            if not isinstance(persona, Persona):
                return False, f"'personas[{i}]' must be of Persona type"
        
        return True, ""
    
    async def execute(self, task_input: Dict[str, Any]) -> Dict[str, Any]:
        """Execute simulated response (async).
        
        Args:
            task_input: {
                "survey": Survey.to_dict() format survey data,
                "personas": List of Persona objects,
                "parallel": Whether to execute in parallel (optional),
                "max_concurrent": Max concurrent executions (optional),
            }
            
        Returns:
            Simulation results
        """
        # Publish start event
        await self.publish_event("simulation_started", {"persona_count": len(task_input.get("personas", []))})
        
        # Parse input
        survey_dict = task_input["survey"]
        personas: List[Persona] = task_input["personas"]
        parallel = task_input.get("parallel", True)
        max_concurrent = task_input.get("max_concurrent", 10)
        
        # Reconstruct Survey object
        survey = Survey.from_dict(survey_dict)
        
        # Get SimulationEngine
        engine = self._get_simulation_engine()
        
        # Execute simulation (already async)
        try:
            responses = await engine.simulate_survey(
                personas=personas,
                survey=survey,
                parallel=parallel,
                max_concurrent=max_concurrent,
            )
            
            # Convert responses to dict format
            response_dicts = [r.to_dict() for r in responses]
            
            # Write to shared state
            await self.write_shared_state(f"agent.{self.agent_id}.last_simulation", {
                "total_count": len(response_dicts),
            })
            
            # Publish completion event
            await self.publish_event("simulation_completed", {"total_count": len(response_dicts)})
            
            return {
                "success": True,
                "responses": response_dicts,
                "total_count": len(response_dicts),
            }
            
        except Exception as e:
            await self.publish_event("simulation_error", {"error": str(e)})
            return {
                "success": False,
                "error": str(e),
                "responses": [],
                "total_count": 0,
            }
    
    def reset(self) -> None:
        """Reset Agent state."""
        super().reset()
        # Optionally keep or reset simulation_engine
        # self._simulation_engine = None
