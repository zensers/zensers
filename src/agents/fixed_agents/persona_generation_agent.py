"""
Persona Generation Agent
========================

Generates virtual respondent personas, supporting templates and stratified sampling.

Responsibilities:
1. Batch generate personas based on templates
2. Support stratified sampling (by gender, age, etc.)
3. Optional LLM enhancement for richer background stories
4. Generate population samples aligned with research objectives

Input:
{
    "template": str,            # Template name (optional, default "White-Collar Professional")
    "count": int,               # Number to generate (required, 1-1000)
    "context": str,             # Research context (optional)
    "stratify_by": List[str],   # Stratification dimensions (optional)
    "enhance_with_llm": bool,   # Whether to use LLM enhancement (optional)
}

Output:
{
    "success": bool,
    "personas": List[Persona],  # List of personas
    "total_count": int,         # Total count
    "template_used": str,       # Template used
    "agent_id": str,
    "agent_name": str,
    "agent_version": str,
}
"""

from typing import Any, Dict, List, Optional
import asyncio
import random

from .base_fixed_agent import FixedAgent
from src.survey.services.persona_factory import Persona, PersonaFactory


class PersonaGenerationAgent(FixedAgent):
    """Persona Generation Agent.
    
    Responsible for generating virtual respondent personas, supporting 
    templating and stratified sampling. A core component of the survey 
    system's AI simulation mode.
    """
    
    agent_type = "persona_generation"
    version = "1.0.0"
    capabilities = [
        "Batch Persona Generation",
        "Template-Based Population Generation",
        "Stratified Sampling",
        "LLM-Enhanced Background Generation",
        "Context-Aware Generation",
    ]
    
    # List of available templates
    AVAILABLE_TEMPLATES = list(PersonaFactory.POPULATION_TEMPLATES.keys())
    
    def __init__(
        self,
        agent_id: str,
        name: str = "Persona Generation Agent",
        description: str = "Generates virtual respondent personas",
        storage_path: Optional[str] = None,
        llm_skill: Optional[Any] = None,
    ):
        """Initialize the Persona Generation Agent.
        
        Args:
            agent_id: Unique agent identifier
            name: Agent name
            description: Agent description
            storage_path: Storage path
            llm_skill: LLM Skill instance (optional, for enhanced generation)
        """
        super().__init__(agent_id, name=name, description=description, storage_path=storage_path)
        self.llm_skill = llm_skill
        self._persona_factory: Optional[PersonaFactory] = None
    
    def _get_persona_factory(self) -> PersonaFactory:
        """Get or create a PersonaFactory instance."""
        if self._persona_factory is None:
            self._persona_factory = PersonaFactory(llm_skill=self.llm_skill)
        return self._persona_factory
    
    def validate_input(self, task_input: Dict[str, Any]) -> tuple[bool, str]:
        """Validate input parameters."""
        valid, error = super().validate_input(task_input)
        if not valid:
            return valid, error
        
        # Check required fields
        if "count" not in task_input:
            return False, "Missing required field 'count'"
        
        # Validate count type
        count = task_input["count"]
        if not isinstance(count, int):
            return False, "'count' must be an integer"
        
        # Validate count range
        if count < 1:
            return False, "'count' must be greater than 0"
        
        if count > 1000:
            return False, "'count' cannot exceed 1000"
        
        # Validate optional field types
        if "template" in task_input and not isinstance(task_input["template"], str):
            return False, "'template' must be a string"
        
        if "context" in task_input and not isinstance(task_input["context"], str):
            return False, "'context' must be a string"
        
        if "stratify_by" in task_input and not isinstance(task_input["stratify_by"], list):
            return False, "'stratify_by' must be a list"
        
        if "enhance_with_llm" in task_input and not isinstance(task_input["enhance_with_llm"], bool):
            return False, "'enhance_with_llm' must be a boolean"
        
        return True, ""
    
    async def execute(self, task_input: Dict[str, Any]) -> Dict[str, Any]:
        """Execute persona generation (async).
        
        Args:
            task_input: {
                "template": Template name (optional),
                "count": Number to generate (required),
                "context": Research context (optional),
                "stratify_by": List of stratification dimensions (optional),
                "enhance_with_llm": Whether to use LLM enhancement (optional),
            }
            
        Returns:
            Generation result
        """
        # Publish start event
        await self.publish_event("persona_generation_started", {"count": task_input.get("count", 0)})
        
        # Parse input
        template = task_input.get("template", "White-Collar Professional")
        count = task_input["count"]
        context = task_input.get("context")
        stratify_by = task_input.get("stratify_by", [])
        enhance_with_llm = task_input.get("enhance_with_llm", False)
        
        # Get PersonaFactory
        factory = self._get_persona_factory()
        
        try:
            # Generate personas
            if stratify_by:
                # Stratified sampling generation
                personas = self._generate_stratified(
                    factory, template, count, stratify_by, context
                )
            else:
                # Regular batch generation
                personas = factory.generate_population(template, count, context)
            
            # LLM enhancement
            if enhance_with_llm and self.llm_skill:
                personas = await self._enhance_with_llm_async(personas, context)
            
            # Write to shared state
            await self.write_shared_state(f"agent.{self.agent_id}.last_generation", {
                "total_count": len(personas),
                "template": template,
            })
            
            # Publish completion event
            await self.publish_event("persona_generation_completed", {"total_count": len(personas)})
            
            return {
                "success": True,
                "personas": personas,
                "total_count": len(personas),
                "template_used": template,
            }
            
        except Exception as e:
            await self.publish_event("persona_generation_error", {"error": str(e)})
            return {
                "success": False,
                "error": str(e),
                "personas": [],
                "total_count": 0,
            }
    
    def _generate_stratified(
        self,
        factory: PersonaFactory,
        template: str,
        count: int,
        stratify_by: List[str],
        context: Optional[str]
    ) -> List[Persona]:
        """Stratified sampling generation.
        
        Args:
            factory: PersonaFactory instance
            template: Template name
            count: Total count
            stratify_by: List of stratification dimensions
            context: Context
            
        Returns:
            List of stratified-generated personas
        """
        personas = []
        
        # Handle gender stratification
        if "gender" in stratify_by:
            # Try to maintain gender balance
            male_count = count // 2
            female_count = count - male_count
            
            # Generate male personas
            male_personas = factory.generate_population(template, male_count, context)
            for p in male_personas:
                # Ensure male gender
                p.gender = "男"
                p.persona_id = f"persona_m_{len(personas)}"
                personas.append(p)
            
            # Generate female personas
            female_personas = factory.generate_population(template, female_count, context)
            for p in female_personas:
                # Ensure female gender
                p.gender = "女"
                p.persona_id = f"persona_f_{len(personas)}"
                personas.append(p)
        
        # Handle age stratification
        elif "age_group" in stratify_by:
            template_data = PersonaFactory.POPULATION_TEMPLATES.get(template, {})
            age_range = template_data.get("age_range", (25, 50))
            
            # Divide into three age groups
            age_min, age_max = age_range
            age_span = age_max - age_min
            group_size = count // 3
            
            for i in range(3):
                group_min = age_min + (age_span * i // 3)
                group_max = age_min + (age_span * (i + 1) // 3)
                
                group_personas = factory.generate_population(template, group_size, context)
                for p in group_personas:
                    p.age = random.randint(group_min, group_max)
                    p.persona_id = f"persona_{len(personas)}"
                    personas.append(p)
            
            # Fill remaining count
            remaining = count - len(personas)
            if remaining > 0:
                remaining_personas = factory.generate_population(template, remaining, context)
                personas.extend(remaining_personas)
        
        else:
            # No known stratification dimension, regular generation
            personas = factory.generate_population(template, count, context)
        
        return personas[:count]  # Ensure not exceeding target count
    
    def _enhance_with_llm_sync(
        self,
        personas: List[Persona],
        context: Optional[str]
    ) -> List[Persona]:
        """Synchronous LLM enhancement.
        
        Generates richer background stories for each persona.
        
        Args:
            personas: List of personas
            context: Research context
            
        Returns:
            Enhanced list of personas
        """
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Async enhancement
                enhanced = loop.run_until_complete(
                    self._enhance_with_llm_async(personas, context)
                )
                return enhanced
            finally:
                loop.close()
        except Exception:
            # LLM enhancement failed, return original personas
            return personas
    
    async def _enhance_with_llm_async(
        self,
        personas: List[Persona],
        context: Optional[str]
    ) -> List[Persona]:
        """Asynchronous LLM enhancement.
        
        Args:
            personas: List of personas
            context: Research context
            
        Returns:
            Enhanced list of personas
        """
        if not self.llm_skill:
            return personas
        
        for persona in personas:
            try:
                # Build enhancement prompt
                prompt = f"""
Generate a short background story for the following persona (50 words or less):

Name: {persona.name}
Age: {persona.age}
Occupation: {persona.occupation}
City: {persona.city}
Personality: {', '.join(persona.personality_traits[:2])}
"""
                
                if context:
                    prompt += f"\nResearch Topic: {context}"
                
                prompt += "\n\nBackground Story:"
                
                # Call LLM
                response = await self.llm_skill.execute(
                    prompt=prompt,
                    max_tokens=100,
                    temperature=0.8,
                )
                
                if response.get("success"):
                    enhanced_story = response.get("content", "").strip()
                    if enhanced_story:
                        persona.background_story = enhanced_story
                        
            except Exception:
                # Single enhancement failed, keep original story
                continue
        
        return personas
    
    async def execute_async(self, task_input: Dict[str, Any]) -> Dict[str, Any]:
        """Asynchronous persona generation execution.
        
        This is the async version of the execute method, suitable for async contexts.
        
        Args:
            task_input: Same as execute method
            
        Returns:
            Generation result
        """
        # Validate input
        valid, error = self.validate_input(task_input)
        if not valid:
            return {
                "success": False,
                "error": f"Input validation failed: {error}",
                "personas": [],
                "total_count": 0,
            }
        
        # Parse input
        template = task_input.get("template", "White-Collar Professional")
        count = task_input["count"]
        context = task_input.get("context")
        stratify_by = task_input.get("stratify_by", [])
        enhance_with_llm = task_input.get("enhance_with_llm", False)
        
        # Get PersonaFactory
        factory = self._get_persona_factory()
        
        try:
            # Generate personas
            if stratify_by:
                personas = self._generate_stratified(
                    factory, template, count, stratify_by, context
                )
            else:
                personas = factory.generate_population(template, count, context)
            
            # LLM enhancement (async version)
            if enhance_with_llm and self.llm_skill:
                personas = await self._enhance_with_llm_async(personas, context)
            
            return {
                "success": True,
                "personas": personas,
                "total_count": len(personas),
                "template_used": template,
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "personas": [],
                "total_count": 0,
            }
    
    def get_available_templates(self) -> List[str]:
        """Get list of available templates.
        
        Returns:
            List of template names
        """
        return self.AVAILABLE_TEMPLATES.copy()
    
    def reset(self) -> None:
        """Reset Agent state."""
        super().reset()
        # Optionally keep or reset persona_factory
        # self._persona_factory = None
