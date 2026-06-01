"""
SurveyOptimizationAgent - Survey Optimization Agent

Analyzes and optimizes survey questions to improve survey quality.

Features:
1. Question clarity check
2. Question completeness check
3. Biased question identification
4. Question order optimization
5. LLM-enhanced optimization suggestions

Input:
{
    "questions": List[Dict],          # Question list
    "optimization_goals": List[str],  # Optimization goals
    "target_audience": str,           # Target audience (optional)
}

Output:
{
    "success": bool,
    "analysis": Dict,                 # Analysis results
    "suggestions": List[Dict],         # Optimization suggestions
    "optimized_questions": List[Dict], # Optimized questions
}
"""
from typing import Any, Dict, List, Optional
import asyncio

from src.agents.fixed_agents.base_fixed_agent import FixedAgent


class SurveyOptimizationAgent(FixedAgent):
    """Survey Optimization Agent.
    
    Responsible for analyzing survey question quality and providing optimization suggestions.
    """
    
    agent_type = "survey_optimization"
    version = "1.0.0"
    capabilities = [
        "Question clarity analysis",
        "Question completeness check",
        "Biased question identification",
        "Question order optimization",
        "LLM-enhanced suggestions",
    ]
    
    # Optimization goal mapping
    OPTIMIZATION_GOALS = {
        "clarity": "Clarity optimization",
        "completeness": "Completeness optimization",
        "bias_reduction": "Bias reduction",
        "flow_optimization": "Flow optimization",
        "response_rate": "Response rate improvement",
    }
    
    # Common issue templates
    ISSUE_TEMPLATES = {
        "ambiguous": {
            "name": "Ambiguous question",
            "patterns": ["is it good", "how about", "how much", "often"],
            "suggestion": "Question phrasing is too vague, suggest making it more specific"
        },
        "leading": {
            "name": "Leading question",
            "patterns": ["isn't it", "doesn't it", "should"],
            "suggestion": "Question may lead respondents, suggest neutral phrasing"
        },
        "double_barreled": {
            "name": "Double-barreled question",
            "patterns": ["and", "as well as", "at the same time"],
            "suggestion": "Question contains multiple topics, suggest splitting"
        },
        "complex": {
            "name": "Complex question",
            "patterns": [],  # Based on length
            "suggestion": "Question is too complex, suggest simplifying"
        },
    }
    
    def __init__(
        self,
        agent_id: str,
        name: str = "Survey Optimization Agent",
        description: str = "Analyze survey question quality and provide optimization suggestions",
        storage_path: Optional[str] = None,
        llm_skill: Optional[Any] = None,
    ):
        """Initialize Survey Optimization Agent."""
        super().__init__(agent_id, name=name, description=description, storage_path=storage_path)
        self.llm_skill = llm_skill
    
    def validate_input(self, task_input: Dict[str, Any]) -> tuple[bool, str]:
        """Validate input parameters."""
        valid, error = super().validate_input(task_input)
        if not valid:
            return valid, error
        
        if "questions" not in task_input:
            return False, "Missing required 'questions' field"
        
        questions = task_input["questions"]
        if not isinstance(questions, list):
            return False, "'questions' must be a list type"
        
        if len(questions) == 0:
            return False, "Question list cannot be empty"
        
        return True, ""
    
    async def execute(self, task_input: Dict[str, Any]) -> Dict[str, Any]:
        """Execute survey optimization (async).
        
        Args:
            task_input: {
                "questions": List[Dict],          # Question list
                "optimization_goals": List[str],  # Optimization goals
                "target_audience": str,           # Target audience (optional)
            }
            
        Returns:
            Analysis and optimization results
        """
        questions = task_input["questions"]
        optimization_goals = task_input.get("optimization_goals", ["clarity"])
        target_audience = task_input.get("target_audience")
        
        # Publish start event
        await self.publish_event("optimization_started", {"question_count": len(questions)})
        
        # Analyze questions
        analysis = await self._analyze_questions_async(questions, optimization_goals)
        
        # Generate optimization suggestions
        suggestions = self._generate_suggestions(analysis)
        
        # Apply optimizations
        optimized_questions = self._apply_optimizations(questions, suggestions)
        
        # Write to shared state
        await self.write_shared_state(f"agent.{self.agent_id}.last_optimization", {
            "original_count": len(questions),
            "suggestion_count": len(suggestions),
        })
        
        # Publish completion event
        await self.publish_event("optimization_completed", {"suggestion_count": len(suggestions)})
        
        return {
            "success": True,
            "analysis": analysis,
            "suggestions": suggestions,
            "optimized_questions": optimized_questions,
        }
    
    async def _analyze_questions_async(
        self, 
        questions: List[Dict], 
        goals: List[str]
    ) -> Dict[str, Any]:
        """Asynchronously analyze questions."""
        # Analysis logic (can actually call LLM)
        return self._analyze_questions(questions, goals)
    
    async def _analyze_questions(
        self, 
        questions: List[Dict], 
        goals: List[str]
    ) -> Dict[str, Any]:
        """Analyze questions."""
        analysis = {
            "total_questions": len(questions),
            "question_types": {},
            "average_length": 0,
            "goals_addressed": goals,
        }
        
        # Count question types
        type_counts = {}
        total_length = 0
        
        for q in questions:
            q_type = q.get("type", "unknown")
            type_counts[q_type] = type_counts.get(q_type, 0) + 1
            total_length += len(q.get("text", ""))
        
        analysis["question_types"] = type_counts
        analysis["average_length"] = total_length / len(questions) if questions else 0
        
        # Evaluate dimensions
        analysis["clarity_score"] = self._calculate_clarity_score(questions)
        analysis["completeness_score"] = self._calculate_completeness_score(questions)
        
        return analysis
    
    def _identify_issues(self, questions: List[Dict]) -> List[Dict]:
        """Identify issues."""
        issues = []
        
        for i, q in enumerate(questions):
            text = q.get("text", "") if isinstance(q, dict) else str(q)
            
            # Check for ambiguous questions
            for pattern in self.ISSUE_TEMPLATES["ambiguous"]["patterns"]:
                if pattern in text:
                    issues.append({
                        "question_index": i,
                        "question_id": q.get("id", f"q{i}") if isinstance(q, dict) else f"q{i}",
                        "issue_type": "ambiguous",
                        "description": self.ISSUE_TEMPLATES["ambiguous"]["name"],
                        "suggestion": self.ISSUE_TEMPLATES["ambiguous"]["suggestion"],
                    })
                    break
            
            # Check for leading questions
            for pattern in self.ISSUE_TEMPLATES["leading"]["patterns"]:
                if pattern in text:
                    issues.append({
                        "question_index": i,
                        "question_id": q.get("id", f"q{i}") if isinstance(q, dict) else f"q{i}",
                        "issue_type": "leading",
                        "description": self.ISSUE_TEMPLATES["leading"]["name"],
                        "suggestion": self.ISSUE_TEMPLATES["leading"]["suggestion"],
                    })
                    break
            
            # Check for complex questions (length > 50 characters)
            if len(text) > 50:
                issues.append({
                    "question_index": i,
                    "question_id": q.get("id", f"q{i}") if isinstance(q, dict) else f"q{i}",
                    "issue_type": "complex",
                    "description": self.ISSUE_TEMPLATES["complex"]["name"],
                    "suggestion": self.ISSUE_TEMPLATES["complex"]["suggestion"],
                })
        
        return issues
    
    async def _generate_suggestions(
        self,
        questions: List[Dict],
        issues: List[Dict],
        goals: List[str],
        target_audience: Optional[str]
    ) -> List[Dict]:
        """Generate optimization suggestions."""
        suggestions = []
        
        # Generate suggestions based on issues
        for issue in issues:
            suggestions.append({
                "question_id": issue["question_id"],
                "priority": "high" if issue["issue_type"] in ["leading", "ambiguous"] else "medium",
                "suggestion": issue["suggestion"],
            })
        
        # Add general suggestions based on optimization goals
        if "clarity" in goals:
            suggestions.append({
                "question_id": "general",
                "priority": "medium",
                "suggestion": "Ensure each question asks only one thing, avoid double negatives and complex sentence structures",
            })
        
        if "response_rate" in goals:
            suggestions.append({
                "question_id": "general",
                "priority": "medium",
                "suggestion": "Consider adding 'don't know' or 'not applicable' options to improve response rate",
            })
        
        # If LLM is available, get smarter suggestions
        if self.llm_skill and target_audience:
            llm_suggestions = await self._get_llm_suggestions(questions, target_audience)
            suggestions.extend(llm_suggestions)
        
        return suggestions
    
    async def _optimize_questions(
        self,
        questions: List[Dict],
        suggestions: List[Dict]
    ) -> List[Dict]:
        """Optimize questions."""
        optimized = []
        
        for i, q in enumerate(questions):
            new_q = q.copy()
            
            # Optimize based on suggestions
            for s in suggestions:
                if s["question_id"] == q.get("id", f"q{i}"):
                    # Simple optimization logic
                    text = new_q.get("text", "")
                    
                    # Fix ambiguous questions
                    if "is it good" in text:
                        new_q["text"] = text.replace("is it good", "to what extent")
                    elif "how about" in text:
                        new_q["text"] = text.replace("how about", "rate from 1-5")
            
            optimized.append(new_q)
        
        return optimized
    
    async def _get_llm_suggestions(
        self,
        questions: List[Dict],
        target_audience: str
    ) -> List[Dict]:
        """Use LLM to get suggestions."""
        if not self.llm_skill:
            return []
        
        try:
            prompt = f"""
Analyze the following survey questions and provide optimization suggestions for target audience "{target_audience}":

Question list:
{self._format_questions_for_llm(questions)}

Please provide:
1. Clarity score for each question (1-5)
2. Specific optimization suggestions
"""
            
            response = await self.llm_skill.execute(
                prompt=prompt,
                max_tokens=500,
            )
            
            if response.get("success"):
                # Parse LLM response to generate suggestions
                return [{
                    "question_id": "llm_analysis",
                    "priority": "medium",
                    "suggestion": response.get("content", "")[:200],
                    "source": "llm",
                }]
        except Exception:
            pass
        
        return []
    
    def _format_questions_for_llm(self, questions: List[Dict]) -> str:
        """Format questions for LLM analysis."""
        lines = []
        for i, q in enumerate(questions, 1):
            lines.append(f"{i}. {q.get('text', '')}")
            if q.get("options"):
                opts = ", ".join(q["options"]) if isinstance(q["options"], list) else str(q["options"])
                lines.append(f"   Options: {opts}")
        return "\n".join(lines)
    
    def _calculate_clarity_score(self, questions: List[Dict]) -> float:
        """Calculate clarity score."""
        if not questions:
            return 0.0
        
        total_score = 0.0
        for q in questions:
            text = q.get("text", "")
            score = 1.0
            
            # Deduction items
            if any(p in text for p in ["is it good", "how about", "how much"]):
                score -= 0.3
            if len(text) > 50:
                score -= 0.2
            if any(p in text for p in ["isn't it", "doesn't it"]):
                score -= 0.4
            
            total_score += max(0, score)
        
        return total_score / len(questions)
    
    def _calculate_completeness_score(self, questions: List[Dict]) -> float:
        """Calculate completeness score."""
        if not questions:
            return 0.0
        
        # Check if multiple question types are covered
        types = set(q.get("type", "unknown") for q in questions)
        type_score = min(1.0, len(types) / 3)  # At least 3 types
        
        # Check question count
        count_score = min(1.0, len(questions) / 5)  # At least 5 questions
        
        return (type_score + count_score) / 2
