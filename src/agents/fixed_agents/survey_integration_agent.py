"""
SurveyIntegrationAgent - Survey Integration Agent

Coordinates the complete survey workflow, connecting all components.

Features:
1. Third-party platform survey distribution
2. AI Agent simulated survey
3. Survey document generation
4. Data persistence storage
5. Task recovery support

Workflow Types (v2.0 simplified):
- third_party: Third-party platform distribution (create → review → distribute → collect → analyze)
- ai_simulation: AI simulated survey (create → review → generate personas → simulate responses → analyze)

Input:
{
    "workflow": str,              # Workflow type: "third_party" | "ai_simulation"
    "topic": str,                 # Survey topic
    "questions": List[Dict],      # Question list (optional, auto-generated if not provided)
    "target_count": int,          # Target sample count
    "backend": str,               # Third-party platform (third_party mode): "api_tencent" | "api_wenjuanxing"
    "persona_template": str,      # Persona template (ai_simulation mode): "first_tier_white_collar" | "second_tier_family_users"
    "parent_task_id": str,        # Associated master research task ID
}

Output:
{
    "success": bool,
    "survey_id": str,
    "mode": str,                  # "third_party" | "ai_simulation"
    "survey": Dict,               # Survey
    "responses": List[Dict],      # Responses
    "analysis": Dict,             # Analysis results
    "survey_document": Dict,      # Survey document info
    "steps": List[Dict],          # Execution steps
}
"""
from typing import Any, Dict, List, Optional
import asyncio
import uuid
import logging
from datetime import datetime
from pathlib import Path

from src.agents.fixed_agents.base_fixed_agent import FixedAgent

logger = logging.getLogger(__name__)


class SurveyIntegrationAgent(FixedAgent):
    """Survey Integration Agent.
    
    Coordinates the complete survey workflow.
    
    v2.0 simplified to two core modes:
    - third_party: Third-party platform distribution
    - ai_simulation: AI Agent simulation
    """
    
    agent_type = "survey_integration"
    version = "2.0.0"
    capabilities = [
        "Third-party platform survey distribution",
        "AI Agent simulated survey",
        "Survey document generation",
        "Data persistence storage",
        "Task recovery support",
    ]
    
    # Workflow types (v2.0 simplified)
    WORKFLOW_TYPES = {
        "third_party": "Third-party platform survey distribution",
        "ai_simulation": "AI Agent simulated survey",
        # Legacy interface compatibility (internally mapped to new workflows)
        "full_survey": "Full survey workflow (legacy)",
        "quick_survey": "Quick survey workflow (legacy)",
        "optimized_survey": "Optimized survey workflow (legacy)",
    }
    
    def __init__(
        self,
        agent_id: str,
        name: str = "Survey Integration Agent",
        description: str = "Coordinate complete survey workflow",
        storage_path: Optional[str] = None,
        llm_skill: Optional[Any] = None,
        connection_manager: Optional[Any] = None,
    ):
        """Initialize Survey Integration Agent."""
        super().__init__(agent_id, name=name, description=description, storage_path=storage_path)
        self.llm_skill = llm_skill
        self.connection_manager = connection_manager
        self._optimization_agent = None
        self._analysis_agent = None
        self._persona_agent = None
        self._simulation_agent = None
        self._stores = None  # Lazy initialization
    
    def _get_stores(self):
        """Lazy initialize storage layer"""
        if self._stores is None:
            from src.survey.stores import (
                SurveyTaskStore,
                SurveyResponseStore,
                SurveyPersonaStore,
                SurveyCheckpointStore,
            )
            from src.core.storage import ConnectionManager
            from pathlib import Path
            
            # If no connection_manager provided, create a default one
            conn_mgr = self.connection_manager
            if conn_mgr is None:
                # Use default data directory
                default_base_path = Path("data")
                default_base_path.mkdir(parents=True, exist_ok=True)
                conn_mgr = ConnectionManager(default_base_path)
                self.connection_manager = conn_mgr
            
            self._stores = {
                "task": SurveyTaskStore(conn_mgr),
                "response": SurveyResponseStore(conn_mgr),
                "persona": SurveyPersonaStore(conn_mgr),
                "checkpoint": SurveyCheckpointStore(conn_mgr),
            }
        return self._stores
    
    def validate_input(self, task_input: Dict[str, Any]) -> tuple[bool, str]:
        """Validate input parameters."""
        valid, error = super().validate_input(task_input)
        if not valid:
            return valid, error
        
        workflow = task_input.get("workflow")
        if not workflow:
            return False, "Missing required 'workflow' field"
        
        if workflow not in self.WORKFLOW_TYPES:
            return False, f"Unknown workflow type: {workflow}, supported: {list(self.WORKFLOW_TYPES.keys())}"
        
        return True, ""
    
    async def execute(self, task_input: Dict[str, Any]) -> Dict[str, Any]:
        """Execute workflow (async).
        
        Dispatches to corresponding handler based on workflow type.
        """
        workflow = task_input.get("workflow")
        
        # Handle legacy workflow types
        workflow = self._normalize_workflow(workflow)
        
        # Publish start event
        await self.publish_event("workflow_started", {"workflow": workflow})
        
        # Create task record
        survey_id = f"survey_{uuid.uuid4().hex[:8]}"
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        
        try:
            if workflow == "third_party":
                result = await self._third_party_workflow(task_input, survey_id, task_id)
            elif workflow == "ai_simulation":
                result = await self._ai_simulation_workflow(task_input, survey_id, task_id)
            else:
                result = {
                    "success": False,
                    "error": f"Unimplemented workflow: {workflow}",
                }
            
            # Publish completion event
            await self.publish_event("workflow_completed", {"success": result.get("success", False)})
            
            return result
            
        except Exception as e:
            logger.error(f"Survey workflow failed: {e}")
            await self.publish_event("workflow_failed", {"error": str(e)})
            return {
                "success": False,
                "error": str(e),
                "survey_id": survey_id,
            }
    
    def _normalize_workflow(self, workflow: Optional[str]) -> str:
        """Normalize workflow type (legacy interface compatibility)"""
        if not workflow:
            return "ai_simulation"
        # Map legacy interfaces to new workflows
        legacy_mapping = {
            "full_survey": "third_party",
            "quick_survey": "ai_simulation",
            "optimized_survey": "ai_simulation",  # Default to AI simulation
        }
        return legacy_mapping.get(workflow, workflow)
    
    # ========== Core workflow implementations ==========
    
    async def _third_party_workflow(
        self,
        task_input: Dict[str, Any],
        survey_id: str,
        task_id: str,
    ) -> Dict[str, Any]:
        """
        Third-party platform distribution workflow
        
        Process:
        1. Create survey
        2. Generate survey document
        3. Distribute to third-party platform
        4. Wait for collection (async)
        5. Retrieve results and analyze
        """
        topic = task_input.get("topic", "Market Research")
        questions = task_input.get("questions", [])
        target_count = task_input.get("target_count", 100)
        backend_type = task_input.get("backend", "api_tencent")
        parent_task_id = task_input.get("parent_task_id")
        
        result = {
            "workflow": "third_party",
            "mode": "third_party",
            "survey_id": survey_id,
            "task_id": task_id,
            "steps": [],
        }
        
        try:
            # Step 1: Create survey (auto-generate questions if not provided)
            if not questions:
                questions = await self._auto_generate_questions(topic)
                result["questions_auto_generated"] = True
            
            survey = await self._create_survey(topic, questions)
            survey["survey_id"] = survey_id
            result["survey"] = survey
            result["steps"].append({"step": "create_survey", "status": "completed"})
            
            # Step 2: Generate survey document
            docx_path = await self._generate_questionnaire_document(survey)
            result["survey_document"] = {
                "path": docx_path,
                "generated_at": datetime.now().isoformat(),
            }
            result["steps"].append({"step": "generate_document", "status": "completed"})
            
            # Step 3: Distribute to third-party platform
            distribution = await self._distribute_to_platform(survey, backend_type, target_count)
            result["distribution"] = distribution
            result["steps"].append({"step": "distribute", "status": "completed"})
            
            # Step 4: Save task to database (ensure storage layer is initialized)
            stores = self._get_stores()  # This automatically initializes connection_manager
            await self._save_task_to_db(
                task_id=task_id,
                survey_id=survey_id,
                topic=topic,
                mode="third_party",
                backend_type=backend_type,
                questions=questions,
                target_count=target_count,
                parent_task_id=parent_task_id,
                external_id=distribution.get("external_id"),
                share_url=distribution.get("share_url"),
            )
            result["steps"].append({"step": "save_task", "status": "completed"})
            
            # Step 5: Create checkpoint
            await self._create_checkpoint(task_id, "distributed", 1, 5)
            result["steps"].append({"step": "checkpoint", "status": "completed"})
            
            result["success"] = True
            result["status"] = "waiting"  # Waiting for third-party platform to collect data
            
        except Exception as e:
            logger.error(f"Third party workflow failed: {e}")
            result["success"] = False
            result["error"] = str(e)
            result["steps"].append({"step": "error", "message": str(e)})
        
        return result
    
    async def _ai_simulation_workflow(
        self,
        task_input: Dict[str, Any],
        survey_id: str,
        task_id: str,
    ) -> Dict[str, Any]:
        """
        AI simulation survey workflow
        
        Process:
        1. Create survey
        2. Generate survey document
        3. Generate AI personas
        4. AI simulate responses
        5. Analyze results
        6. Store to database
        """
        topic = task_input.get("topic", "Market Research")
        questions = task_input.get("questions", [])
        target_count = task_input.get("target_count", 100)
        persona_template = task_input.get("persona_template", "一线白领")
        parent_task_id = task_input.get("parent_task_id")
        
        result = {
            "workflow": "ai_simulation",
            "mode": "ai_simulation",
            "survey_id": survey_id,
            "task_id": task_id,
            "steps": [],
        }
        
        try:
            # Step 1: Create survey
            if not questions:
                questions = await self._auto_generate_questions(topic)
                result["questions_auto_generated"] = True
            
            survey = await self._create_survey(topic, questions)
            survey["survey_id"] = survey_id
            result["survey"] = survey
            result["steps"].append({"step": "create_survey", "status": "completed"})
            
            # Step 2: Generate survey document
            docx_path = await self._generate_questionnaire_document(survey)
            result["survey_document"] = {
                "path": docx_path,
                "generated_at": datetime.now().isoformat(),
            }
            result["steps"].append({"step": "generate_document", "status": "completed"})
            
            # Step 3: Save task to database (ensure storage layer is initialized)
            stores = self._get_stores()  # This automatically initializes connection_manager
            await self._save_task_to_db(
                task_id=task_id,
                survey_id=survey_id,
                topic=topic,
                mode="ai_simulation",
                backend_type="ai_simulation",
                questions=questions,
                target_count=target_count,
                parent_task_id=parent_task_id,
            )
            result["steps"].append({"step": "save_task", "status": "completed"})
            
            # Step 4: Generate AI personas
            personas = await self._generate_personas(persona_template, target_count)
            result["personas_count"] = len(personas)
            result["steps"].append({"step": "generate_personas", "status": "completed"})
            
            # Create checkpoint
            await self._create_checkpoint(task_id, "personas_generated", 2, 5, {
                "personas_count": len(personas),
            })
            
            # Step 5: AI simulate responses
            responses = await self._simulate_responses(survey, personas)
            result["responses"] = responses
            result["responses_count"] = len(responses)
            result["steps"].append({"step": "simulate_responses", "status": "completed"})
            
            # Create checkpoint
            await self._create_checkpoint(task_id, "responses_collected", 3, 5, {
                "responses_count": len(responses),
            })
            
            # Step 6: Store responses to database
            await self._save_responses_to_db(task_id, survey_id, responses, personas)
            result["steps"].append({"step": "save_responses", "status": "completed"})
            
            # Step 7: Analyze results
            analysis = await self._analyze_results(responses, questions)
            result["analysis"] = analysis
            result["steps"].append({"step": "analyze_results", "status": "completed"})
            
            # Step 8: Update task status to completed
            if self.connection_manager:
                await self._update_task_status(task_id, "completed")
            result["steps"].append({"step": "complete_task", "status": "completed"})
            
            result["success"] = True
            result["status"] = "completed"
            
        except Exception as e:
            logger.error(f"AI simulation workflow failed: {e}")
            result["success"] = False
            result["error"] = str(e)
            result["steps"].append({"step": "error", "message": str(e)})
            
            # Update task status to failed
            if self.connection_manager:
                await self._update_task_status(task_id, "failed", str(e))
        
        return result
    
    # ========== Legacy workflow compatibility ==========
    
    async def _full_survey_workflow(self, task_input: Dict[str, Any]) -> Dict[str, Any]:
        """Full survey workflow (legacy interface)"""
        # Map to new third-party workflow
        return await self._third_party_workflow(
            task_input,
            f"survey_{uuid.uuid4().hex[:8]}",
            f"task_{uuid.uuid4().hex[:8]}",
        )
    
    async def _quick_survey_workflow(self, task_input: Dict[str, Any]) -> Dict[str, Any]:
        """Quick survey workflow (legacy interface)"""
        # Map to new AI simulation workflow
        return await self._ai_simulation_workflow(
            task_input,
            f"survey_{uuid.uuid4().hex[:8]}",
            f"task_{uuid.uuid4().hex[:8]}",
        )
    
    async def _optimized_survey_workflow(self, task_input: Dict[str, Any]) -> Dict[str, Any]:
        """Optimized survey workflow (legacy interface)"""
        # Map to new AI simulation workflow
        return await self._ai_simulation_workflow(
            task_input,
            f"survey_{uuid.uuid4().hex[:8]}",
            f"task_{uuid.uuid4().hex[:8]}",
        )
    
    # ========== Helper methods ==========
    
    async def _create_survey(self, title: str, questions: List[Dict]) -> Dict[str, Any]:
        """Create survey."""
        from datetime import datetime
        
        survey_id = f"survey_{uuid.uuid4().hex[:8]}"
        
        # Ensure question format is correct
        formatted_questions = []
        for i, q in enumerate(questions):
            if isinstance(q, dict):
                # Format options
                options = None
                if q.get("options"):
                    options = []
                    for j, opt in enumerate(q["options"]):
                        if isinstance(opt, dict):
                            options.append({
                                "option_id": opt.get("option_id", f"opt_{i}_{j}"),
                                "text": opt.get("text", ""),
                                "value": opt.get("value"),
                            })
                        elif isinstance(opt, str):
                            options.append({
                                "option_id": f"opt_{i}_{j}",
                                "text": opt,
                                "value": None,
                            })
                
                formatted_questions.append({
                    "question_id": q.get("question_id", q.get("id", f"q{i}")),
                    "text": q.get("text", ""),
                    "question_type": q.get("question_type", q.get("type", "single_choice")),
                    "options": options,
                    "required": q.get("required", True),
                    "description": q.get("description"),
                })
        
        return {
            "survey_id": survey_id,
            "title": title,
            "questions": formatted_questions,
            "description": "",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
    
    async def _optimize_survey(self, questions: List[Dict]) -> Dict[str, Any]:
        """Optimize survey."""
        if self._optimization_agent is None:
            from src.agents.fixed_agents.survey_optimization_agent import SurveyOptimizationAgent
            self._optimization_agent = SurveyOptimizationAgent(
                agent_id="int_opt_agent",
                llm_skill=self.llm_skill
            )
        
        # Convert question format
        formatted_questions = []
        for i, q in enumerate(questions):
            if isinstance(q, dict):
                formatted_questions.append({
                    "question_id": q.get("question_id", q.get("id", f"q{i}")),
                    "text": q.get("text", ""),
                    "question_type": q.get("question_type", q.get("type", "single_choice")),
                    "options": q.get("options", []),
                })
        
        return await self._optimization_agent.execute_async({
            "questions": formatted_questions,
            "optimization_goals": ["clarity", "completeness"]
        })
    
    async def _distribute_survey(
        self, 
        survey: Dict, 
        target_count: int,
        mode: str
    ) -> Dict[str, Any]:
        """Distribute survey."""
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        
        return {
            "task_id": task_id,
            "survey_id": survey.get("survey_id"),
            "target_count": target_count,
            "mode": mode,
            "status": "active",
        }
    
    async def _get_responses(self, task: Dict) -> List[Dict]:
        """Get responses."""
        # Simplified implementation - return mock data
        return []
    
    async def _ai_simulate(self, survey: Dict, target_count: int) -> List[Dict]:
        """AI simulate responses."""
        from src.agents.fixed_agents.persona_generation_agent import PersonaGenerationAgent
        from src.agents.fixed_agents.simulated_response_agent import SimulatedResponseAgent
        
        # Generate personas
        if self._persona_agent is None:
            self._persona_agent = PersonaGenerationAgent(
                agent_id="int_persona_agent",
                llm_skill=self.llm_skill
            )
        
        persona_result = await self._persona_agent.execute_async({
            "template": "first_tier_white_collar",
            "count": target_count
        })
        
        if not persona_result.get("success"):
            return []
        
        personas = persona_result.get("personas", [])
        
        # Simulate responses
        if self._simulation_agent is None:
            self._simulation_agent = SimulatedResponseAgent(
                agent_id="int_sim_agent",
                llm_skill=self.llm_skill
            )
        
        simulation_result = await self._simulation_agent.execute({
            "survey": survey,
            "personas": personas,
            "parallel": True
        })
        
        return simulation_result.get("responses", [])
    
    async def _analyze_results(
        self, 
        responses: List[Dict], 
        questions: List[Dict]
    ) -> Dict[str, Any]:
        """Analyze results."""
        if self._analysis_agent is None:
            from src.agents.fixed_agents.survey_analysis_agent import SurveyAnalysisAgent
            self._analysis_agent = SurveyAnalysisAgent(
                agent_id="int_analysis_agent",
                llm_skill=self.llm_skill
            )
            # Fix breakpoint #3-4: Inject communication capabilities
            if hasattr(self, '_message_bus') and self._message_bus:
                self._analysis_agent.set_message_bus(self._message_bus)
            if hasattr(self, '_shared_memory') and self._shared_memory:
                self._analysis_agent.set_shared_memory(self._shared_memory)
        
        return await self._analysis_agent.execute({
            "responses": responses,
            "questions": questions,
            "analysis_type": "full",
            "generate_charts": True,  # Enable chart generation
            "chart_output_dir": str(Path(self.storage_path) / "charts") if self.storage_path else None,
        })
    
    async def _auto_generate_questions(self, topic: str) -> List[Dict]:
        """Auto-generate questions."""
        # Generate basic question template based on topic
        base_questions = [
            {
                "question_id": "q1",
                "text": f"What is your overall view on {topic}?",
                "question_type": "single_choice",
                "options": [
                    {"option_id": "opt1", "text": "Very Satisfied", "value": 5},
                    {"option_id": "opt2", "text": "Satisfied", "value": 4},
                    {"option_id": "opt3", "text": "Neutral", "value": 3},
                    {"option_id": "opt4", "text": "Dissatisfied", "value": 2},
                    {"option_id": "opt5", "text": "Very Dissatisfied", "value": 1}
                ]
            },
            {
                "question_id": "q2",
                "text": f"How interested are you in {topic}? (1-10 scale)",
                "question_type": "scale",
                "options": None
            },
            {
                "question_id": "q3",
                "text": f"Please briefly describe your suggestions for {topic}",
                "question_type": "open_ended",
                "options": None
            }
        ]
        
        return base_questions
    
    # ========== Database storage methods ==========
    
    async def _save_task_to_db(
        self,
        task_id: str,
        survey_id: str,
        topic: str,
        mode: str,
        backend_type: str,
        questions: List[Dict],
        target_count: int,
        parent_task_id: Optional[str] = None,
        external_id: Optional[str] = None,
        share_url: Optional[str] = None,
    ) -> None:
        """Save task to database"""
        import json
        
        try:
            stores = self._get_stores()
            task_store = stores["task"]
            
            task_data = {
                "task_id": task_id,
                "survey_id": survey_id,
                "topic": topic,
                "mode": mode,
                "backend_type": backend_type,
                "status": "active",
                "questions": json.dumps(questions, ensure_ascii=False),
                "target_count": target_count,
                "collected_count": 0,
                "valid_count": 0,
                "created_at": datetime.now().isoformat(),
                "parent_task_id": parent_task_id,
                "external_id": external_id,
                "share_url": share_url,
            }
            
            task_store.add(task_data)
            logger.info(f"Task saved to database: {task_id}")
            
        except Exception as e:
            logger.error(f"Failed to save task to database: {e}")
    
    async def _save_responses_to_db(
        self,
        task_id: str,
        survey_id: str,
        responses: List[Dict],
        personas: List[Dict],
    ) -> None:
        """Save responses and personas to database"""
        import json
        
        try:
            stores = self._get_stores()
            response_store = stores["response"]
            persona_store = stores["persona"]
            
            # Store personas
            persona_map = {}
            for persona in personas:
                # Handle Persona object or dict
                if hasattr(persona, '__dict__'):
                    persona_dict = persona.__dict__
                elif isinstance(persona, dict):
                    persona_dict = persona
                else:
                    logger.warning(f"Unknown persona type: {type(persona)}")
                    continue
                
                # Generate unique persona_id (with task_id prefix to avoid conflicts)
                existing_id = persona_dict.get("persona_id")
                if existing_id and not existing_id.startswith(task_id):
                    persona_id = f"{task_id}_{existing_id}"
                elif existing_id:
                    persona_id = existing_id
                else:
                    persona_id = f"{task_id}_persona_{uuid.uuid4().hex[:8]}"
                
                persona_map[persona_dict.get("name", persona_id)] = persona_id
                
                persona_data = {
                    "persona_id": persona_id,
                    "task_id": task_id,
                    "name": persona_dict.get("name", ""),
                    "age": persona_dict.get("age"),
                    "gender": persona_dict.get("gender", ""),
                    "city": persona_dict.get("city", ""),
                    "occupation": persona_dict.get("occupation", ""),
                    "income": persona_dict.get("income", ""),
                    "education": persona_dict.get("education", ""),
                    "personality_traits": json.dumps(persona_dict.get("personality_traits", []), ensure_ascii=False),
                    "interests": json.dumps(persona_dict.get("interests", []), ensure_ascii=False),
                    "value_preferences": json.dumps(persona_dict.get("values", []), ensure_ascii=False),
                    "decision_style": persona_dict.get("decision_style", ""),
                    "background_story": persona_dict.get("background_story", ""),
                    "created_at": datetime.now().isoformat(),
                }
                persona_store.add(persona_data)
            
            # Store responses
            for i, response in enumerate(responses):
                response_id = response.get("response_id", f"resp_{task_id}_{i}")
                respondent_id = response.get("respondent_id", "")
                
                response_data = {
                    "response_id": response_id,
                    "task_id": task_id,
                    "survey_id": survey_id,
                    "respondent_id": respondent_id,
                    "persona_id": persona_map.get(respondent_id, ""),
                    "answers": json.dumps(response.get("answers", {}), ensure_ascii=False),
                    "quality_score": response.get("quality_score", 1.0),
                    "is_valid": 1 if response.get("is_valid", True) else 0,
                    "duration_seconds": response.get("duration_seconds", 0),
                    "source": "ai_simulation",
                    "completed_at": response.get("completed_at", datetime.now().isoformat()),
                }
                response_store.add(response_data)
            
            logger.info(f"Saved {len(responses)} responses and {len(personas)} personas to database")
            
        except Exception as e:
            logger.error(f"Failed to save responses to database: {e}")
    
    async def _update_task_status(
        self,
        task_id: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> None:
        """Update task status"""
        try:
            stores = self._get_stores()
            task_store = stores["task"]
            
            update_data = {
                "status": status,
            }
            if status == "completed":
                update_data["completed_at"] = datetime.now().isoformat()
            if error_message:
                update_data["error_message"] = error_message
            
            task_store.update(task_id, update_data)
            logger.info(f"Task status updated: {task_id} -> {status}")
            
        except Exception as e:
            logger.error(f"Failed to update task status: {e}")
    
    async def _create_checkpoint(
        self,
        task_id: str,
        step_name: str,
        step_index: int,
        total_steps: int,
        snapshot_data: Optional[Dict] = None,
    ) -> None:
        """Create checkpoint"""
        import json
        
        try:
            stores = self._get_stores()
            checkpoint_store = stores["checkpoint"]
            
            checkpoint_id = f"cp_{uuid.uuid4().hex[:8]}"
            
            checkpoint_data = {
                "checkpoint_id": checkpoint_id,
                "task_id": task_id,
                "step_name": step_name,
                "step_index": step_index,
                "total_steps": total_steps,
                "status": "completed",
                "progress_percent": (step_index / total_steps) * 100,
                "snapshot_data": json.dumps(snapshot_data or {}, ensure_ascii=False),
                "created_at": datetime.now().isoformat(),
            }
            
            checkpoint_store.add(checkpoint_data)
            
            # Update task's checkpoint reference
            stores["task"].update(task_id, {
                "checkpoint_id": checkpoint_id,
                "last_checkpoint_at": datetime.now().isoformat(),
            })
            
            logger.info(f"Checkpoint created: {checkpoint_id} for task {task_id}")
            
        except Exception as e:
            logger.error(f"Failed to create checkpoint: {e}")
    
    # ========== Document generation methods ==========
    
    async def _generate_questionnaire_document(self, survey: Dict) -> str:
        """Generate survey Word document"""
        try:
            from pathlib import Path
            
            # P0-5 fix: Use output path from config
            try:
                from src.config.system import SystemSettings
                settings = SystemSettings.from_yaml() if hasattr(SystemSettings, 'from_yaml') else SystemSettings()
                base_output_dir = Path(settings.paths.report_output_dir) / "survey"
            except Exception:
                base_output_dir = Path("output/reports/survey")
            
            output_dir = Path(self.storage_path) / survey["survey_id"] if self.storage_path else base_output_dir / survey["survey_id"]
            output_dir.mkdir(parents=True, exist_ok=True)
            
            docx_path = output_dir / "questionnaire.docx"
            
            # Use document generator
            try:
                from src.content.content_orchestrator import ContentOrchestrator
                from src.converters.html_to_word import HTMLToWordConverter
                
                # Prepare template variables
                questions = survey.get("questions", [])
                required_count = sum(1 for q in questions if q.get("required", True))
                
                template_vars = {
                    "title": survey.get("title", "Survey Questionnaire"),
                    "created_at": datetime.now().strftime("%Y-%m-%d"),
                    "topic": survey.get("topic", ""),
                    "target_count": survey.get("target_count", 100),
                    "total_questions": len(questions),
                    "required_count": required_count,
                    "estimated_minutes": len(questions) * 2 // 3 + 1,  # Estimated time
                    "survey_id": survey.get("survey_id", ""),
                    "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "questions": [
                        {
                            "index": i + 1,
                            "id": q.get("question_id", f"q{i}"),
                            "text": q.get("text", ""),
                            "type": self._get_question_type_label(q.get("question_type", "single_choice")),
                            "options": q.get("options") or [],
                            "required": q.get("required", True),
                        }
                        for i, q in enumerate(questions)
                    ],
                }
                
                # Generate HTML (transform_to_html is a sync method)
                orchestrator = ContentOrchestrator()
                html = orchestrator.transform_to_html(
                    research_result=template_vars,
                    output_format="docx",
                    template_name="questionnaire_word",
                )
                
                # Convert to Word
                converter = HTMLToWordConverter()
                converter.convert(html, str(docx_path))
                
                logger.info(f"Questionnaire document generated: {docx_path}")
                return str(docx_path)
                
            except ImportError:
                # Fallback: Generate simple text file
                logger.warning("Document generation dependencies not available, creating text file")
                return await self._generate_questionnaire_text(survey, docx_path)
            
        except Exception as e:
            logger.error(f"Failed to generate questionnaire document: {e}")
            return ""
    
    async def _generate_questionnaire_text(self, survey: Dict, output_path: Path) -> str:
        """Generate survey text file (fallback)"""
        txt_path = output_path.with_suffix(".txt")
        
        lines = [
            f"Survey Title: {survey.get('title', 'Survey Questionnaire')}",
            f"Created: {datetime.now().strftime('%Y-%m-%d')}",
            f"Number of Questions: {len(survey.get('questions', []))}",
            "",
            "=" * 50,
            "",
        ]
        
        for i, q in enumerate(survey.get("questions", []), 1):
            lines.append(f"Question {i}: {q.get('text', '')}")
            lines.append(f"Type: {self._get_question_type_label(q.get('question_type', 'single_choice'))}")
            
            if q.get("options"):
                lines.append("Options:")
                for opt in q["options"]:
                    if isinstance(opt, dict):
                        lines.append(f"  - {opt.get('text', '')}")
                    else:
                        lines.append(f"  - {opt}")
            
            lines.append("")
        
        txt_path.write_text("\n".join(lines), encoding="utf-8")
        return str(txt_path)
    
    def _get_question_type_label(self, question_type: str) -> str:
        """Get question type label"""
        type_labels = {
            "single_choice": "Single Choice",
            "multiple_choice": "Multiple Choice",
            "open_ended": "Open-ended",
            "scale": "Scale",
            "likert": "Likert Scale",
            "dropdown": "Dropdown",
            "yes_no": "Yes/No",
            "ranking": "Ranking",
            "matrix": "Matrix",
        }
        return type_labels.get(question_type, question_type)
    
    # ========== Third-party platform methods ==========
    
    async def _distribute_to_platform(
        self,
        survey: Dict,
        backend_type: str,
        target_count: int,
    ) -> Dict[str, Any]:
        """Distribute survey to third-party platform"""
        try:
            from src.survey.backends.factory import BackendFactory
            
            backend = BackendFactory.get_or_create(backend_type)
            
            # Create survey
            external_id = await backend.create_survey(survey)
            
            # Distribute survey
            share_url = await backend.distribute(external_id, {
                "target_count": target_count,
            })
            
            return {
                "external_id": external_id,
                "share_url": share_url,
                "backend_type": backend_type,
                "status": "active",
            }
            
        except Exception as e:
            logger.error(f"Failed to distribute to platform: {e}")
            return {
                "error": str(e),
                "status": "failed",
            }
    
    # ========== AI simulation methods ==========
    
    async def _generate_personas(self, template: str, count: int) -> List[Dict]:
        """Generate AI personas"""
        try:
            from src.agents.fixed_agents.persona_generation_agent import PersonaGenerationAgent
            
            if self._persona_agent is None:
                self._persona_agent = PersonaGenerationAgent(
                    agent_id=f"{self.agent_id}_persona",
                    llm_skill=self.llm_skill,
                )
            
            result = await self._persona_agent.execute_async({
                "template": template,
                "count": count,
            })
            
            if result.get("success"):
                return result.get("personas", [])
            return []
            
        except Exception as e:
            logger.error(f"Failed to generate personas: {e}")
            return []
    
    async def _simulate_responses(self, survey: Dict, personas: List[Dict]) -> List[Dict]:
        """AI simulate responses"""
        try:
            from src.agents.fixed_agents.simulated_response_agent import SimulatedResponseAgent
            
            if self._simulation_agent is None:
                self._simulation_agent = SimulatedResponseAgent(
                    agent_id=f"{self.agent_id}_sim",
                    llm_skill=self.llm_skill,
                )
            
            result = await self._simulation_agent.execute({
                "survey": survey,
                "personas": personas,
                "parallel": True,
            })
            
            return result.get("responses", [])
            
        except Exception as e:
            logger.error(f"Failed to simulate responses: {e}")
            return []
