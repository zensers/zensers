"""
Requirement Analysis Agent
=========================

Deep analysis of user requirements to generate research plans.

Responsibilities:
1. Identify user intent (research type, target audience, use case)
2. Extract key entities (industry, companies, technologies, time range, etc.)
3. Analyze complexity, recommend research depth
4. Generate research framework draft (section suggestions, data sources, analysis methods)

Input:
{
    "user_input": str,          # User's raw input
    "context": dict,            # Context information (optional)
    "history": list,            # Conversation history (optional)
}

Output:
{
    "success": bool,
    "intent": {
        "type": str,            # Research type: market_research|investment|policy|competitor
        "audience": str,        # Target audience: investor|executive|researcher
        "scenario": str,        # Use case: decision|presentation|learning
    },
    "entities": {
        "industry": str,        # Industry
        "companies": list,      # Companies of interest
        "technologies": list,   # Technologies of interest
        "time_range": str,      # Time range
        "region": str,          # Geographic scope
    },
    "complexity": {
        "level": str,           # Complexity: simple|medium|complex
        "estimated_sections": int,  # Suggested section count
        "estimated_time": str,  # Estimated time
    },
    "framework": {
        "recommended_sections": list,   # Recommended section list
        "data_sources": list,           # Recommended data sources
        "analysis_methods": list,       # Analysis method suggestions
    },
    "reasoning": str,           # Analysis reasoning explanation
}
"""

from typing import Any, Dict
from .base_fixed_agent import FixedAgent


class RequirementAnalysisAgent(FixedAgent):
    """Requirement Analysis Agent.
    
    Responsible for deep analysis of user requirements and generating research plan drafts.
    This is the first step in the research process, providing clear task definitions for subsequent agents.
    """
    
    agent_type = "requirement_analysis"
    version = "1.0.0"
    capabilities = [
        "intent_recognition",
        "entity_extraction",
        "complexity_assessment",
        "research_framework_design",
        "scenario_analysis",
    ]
    
    # Research type mapping
    RESEARCH_TYPES = {
        "market_research": "Market Research",
        "investment": "Investment Research",
        "policy": "Policy Analysis",
        "competitor": "Competitor Analysis",
        "technology": "Technology Research",
        "industry": "Industry Analysis",
    }
    
    # Standard section library
    STANDARD_SECTIONS = {
        "market_research": [
            {"id": "exec_summary", "name": "Executive Summary", "priority": "high"},
            {"id": "market_size", "name": "Market Size", "priority": "high"},
            {"id": "competitive_landscape", "name": "Competitive Landscape", "priority": "high"},
            {"id": "policy_analysis", "name": "Policy Analysis", "priority": "medium"},
            {"id": "tech_trends", "name": "Technology Trends", "priority": "medium"},
            {"id": "user_insights", "name": "User Insights", "priority": "medium"},
            {"id": "business_model", "name": "Business Model", "priority": "medium"},
            {"id": "investment_analysis", "name": "Investment Analysis", "priority": "low"},
            {"id": "risk_assessment", "name": "Risk Assessment", "priority": "medium"},
            {"id": "forecast", "name": "Future Forecast", "priority": "medium"},
        ],
        "investment": [
            {"id": "market_opportunity", "name": "Market Opportunity", "priority": "high"},
            {"id": "competitive_advantage", "name": "Competitive Advantage", "priority": "high"},
            {"id": "financial_analysis", "name": "Financial Analysis", "priority": "high"},
            {"id": "valuation", "name": "Valuation Analysis", "priority": "high"},
            {"id": "risk_factors", "name": "Risk Factors", "priority": "high"},
            {"id": "exit_strategy", "name": "Exit Strategy", "priority": "medium"},
        ],
        "policy": [
            {"id": "policy_overview", "name": "Policy Overview", "priority": "high"},
            {"id": "impact_analysis", "name": "Impact Analysis", "priority": "high"},
            {"id": "regulatory_trends", "name": "Regulatory Trends", "priority": "high"},
            {"id": "compliance_guide", "name": "Compliance Guide", "priority": "medium"},
            {"id": "case_studies", "name": "Case Studies", "priority": "low"},
        ],
    }
    
    def validate_input(self, task_input: Dict[str, Any]) -> tuple[bool, str]:
        """Validate input parameters."""
        valid, error = super().validate_input(task_input)
        if not valid:
            return valid, error
        
        if "user_input" not in task_input:
            return False, "Missing required field 'user_input'"
        
        if not isinstance(task_input["user_input"], str):
            return False, "'user_input' must be a string"
        
        return True, ""
    
    async def execute(self, task_input: Dict[str, Any]) -> Dict[str, Any]:
        """Execute requirement analysis (async).
        
        Args:
            task_input: {
                "user_input": "Analyze energy storage industry investment opportunities",
                "context": {"industry": "energy storage"},
            }
            
        Returns:
            Analysis result
        """
        user_input = task_input["user_input"]
        context = task_input.get("context", {})
        
        # Publish progress event
        await self.publish_event("analysis_started", {"input_length": len(user_input)})
        
        # 1. Intent recognition
        intent = self._identify_intent(user_input)
        
        # 2. Entity extraction
        entities = self._extract_entities(user_input, context)
        
        # 3. Complexity assessment
        complexity = self._assess_complexity(user_input, intent)
        
        # 4. Generate research framework
        framework = self._generate_framework(intent, entities, complexity)
        
        # 5. Generate reasoning
        reasoning = self._generate_reasoning(intent, entities, framework)
        
        # Write to shared state
        await self.write_shared_state(f"agent.{self.agent_id}.last_analysis", {
            "intent": intent,
            "entities": entities,
        })
        
        return {
            "success": True,
            "intent": intent,
            "entities": entities,
            "complexity": complexity,
            "framework": framework,
            "reasoning": reasoning,
        }
    
    def _identify_intent(self, user_input: str) -> Dict[str, str]:
        """Identify user intent.
        
        Identify research type, target audience, and use case based on keyword matching.
        Actual implementation can use LLM for more precise semantic understanding.
        
        New: Returns domain_context for subsequent agent keyword expansion.
        """
        user_input_lower = user_input.lower()
        
        # Identify research type
        research_type = "market_research"  # Default
        if any(kw in user_input_lower for kw in ["invest", "valuation", "financing", "pitch"]):
            research_type = "investment"
        elif any(kw in user_input_lower for kw in ["policy", "regulation", "compliance"]):
            research_type = "policy"
        elif any(kw in user_input_lower for kw in ["competitor", "comparison", "competitive"]):
            research_type = "competitor"
        elif any(kw in user_input_lower for kw in ["technology", "patent", "rd", "research"]):
            research_type = "technology"
        
        # Identify target audience
        audience = "executive"  # Default
        if any(kw in user_input_lower for kw in ["invest", "valuation", "roi", "return"]):
            audience = "investor"
        elif any(kw in user_input_lower for kw in ["academic", "paper", "research", "deep", "study"]):
            audience = "researcher"
        
        # Identify use case
        scenario = "decision"  # Default
        if any(kw in user_input_lower for kw in ["pitch", "ppt", "presentation", "report", "deck"]):
            scenario = "presentation"
        elif any(kw in user_input_lower for kw in ["learn", "understand", "intro", "overview", "basics"]):
            scenario = "learning"
        
        # New: Detect language (simple heuristic)
        from src.core.search import DomainRoleInferrer
        inferrer = DomainRoleInferrer()
        language = inferrer.detect_language(user_input)
        
        # New: Get domain role information
        domain_context = inferrer.infer(research_type, user_input, language)
        
        return {
            "type": research_type,
            "audience": audience,
            "scenario": scenario,
            "language": language,
            "domain_context": domain_context,
        }
    
    def _extract_entities(self, user_input: str, context: Dict) -> Dict[str, Any]:
        """Extract key entities.
        
        Extract industry, companies, technologies, time, and region from user input.
        """
        user_input_lower = user_input.lower()
        
        # Industry recognition (simplified, actual can use NER model)
        industries = {
            "energy storage": "Energy Storage",
            "new energy": "New Energy",
            "ai": "AI",
            "artificial intelligence": "AI",
            "semiconductor": "Semiconductor",
            "healthcare": "Healthcare",
            "pharma": "Healthcare",
            "automotive": "Automotive",
            "electric vehicle": "Electric Vehicles",
            "ev": "Electric Vehicles",
        }
        
        industry = context.get("industry", "")
        if not industry:
            for kw, val in industries.items():
                if kw in user_input_lower:
                    industry = val
                    break
        
        # Time range recognition
        time_range = "Last 3 years"  # Default
        if any(kw in user_input_lower for kw in ["2024", "this year", "latest"]):
            time_range = "2024 Latest"
        elif any(kw in user_input_lower for kw in ["5 year", "five year", "history", "historical"]):
            time_range = "Last 5 years"
        elif any(kw in user_input_lower for kw in ["10 year", "ten year", "panorama"]):
            time_range = "Historical Panorama"
        
        # Region recognition
        region = "China"  # Default
        if any(kw in user_input_lower for kw in ["global", "world", "international"]):
            region = "Global"
        elif any(kw in user_input_lower for kw in ["us", "usa", "america"]):
            region = "United States"
        elif any(kw in user_input_lower for kw in ["europe", "eu"]):
            region = "Europe"
        
        # Companies of interest (simplified extraction, actual can use NER)
        companies = []
        company_keywords = ["BYD", "Tesla", "CATL", "Huawei", "Siemens", "GE"]
        for kw in company_keywords:
            if kw.lower() in user_input_lower:
                companies.append(kw)
        
        return {
            "industry": industry or "Unspecified",
            "companies": companies,
            "technologies": [],  # Can be extracted from input
            "time_range": time_range,
            "region": region,
        }
    
    def _assess_complexity(self, user_input: str, intent: Dict) -> Dict[str, Any]:
        """Assess task complexity."""
        user_input_len = len(user_input)
        
        # Assess complexity based on input length and intent
        if user_input_len < 10:
            level = "simple"
            estimated_sections = 3
            estimated_time = "3-5 minutes"
        elif user_input_len < 30 or intent["type"] in ["investment", "policy"]:
            level = "medium"
            estimated_sections = 5
            estimated_time = "5-10 minutes"
        else:
            level = "complex"
            estimated_sections = 8
            estimated_time = "10-20 minutes"
        
        return {
            "level": level,
            "estimated_sections": estimated_sections,
            "estimated_time": estimated_time,
        }
    
    def _generate_framework(
        self, 
        intent: Dict, 
        entities: Dict, 
        complexity: Dict
    ) -> Dict[str, Any]:
        """Generate research framework."""
        research_type = intent["type"]
        
        # Get standard sections for this type
        standard_sections = self.STANDARD_SECTIONS.get(research_type, [])
        
        # Filter sections based on complexity
        if complexity["level"] == "simple":
            # Simple task: only select high priority sections
            recommended = [s for s in standard_sections if s["priority"] == "high"][:3]
        elif complexity["level"] == "medium":
            # Medium task: select high + medium priority
            recommended = [s for s in standard_sections if s["priority"] in ["high", "medium"]][:5]
        else:
            # Complex task: include all sections
            recommended = standard_sections[:complexity["estimated_sections"]]
        
        # Recommend data sources
        data_sources = self._recommend_data_sources(entities, intent)
        
        # Recommend analysis methods
        analysis_methods = self._recommend_analysis_methods(intent)
        
        return {
            "recommended_sections": recommended,
            "data_sources": data_sources,
            "analysis_methods": analysis_methods,
        }
    
    def _recommend_data_sources(self, entities: Dict, intent: Dict) -> list:
        """Recommend data sources."""
        sources = []
        
        # Based on industry
        if entities["industry"] in ["Energy Storage", "New Energy", "New Energy Vehicles"]:
            sources.extend([
                {"name": "CNESA Energy Storage Database", "type": "industry", "priority": "high"},
                {"name": "MIIT Industry Data", "type": "government", "priority": "high"},
            ])
        
        # Based on research type
        if intent["type"] == "investment":
            sources.extend([
                {"name": "Wind/Tonghuashun", "type": "financial", "priority": "high"},
                {"name": "IT Juzi", "type": "investment", "priority": "medium"},
            ])
        elif intent["type"] == "policy":
            sources.extend([
                {"name": "State Council Policy Database", "type": "government", "priority": "high"},
                {"name": "NDRC Documents", "type": "government", "priority": "high"},
            ])
        
        # General data sources
        sources.extend([
            {"name": "iResearch Consulting", "type": "consulting", "priority": "medium"},
            {"name": "Analysys", "type": "consulting", "priority": "medium"},
            {"name": "Expert Interviews", "type": "primary", "priority": "low"},
        ])
        
        return sources
    
    def _recommend_analysis_methods(self, intent: Dict) -> list:
        """Recommend analysis methods."""
        methods = ["desk_research"]  # Basic desk research
        
        if intent["type"] == "market_research":
            methods.extend(["market_sizing", "competitive_mapping"])
        elif intent["type"] == "investment":
            methods.extend(["dcf_valuation", "comparable_analysis", "risk_assessment"])
        elif intent["type"] == "policy":
            methods.extend(["policy_text_analysis", "impact_assessment"])
        
        return methods
    
    def _generate_reasoning(
        self, 
        intent: Dict, 
        entities: Dict, 
        framework: Dict
    ) -> str:
        """Generate analysis reasoning."""
        reasoning_parts = []
        
        # Intent recognition reasoning
        reasoning_parts.append(
            f"Identified as [{self.RESEARCH_TYPES.get(intent['type'], 'Market Research')}] type, "
            f"target audience is [{intent['audience']}], "
            f"use case is [{intent['scenario']}]."
        )
        
        # Entity extraction reasoning
        if entities["industry"] != "Unspecified":
            reasoning_parts.append(f"Focusing on [{entities['industry']}] industry")
        if entities["companies"]:
            reasoning_parts.append(f"Key focus on [{', '.join(entities['companies'])}]")
        reasoning_parts.append(
            f"Research scope: {entities['region']}, time span: {entities['time_range']}."
        )
        
        # Framework design reasoning
        section_names = [s["name"] for s in framework["recommended_sections"]]
        reasoning_parts.append(
            f"Based on the above analysis, recommending the following sections: {', '.join(section_names)}."
        )
        
        return " ".join(reasoning_parts)
