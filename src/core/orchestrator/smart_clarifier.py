"""
Smart Requirement Clarifier - Provides framework options, lets users make decisions

Content template architecture:
- Content templates (config/templates/*.yaml): define section structure
- HTML templates (config/document_templates/*.html): define style and layout

Styling is handled by HTML templates; research phase only focuses on content structure.

Multi-language support:
- Templates support multi-language name/description fields
- Uses i18n module for language detection and localization
"""
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import yaml
import logging

# NEW: interaction parameter model (lazy import, called inside methods)

# Import i18n module
try:
    from src.core.i18n import (
        I18n, 
        Language, 
        detect_language, 
        get_language, 
        set_language,
        get_localized_text,
    )
except ImportError:
    # Backward compatibility: if i18n module not available, use simplified version
    def detect_language(text: str):
        return "en"
    def get_language():
        return "en"
    def get_localized_text(text_dict, lang=None, fallback=""):
        if isinstance(text_dict, str):
            return text_dict
        return text_dict.get("en", text_dict.get("zh", fallback))
    class I18n:
        @classmethod
        def localize_section(cls, section, lang=None):
            result = section.copy()
            if "name" in result and isinstance(result["name"], dict):
                result["name"] = result["name"].get("en", result["name"].get("zh", ""))
            if "description" in result and isinstance(result["description"], dict):
                result["description"] = result["description"].get("en", result["description"].get("zh", ""))
            return result
        @classmethod
        def localize_sections(cls, sections, lang=None):
            return [cls.localize_section(s, lang) for s in sections]

logger = logging.getLogger(__name__)

# Content template config file path (modifiable after compilation)
TEMPLATE_CONFIG_DIR = Path("config/templates")
TEMPLATE_CUSTOM_DIR = Path("config/templates/custom")


class OutputType(Enum):
    """Output type (classified by professional use)"""
    # Broker/investment institution standard reports
    INDUSTRY_REPORT = "industry_report"
    INDUSTRY_WEEKLY = "industry_weekly"
    COMPANY_RESEARCH = "company_research"
    QUARTERLY_COMMENTARY = "quarterly_commentary"
    ANNUAL_ANALYSIS = "annual_analysis"
    CONFERENCE_CALL = "conference_call"
    # Financing/business reports
    COMMERCIAL_PLAN = "commercial_plan"
    PITCH_DECK = "pitch_deck"
    INVESTMENT_MEMO = "investment_memo"
    # Analysis reports
    COMPETITOR_ANALYSIS = "competitor_analysis"
    POLICY_BRIEF = "policy_brief"
    MARKET_BRIEF = "market_brief"
    DATA_DASHBOARD = "data_dashboard"
    CUSTOM = "custom"


class OutputFormat(Enum):
    """Output format"""
    DOCX = "docx"
    PPTX = "pptx"
    PDF = "pdf"
    MD = "md"
    HTML = "html"


class QuestionType(Enum):
    """Question type"""
    SINGLE_CHOICE = "single_choice"
    MULTI_CHOICE = "multi_choice"
    TEXT = "text"
    CONFIRM = "confirm"


@dataclass
class Question:
    """Question definition"""
    id: str
    type: QuestionType
    text: str
    options: Optional[List[str]] = None
    default: Optional[Any] = None
    required: bool = True
    help_text: Optional[str] = None


@dataclass
class ResearchRequirement:
    """Research requirement (after clarification)"""
    topic: str
    aspects: List[str]
    region: str = "China"
    time_range: str = "Last 3 Years"
    focus_brands: List[str] = field(default_factory=list)
    competitors: List[str] = field(default_factory=list)
    depth: str = "standard"
    output_type: Optional[OutputType] = None
    output_format: OutputFormat = OutputFormat.DOCX
    template_id: str = "industry_report_standard"
    selected_sections: List[str] = field(default_factory=list)
    # Complete section info: List[Dict] containing id, name, description, etc.
    section_details: List[Dict[str, Any]] = field(default_factory=list)
    special_requirements: List[str] = field(default_factory=list)
    confirmed: bool = False
    intent_type: str = "research"
    complexity: str = "medium"
    recommended_skills: List[str] = field(default_factory=list)
    # NEW: dynamic field passthrough
    dynamic_fields: Dict[str, Any] = field(default_factory=dict)
    # Survey integration fields
    include_survey: bool = False
    enable_questionnaire: bool = False
    survey_mode: str = "ai_simulation"  # "ai_simulation" | "third_party"
    survey_target_count: int = 100
    survey_timeout_days: int = 7
    section_requirements: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class Template:
    """Content template definition (defines section structure)"""
    id: str
    name: str
    description: str
    output_type: OutputType
    sections: List[Dict[str, Any]]
    estimated_pages: str
    suitable_for: List[str]
    supported_formats: List[OutputFormat] = field(
        default_factory=lambda: [OutputFormat.DOCX, OutputFormat.PPTX, OutputFormat.PDF]
    )


@dataclass
class UserChoice:
    """User choice"""
    topic: str
    output_type: OutputType
    output_format: OutputFormat
    template_id: str
    selected_sections: List[str] = field(default_factory=list)
    # Complete section info: List[Dict] containing id, name, description, etc.
    section_details: List[Dict[str, Any]] = field(default_factory=list)
    custom_sections: List[Dict] = field(default_factory=list)
    region: str = "China"
    time_range: str = "Last 3 Years"
    focus_areas: List[str] = field(default_factory=list)
    depth: str = "Standard"
    confirmed: bool = False
    # NEW: dynamic field storage (stores all key-value pairs from interaction_parameters)
    dynamic_fields: Dict[str, Any] = field(default_factory=dict)
    # Survey configuration
    include_survey: bool = False
    survey_mode: str = "ai_simulation"  # "ai_simulation" | "third_party"
    survey_target_count: int = 100
    survey_timeout_days: int = 7


class TemplateLoader:
    """
    Template loader - dynamically loads template definitions from YAML config files
    
    Supports post-compilation modification: edit YAML files directly to update templates
    """
    
    def __init__(self, config_dir: Path = None, custom_dir: Path = None):
        self.config_dir = config_dir or TEMPLATE_CONFIG_DIR
        self.custom_dir = custom_dir or TEMPLATE_CUSTOM_DIR
        self._templates: Dict[str, Template] = {}
        self._loaded = False
    
    def load_templates(self) -> Dict[str, Template]:
        """Load all templates from config files"""
        if self._loaded:
            return self._templates
        
        templates = {}
        
        # 1. Load standard templates
        if self.config_dir.exists():
            for yaml_file in self.config_dir.glob("*.yaml"):
                if yaml_file.name == "template_schema.yaml":
                    continue
                try:
                    template = self._load_template_from_yaml(yaml_file)
                    if template:
                        templates[template.id] = template
                        logger.info(f"Loaded template: {template.id}")
                except Exception as e:
                    logger.warning(f"Failed to load {yaml_file}: {e}")
        
        # 2. Load custom templates (override same-name standard templates)
        if self.custom_dir.exists():
            for yaml_file in self.custom_dir.glob("*.yaml"):
                try:
                    template = self._load_template_from_yaml(yaml_file)
                    if template:
                        templates[template.id] = template
                        logger.info(f"Loaded custom template: {template.id}")
                except Exception as e:
                    logger.warning(f"Failed to load custom {yaml_file}: {e}")
        
        self._templates = templates
        self._loaded = True
        return templates
    
    def _load_template_from_yaml(self, yaml_path: Path) -> Optional[Template]:
        """Load single template from YAML file"""
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        if not data:
            return None
        
        # Parse output_type
        output_type_str = data.get('output_type', 'custom')
        try:
            output_type = OutputType(output_type_str)
        except ValueError:
            output_type = OutputType.CUSTOM
        
        # Parse supported_formats
        formats_str = data.get('supported_formats', ['docx'])
        supported_formats = []
        for fmt in formats_str:
            try:
                supported_formats.append(OutputFormat(fmt))
            except ValueError:
                pass
        if not supported_formats:
            supported_formats = [OutputFormat.DOCX]
        
        return Template(
            id=data.get('id', yaml_path.stem),
            name=data.get('name', yaml_path.stem),
            description=data.get('description', ''),
            output_type=output_type,
            sections=data.get('sections', []),
            estimated_pages=data.get('estimated_pages', 'Unknown'),
            suitable_for=data.get('suitable_for', []),
            supported_formats=supported_formats,
        )
    
    def reload_templates(self) -> Dict[str, Template]:
        """Reload templates (runtime update)"""
        self._loaded = False
        self._templates = {}
        return self.load_templates()
    
    def get_template(self, template_id: str) -> Optional[Template]:
        """Get single template"""
        return self.load_templates().get(template_id)
    
    def get_templates_by_type(self, output_type: OutputType) -> List[Template]:
        """Get template list by output type"""
        return [t for t in self.load_templates().values() if t.output_type == output_type]
    
    def get_localized_template(
        self, 
        template_id: str, 
        lang: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get localized template
        
        Args:
            template_id: Template ID
            lang: Target language (None uses current language)
            
        Returns:
            Localized template dict
        """
        template = self.get_template(template_id)
        if not template:
            return None
        
        target_lang = lang or get_language()
        
        result = {
            "id": template.id,
            "name": get_localized_text(template.name, target_lang) if isinstance(template.name, dict) else template.name,
            "description": get_localized_text(template.description, target_lang) if isinstance(template.description, dict) else template.description,
            "output_type": template.output_type,
            "sections": I18n.localize_sections(template.sections, target_lang),
            "estimated_pages": template.estimated_pages,
            "suitable_for": template.suitable_for,
            "supported_formats": template.supported_formats,
        }
        
        return result
    
    def get_localized_sections(
        self,
        template_id: str,
        lang: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get localized section list for template
        
        Args:
            template_id: Template ID
            lang: Target language
            
        Returns:
            Localized section list
        """
        template = self.get_template(template_id)
        if not template:
            return []
        
        target_lang = lang or get_language()
        return I18n.localize_sections(template.sections, target_lang)


# Global template loader
_template_loader = TemplateLoader()


class SmartClarifier:
    """
    Smart Requirement Clarifier
    
    Content templates: define section structure (loaded from config/templates/*.yaml)
    Styling handled by HTML templates (config/document_templates/*.html)
    
    Supports post-compilation modification: edit YAML/HTML files directly to update
    """
    
    def __init__(self):
        self.current_choice: Optional[UserChoice] = None
        self._template_loader = _template_loader
        # NEW: introduce framework manager (for getting interaction parameters per report type)
        try:
            from src.core.research_framework_manager import get_framework_manager
            self._framework_manager = get_framework_manager()
        except ImportError:
            self._framework_manager = None
    
    @property
    def TEMPLATES(self) -> Dict[str, Template]:
        """Get content template dict (dynamic loading)"""
        templates = self._template_loader.load_templates()
        if templates:
            return templates
        logger.warning("Using built-in fallback templates")
        return self._get_builtin_templates()
    
    def _get_builtin_templates(self) -> Dict[str, Template]:
        """Built-in default templates (when config file loading fails)"""
        return {
            "industry_report_standard": Template(
                id="industry_report_standard",
                name="Standard Industry Research Report",
                description="Comprehensive industry analysis",
                output_type=OutputType.INDUSTRY_REPORT,
                sections=[
                    {"id": "summary", "name": "Summary", "required": True},
                    {"id": "market_size", "name": "Market Size", "required": False},
                    {"id": "competition", "name": "Competitive Landscape", "required": False},
                ],
                estimated_pages="20-30 pages",
                suitable_for=["Strategic Decision"],
                supported_formats=[OutputFormat.DOCX, OutputFormat.PPTX, OutputFormat.PDF],
            ),
            "commercial_plan_standard": Template(
                id="commercial_plan_standard",
                name="Standard Business Plan",
                description="Systematically describes business model",
                output_type=OutputType.COMMERCIAL_PLAN,
                sections=[
                    {"id": "exec_summary", "name": "Executive Summary", "required": True},
                    {"id": "business_model", "name": "Business Model", "required": True},
                    {"id": "team", "name": "Team Introduction", "required": True},
                ],
                estimated_pages="30-50 pages",
                suitable_for=["Financing Application"],
                supported_formats=[OutputFormat.DOCX, OutputFormat.PDF],
            ),
        }
    
    def _get_interaction_parameters(self, output_type: OutputType) -> Dict[str, Any]:
        """
        Get interaction parameter config by output type.
        Returns safe defaults if no specific config for the type.
        
        Args:
            output_type: Output type enum value
            
        Returns:
            Parameter dict, format: { param_id: { type, label, default, options, ... } }
        """
        if not self._framework_manager:
            return self._get_default_parameters()
        
        output_type_str = output_type.value if hasattr(output_type, 'value') else str(output_type)
        
        # Get parameters from framework config
        framework_config = self._framework_manager.get_framework_config(output_type_str)
        params = framework_config.get_interaction_parameters()
        
        if params:
            # Use InteractionParameterSet serialization (with localization)
            try:
                from src.core.interaction_parameter import InteractionParameterSet
                if InteractionParameterSet is not None:
                    param_set = InteractionParameterSet.from_yaml_dict(params)
                    if param_set:
                        from src.core.i18n import get_language
                        lang = get_language()
                        # Return list format (for new frontend) and dict format (for CLI/old frontend)
                        return {
                            "parameters": param_set.to_list(lang),
                        }
            except Exception:
                pass
            # Fallback: return raw dict
            return params
        
        # Fallback: return industry report default parameters
        return self._get_default_parameters()
    
    def _get_default_parameters(self) -> Dict[str, Any]:
        """Safe fallback - industry report default parameters (backward compatible)"""
        return {
            "parameters": [
                {
                    "id": "region",
                    "type": "select",
                    "label": "Research Region",
                    "default": "China",
                    "required": False,
                    "options": [
                        {"value": "China", "label": "China"},
                        {"value": "Global", "label": "Global"},
                        {"value": "USA", "label": "USA"},
                        {"value": "Europe", "label": "Europe"},
                    ],
                },
                {
                    "id": "time_range",
                    "type": "select",
                    "label": "Time Range",
                    "default": "Last 3 Years",
                    "required": False,
                    "options": [
                        {"value": "Last 1 Year", "label": "Last 1 Year"},
                        {"value": "Last 3 Years", "label": "Last 3 Years"},
                        {"value": "Last 5 Years", "label": "Last 5 Years"},
                    ],
                },
                {
                    "id": "depth",
                    "type": "select",
                    "label": "Research Depth",
                    "default": "Deep",
                    "required": False,
                    "options": [
                        {"value": "Brief", "label": "Brief"},
                        {"value": "Standard", "label": "Standard"},
                        {"value": "Deep", "label": "Deep"},
                    ],
                },
            ]
        }

    def _localize_params(self, params: Dict) -> Dict:
        """Localize parameter fields (using current language)"""
        try:
            from src.core.i18n import get_language
            lang = get_language()
        except ImportError:
            return params
        
        if lang == "en":
            return params  # Default is English, no conversion needed
        
        # If already in to_list format
        param_list = params.get("parameters")
        if param_list is not None and isinstance(param_list, list):
            localized_list = []
            for p in param_list:
                entry = dict(p)
                # If label is a dict, get corresponding language
                if isinstance(p.get("label"), dict):
                    entry["label"] = p["label"].get(lang, p["label"].get("en", p.get("id", "")))
                # Localize options
                if p.get("options"):
                    entry["options"] = [
                        {
                            "value": o.get("value", ""),
                            "label": o.get("label", {}).get(lang, o.get("label", {}).get("en", o.get("value", "")))
                            if isinstance(o.get("label"), dict) else o.get("label", o.get("value", "")),
                        }
                        for o in p["options"]
                    ]
                localized_list.append(entry)
            return {"parameters": localized_list}
        
        return params

    def _parse_output_type(self, output_type_str: str) -> OutputType:
        """
        Parse output type string, supports aliases
        
        Args:
            output_type_str: Output type string (can be enum value or alias)
            
        Returns:
            OutputType enum value
        """
        if not output_type_str:
            return OutputType.INDUSTRY_REPORT
        
        # Try direct enum match
        try:
            return OutputType(output_type_str)
        except ValueError:
            pass
        
        # Alias mapping
        type_mapping = {
            "industry_report": OutputType.INDUSTRY_REPORT,
            "commercial_plan": OutputType.COMMERCIAL_PLAN,
            "pitch_deck": OutputType.PITCH_DECK,
            "investment_memo": OutputType.INVESTMENT_MEMO,
            "competitor_analysis": OutputType.COMPETITOR_ANALYSIS,
            "policy_brief": OutputType.POLICY_BRIEF,
            "market_brief": OutputType.MARKET_BRIEF,
            "data_dashboard": OutputType.DATA_DASHBOARD,
            "custom": OutputType.CUSTOM,
            # Legacy format compatibility
            "research_report": OutputType.INDUSTRY_REPORT,
            "market_research": OutputType.INDUSTRY_REPORT,
            "report": OutputType.INDUSTRY_REPORT,
        }
        
        return type_mapping.get(output_type_str.lower(), OutputType.INDUSTRY_REPORT)
    
    def start(self, user_input: str) -> Dict[str, Any]:
        """Start clarification process"""
        self.current_choice = UserChoice(
            topic=user_input,
            output_type=OutputType.INDUSTRY_REPORT,
            output_format=OutputFormat.DOCX,
            template_id="",
            selected_sections=[],
            custom_sections=[],
            region="China",
            time_range="Last 3 Years",
            focus_areas=[],
            depth="detailed"
        )
        
        return {
            "step": 1,
            "message": f"OK, let's work on the research for '{user_input}' together",
            "instruction": "Please select the output type you need:",
            "options": self._get_output_type_options(),
            "next_step": "select_output_type"
        }
    
    def select_output_type(self, output_type: str) -> Dict[str, Any]:
        """After user selects output type, recommend research framework options"""
        # Parse output type, supports string aliases
        parsed_type = self._parse_output_type(output_type)
        self.current_choice.output_type = parsed_type
        templates = self._template_loader.get_templates_by_type(self.current_choice.output_type)
        
        # Generate framework options based on template (detailed/standard/brief)
        framework_options = self._generate_framework_options(templates)
        
        return {
            "step": 2,
            "message": "Output type selected, please choose a research framework:",
            "instruction": "Based on your needs, the following research frameworks are recommended:",
            "framework_options": framework_options,
            "next_step": "select_framework"
        }
    
    def _generate_framework_options(self, templates: List) -> List[Dict[str, Any]]:
        """Generate framework options based on template"""
        options = []
        
        # Get first template as base
        base_template = templates[0] if templates else None
        if not base_template:
            return self._get_default_framework_options()
        
        all_sections = base_template.sections if hasattr(base_template, 'sections') else []
        
        # Helper: get section name (supports multi-language format)
        def get_section_name(section: Dict) -> str:
            name = section.get("name", section.get("id", ""))
            if isinstance(name, dict):
                # Multi-language format: prefer English, then Chinese, then first value
                return name.get("en", name.get("zh", list(name.values())[0] if name else ""))
            return str(name)
        
        # Option A: Detailed (all sections)
        detailed_sections = [s.get("id", s.get("name", "")) for s in all_sections]
        options.append({
            "id": "detailed",
            "name": "Detailed",
            "description": f"Includes all {len(all_sections)} sections, suitable for in-depth research",
            "sections": all_sections,
            "section_names": [get_section_name(s) for s in all_sections],
            "estimated_pages": "25-40 pages",
            "depth": "deep",
        })
        
        # Option B: Standard (using required field, no longer hardcoded section IDs)
        core_sections = [s for s in all_sections if s.get("required", False)]
        if not core_sections:
            # If no required flag, take first half
            core_sections = all_sections[:max(4, len(all_sections) // 2)]
        options.append({
            "id": "standard",
            "name": "Standard",
            "description": f"Includes {len(core_sections)} core sections, suitable for regular research",
            "sections": core_sections,
            "section_names": [get_section_name(s) for s in core_sections],
            "estimated_pages": "15-25 pages",
            "depth": "standard",
        })
        
        # Option C: Brief (essential sections only)
        minimal_sections = [s for s in all_sections if s.get("required", False)]
        if not minimal_sections:
            minimal_sections = all_sections[:max(3, len(all_sections)//3)]
        options.append({
            "id": "brief",
            "name": "Brief",
            "description": f"Includes {len(minimal_sections)} essential sections, suitable for quick overview",
            "sections": minimal_sections,
            "section_names": [get_section_name(s) for s in minimal_sections],
            "estimated_pages": "8-15 pages",
            "depth": "brief",
        })
        
        return options
    
    def _get_default_framework_options(self) -> List[Dict[str, Any]]:
        """Default framework options"""
        return [
            {
                "id": "detailed",
                "name": "Detailed",
                "description": "Includes 10 sections, suitable for in-depth research",
                "sections": ["Summary", "Market Size", "Competitive Landscape", "Industry Chain", "Trends", 
                           "Policy Environment", "Technology Analysis", "Risk Analysis", "Investment Advice", "Conclusion"],
                "section_names": ["Summary", "Market Size", "Competitive Landscape", "Industry Chain", "Trends", 
                                "Policy Environment", "Technology Analysis", "Risk Analysis", "Investment Advice", "Conclusion"],
                "estimated_pages": "25-40 pages",
                "depth": "deep",
            },
            {
                "id": "standard",
                "name": "Standard",
                "description": "Includes 5 core sections, suitable for regular research",
                "sections": ["Summary", "Market Size", "Competitive Landscape", "Trends", "Conclusion"],
                "section_names": ["Summary", "Market Size", "Competitive Landscape", "Trends", "Conclusion"],
                "estimated_pages": "15-25 pages",
                "depth": "standard",
            },
            {
                "id": "brief",
                "name": "Brief",
                "description": "Includes 3 essential sections, suitable for quick overview",
                "sections": ["Summary", "Market Overview", "Conclusion"],
                "section_names": ["Summary", "Market Overview", "Conclusion"],
                "estimated_pages": "8-15 pages",
                "depth": "brief",
            },
        ]
    
    def select_framework(self, framework_id: str) -> Dict[str, Any]:
        """After user selects research framework, show section details for confirmation"""
        # Get section details by framework_id
        sections_detail = self._get_sections_detail(framework_id)
        
        # Set current choice
        self.current_choice.depth = framework_id
        self.current_choice.selected_sections = [s["id"] for s in sections_detail]
        # Store complete section info (includes id, name, content/description)
        self.current_choice.section_details = sections_detail
        
        return {
            "step": 3,
            "message": f"Selected {framework_id} research framework",
            "instruction": "Please confirm the following sections to ensure the research scope is clear:",
            "sections_detail": sections_detail,
            "framework_id": framework_id,
            "next_step": "confirm_sections"
        }
    
    def _get_sections_detail(self, framework_id: str) -> List[Dict[str, Any]]:
        """Get section details, prioritize template config, fallback to hardcoded defaults"""
        # Prioritize loaded template section definitions
        template_sections = getattr(self.current_choice, 'template_sections', None)
        if template_sections:
            return self._build_sections_from_template(template_sections, framework_id)
        
        # Fallback: hardcoded default sections
        return self._get_default_sections(framework_id)
    
    def _build_sections_from_template(self, sections: List[Dict], framework_id: str) -> List[Dict]:
        """Build section list from template sections at specified detail level"""
        import yaml
        
        def get_name(s):
            name = s.get("name", s.get("id", ""))
            if isinstance(name, dict):
                return name.get("en", name.get("zh", ""))
            return str(name)
        
        def get_content(s):
            desc = s.get("description", "")
            if isinstance(desc, dict):
                return desc.get("en", desc.get("zh", ""))
            return str(desc)
        
        if framework_id == "detailed":
            return [{"id": s["id"], "name": get_name(s), "content": get_content(s)} for s in sections]
        elif framework_id == "standard":
            core = [s for s in sections if s.get("required", False) or 
                    s["id"] in ["summary", "market_size", "competitive_landscape", "growth_drivers", "conclusion"]]
            return [{"id": s["id"], "name": get_name(s), "content": get_content(s)} for s in (core or sections[:5])]
        else:
            minimal = [s for s in sections if s.get("required", False)]
            return [{"id": s["id"], "name": get_name(s), "content": get_content(s)} for s in (minimal or sections[:3])]
    
    def _get_default_sections(self, framework_id: str) -> List[Dict[str, Any]]:
        """Fallback default sections"""
        if framework_id == "detailed":
            return [
                {"id": "summary", "name": "Executive Summary", "content": "Research background, key findings, main conclusions"},
                {"id": "market_size", "name": "Market Size", "content": "Total market, growth rate, segment market size"},
                {"id": "competition", "name": "Competitive Landscape", "content": "Major players, market share, competitive dynamics"},
                {"id": "industry_chain", "name": "Industry Chain", "content": "Upstream supply, midstream manufacturing, downstream applications"},
                {"id": "trend", "name": "Development Trends", "content": "Technology trends, market trends, policy trends"},
                {"id": "policy", "name": "Policy Environment", "content": "Relevant policies, regulatory impact, compliance requirements"},
                {"id": "technology", "name": "Technology Analysis", "content": "Core technologies, technology roadmap, innovation direction"},
                {"id": "risk", "name": "Risk Analysis", "content": "Market risk, policy risk, technology risk"},
                {"id": "investment", "name": "Investment Advice", "content": "Investment opportunities, investment risks, investment strategy"},
                {"id": "conclusion", "name": "Research Conclusion", "content": "Core views, recommendations, future outlook"},
            ]
        elif framework_id == "standard":
            return [
                {"id": "summary", "name": "Executive Summary", "content": "Research background, key findings, main conclusions"},
                {"id": "market_size", "name": "Market Size", "content": "Total market, growth rate, market segments"},
                {"id": "competition", "name": "Competitive Landscape", "content": "Major players, market share, competitive dynamics"},
                {"id": "trend", "name": "Development Trends", "content": "Technology trends, market trends, growth forecast"},
                {"id": "conclusion", "name": "Research Conclusion", "content": "Core views, recommendations"},
            ]
        else:
            return [
                {"id": "summary", "name": "Executive Summary", "content": "Research background, key findings"},
                {"id": "overview", "name": "Market Overview", "content": "Market size, major players"},
                {"id": "conclusion", "name": "Research Conclusion", "content": "Core views, recommendations"},
            ]
    
    def confirm_sections(self, confirmed: bool = True, adjustments: List[Dict] = None) -> Dict[str, Any]:
        """After user confirms sections — return dynamic parameters based on output_type"""
        if adjustments:
            # Apply user adjustments
            self.current_choice.selected_sections = [a.get("id") for a in adjustments if a.get("keep", True)]
        
        # NEW: get parameters by output type
        params = self._get_interaction_parameters(self.current_choice.output_type)
        # Localize
        params = self._localize_params(params)
        
        result = {
            "step": 4,
            "message": "Sections confirmed",
            "instruction": "Please confirm research parameters:",
            "parameters": params,  # ← no longer hardcoded
            "next_step": "confirm_parameters"
        }
        
        # Keep compatibility fields (CLI legacy code needs these)
        if "parameters" in params:
            param_list = params["parameters"]
            for p in param_list:
                if p["id"] in ("region", "time_range", "depth"):
                    result[p["id"]] = {
                        "default": p.get("default", ""),
                        "options": [o["value"] for o in p.get("options", [])],
                    }
        
        return result
    
    def confirm_parameters(self, **kwargs) -> Dict[str, Any]:
        """Confirm research parameters — supports arbitrary parameter names"""
        # Save parameters to dynamic_fields
        for key, value in kwargs.items():
            self.current_choice.dynamic_fields[key] = value
        
        # Special handling for known fields to maintain backward compatibility
        if "region" in kwargs:
            self.current_choice.region = kwargs["region"]
        if "time_range" in kwargs:
            self.current_choice.time_range = kwargs["time_range"]
        
        summary = self._generate_summary()
        
        return {
            "step": 5,
            "message": "Parameters confirmed",
            "summary": summary,
            "instruction": "Confirm to start research?",
            "next_step": "confirm_research"
        }
    
    def select_template(self, template_id: str) -> Dict[str, Any]:
        """After user selects content template"""
        template = self.TEMPLATES.get(template_id)
        if not template:
            return {"error": "Template not found"}
        
        self.current_choice.template_id = template_id
        self.current_choice.selected_sections = [
            s["id"] for s in template.sections if s.get("required", False)
        ]
        if template.supported_formats:
            self.current_choice.output_format = template.supported_formats[0]
        
        return {
            "step": 3,
            "message": f"Selected template: {template.name}",
            "instruction": "Please adjust sections and output format:",
            "sections": template.sections,
            "format_options": [f.value for f in template.supported_formats],
            "next_step": "customize_sections"
        }
    
    def customize_sections(self, selected_sections: List[str], output_format: str = None) -> Dict[str, Any]:
        """After user adjusts sections — use dynamic parameters"""
        self.current_choice.selected_sections = selected_sections
        if output_format:
            self.current_choice.output_format = OutputFormat(output_format)
        
        # NEW: use dynamic parameters
        params = self._get_interaction_parameters(self.current_choice.output_type)
        params = self._localize_params(params)
        
        return {
            "step": 4,
            "message": "Sections adjusted",
            "instruction": "Please configure parameters:",
            "parameters": params,
            "next_step": "set_parameters"
        }
    
    def set_parameters(self, region: str, time_range: str, depth: str, focus_areas: str = "") -> Dict[str, Any]:
        """After user sets parameters"""
        self.current_choice.region = region
        self.current_choice.time_range = time_range
        self.current_choice.depth = depth
        if focus_areas:
            self.current_choice.focus_areas = focus_areas.split(",")
        
        return {
            "step": 5,
            "message": "Parameters configured",
            "instruction": "Would you like to add survey data support?",
            "survey_options": {
                "include_survey": {"options": [True, False], "default": False, "label": "Include survey"},
                "survey_mode": {"options": ["ai_simulation", "third_party"], "default": "ai_simulation", "label": "Survey method"},
                "survey_target_count": {"options": [50, 100, 200, 500], "default": 100, "label": "Target sample size"},
            },
            "next_step": "configure_survey"
        }
    
    def configure_survey(
        self, 
        include_survey: bool = False,
        survey_mode: str = "ai_simulation",
        survey_target_count: int = 100,
        survey_timeout_days: int = 7,
    ) -> Dict[str, Any]:
        """Configure survey parameters"""
        self.current_choice.include_survey = include_survey
        self.current_choice.survey_mode = survey_mode
        self.current_choice.survey_target_count = survey_target_count
        self.current_choice.survey_timeout_days = survey_timeout_days
        
        summary = self._generate_summary()
        
        return {
            "step": 6,
            "message": "Survey configured" if include_survey else "Survey skipped",
            "summary": summary,
            "survey_config": {
                "include_survey": include_survey,
                "survey_mode": survey_mode if include_survey else None,
                "survey_target_count": survey_target_count if include_survey else None,
            },
            "next_step": "confirm"
        }
    
    def confirm(self, confirmed: bool) -> Dict[str, Any]:
        """User final confirmation"""
        if not confirmed:
            return {"step": 5, "message": "Cancelled"}
        
        self.current_choice.confirmed = True
        template = self.TEMPLATES.get(self.current_choice.template_id)
        
        final_plan = {
            "topic": self.current_choice.topic,
            "output_type": self.current_choice.output_type.value,
            "content_template": template.name if template else "Custom",
            "sections": self.current_choice.selected_sections,
            "format": self.current_choice.output_format.value,
            "region": self.current_choice.region,
            "time_range": self.current_choice.time_range,
            "depth": self.current_choice.depth,
        }
        
        # Add survey config
        if self.current_choice.include_survey:
            final_plan["survey"] = {
                "include": True,
                "mode": self.current_choice.survey_mode,
                "target_count": self.current_choice.survey_target_count,
                "timeout_days": self.current_choice.survey_timeout_days,
            }
        
        return {
            "step": 7,
            "message": "Requirements confirmed",
            "final_plan": final_plan,
            "next_step": "execute"
        }
    
    def get_final_requirement(self) -> Optional[UserChoice]:
        """Get final requirement"""
        return self.current_choice if self.current_choice and self.current_choice.confirmed else None
    
    def reload_templates(self) -> Dict[str, Any]:
        """Reload content templates (runtime update)"""
        templates = self._template_loader.reload_templates()
        return {
            "success": True,
            "message": f"Reloaded {len(templates)} content templates",
            "templates": list(templates.keys())
        }
    
    def _get_output_type_options(self) -> List[Dict]:
        """Get output type options"""
        return [
            {"value": OutputType.INDUSTRY_REPORT.value, "label": "[Industry] Industry Research Report", "desc": "20-30 pages"},
            {"value": OutputType.INDUSTRY_WEEKLY.value, "label": "[Weekly] Industry Weekly", "desc": "3-8 pages"},
            {"value": OutputType.COMPANY_RESEARCH.value, "label": "[Company] Company Deep Dive", "desc": "15-40 pages"},
            {"value": OutputType.QUARTERLY_COMMENTARY.value, "label": "[Quarterly] Quarterly Commentary", "desc": "8-15 pages"},
            {"value": OutputType.ANNUAL_ANALYSIS.value, "label": "[Annual] Annual Analysis", "desc": "20-50 pages"},
            {"value": OutputType.CONFERENCE_CALL.value, "label": "[Meeting] Conference Call Report", "desc": "5-12 pages"},
            {"value": OutputType.COMMERCIAL_PLAN.value, "label": "[Plan] Business Plan", "desc": "30-50 pages"},
            {"value": OutputType.PITCH_DECK.value, "label": "[PPT] Pitch Deck", "desc": "10-15 pages"},
            {"value": OutputType.INVESTMENT_MEMO.value, "label": "[Memo] Investment Memo", "desc": "10-20 pages"},
            {"value": OutputType.COMPETITOR_ANALYSIS.value, "label": "[Competitor] Competitive Analysis", "desc": "8-15 pages"},
            {"value": OutputType.POLICY_BRIEF.value, "label": "[Policy] Policy Brief", "desc": "10-15 pages"},
            {"value": OutputType.MARKET_BRIEF.value, "label": "[Brief] Market Brief", "desc": "1-2 pages"},
            {"value": OutputType.CUSTOM.value, "label": "[Custom]", "desc": "Fully customizable"},
        ]
    
    def _generate_summary(self) -> Dict[str, Any]:
        """Generate summary dict"""
        if not self.current_choice:
            return {}
        
        template = self.TEMPLATES.get(self.current_choice.template_id)
        
        return {
            "topic": self.current_choice.topic,
            "output_type": self.current_choice.output_type.value if hasattr(self.current_choice.output_type, 'value') else str(self.current_choice.output_type),
            "output_format": self.current_choice.output_format.value if hasattr(self.current_choice.output_format, 'value') else str(self.current_choice.output_format),
            "template_name": template.name if template else "Custom",
            "sections": self.current_choice.selected_sections,
            "region": self.current_choice.region,
            "time_range": self.current_choice.time_range,
        }


# Convenience functions
def start_smart_clarification(user_input: str) -> Dict[str, Any]:
    """Start smart clarification process"""
    clarifier = SmartClarifier()
    return clarifier.start(user_input)


__all__ = [
    # Core classes
    "SmartClarifier",
    "TemplateLoader",
    # Enums
    "OutputType",
    "OutputFormat",
    "QuestionType",
    # Data classes
    "Template",
    "ResearchRequirement",
    "UserChoice",
    "Question",
    # Convenience functions
    "start_smart_clarification",
    # Path constants
    "TEMPLATE_CONFIG_DIR",
    "TEMPLATE_CUSTOM_DIR",
]
