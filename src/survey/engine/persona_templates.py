"""
Persona Template Registry

12 Chinese templates (6 consumer + 6 expert) + 6 English multi-country templates.
Each template contains demographic parameters, attribute association rules, and LLM prompt context.

Cities in Chinese templates are classified per GaWC 2024 (https://gawc.lboro.ac.uk/).
Occupations follow ISCO-08 skill levels (https://isco.ilo.org/).
Income/education distributions reference UN WPP 2024 and World Bank data.
"""

from typing import Dict, Any, List, Optional
from .persona_models import PersonaType


class PersonaTemplateRegistry:
    """Persona Template Registry"""

    CONSUMER_TEMPLATES: Dict[str, Dict[str, Any]] = {
        "一线白领": {
            "name": "Tier-1 City White-Collar Consumer",
            "description": "25-40, tier-1 cities, high income, quality-conscious",
            "persona_type": "consumer",
            "params": {
                "age_range": (25, 40),
                "cities": ["Beijing", "Shanghai", "Guangzhou", "Shenzhen"],
                "occupations": [
                    "Software Engineer", "Product Manager", "Marketing Manager", "Financial Accountant", "HR",
                    "Investment Advisor", "Designer", "Data Analyst", "Operations Manager",
                ],
                "income_range": ("200K-400K", "400K-600K"),
                "education": ["Bachelor", "Master", "PhD"],
                "traits": ["Rational consumption", "Quality-focused", "Time-sensitive", "High brand awareness"],
                "consumption": ["Online shopping oriented", "Quality consumption", "Experience consumption", "Membership consumption"],
            },
            "llm_context": "Highly educated, high-income tier-1 city white-collar workers focused on quality of life and efficiency",
        },
        "二三线家庭": {
            "name": "Tier-2/3 City Family User",
            "description": "30-50, tier-2/3 cities, family-oriented consumption",
            "persona_type": "consumer",
            "params": {
                "age_range": (30, 50),
                "cities": ["Chengdu", "Hangzhou", "Wuhan", "Xi'an", "Nanjing", "Chongqing", "Changsha", "Suzhou"],
                "occupations": ["Teacher", "Civil Servant", "Sales Manager", "Self-employed", "Engineer", "Doctor"],
                "income_range": ("100K-200K", "150K-300K"),
                "education": ["Associate", "Bachelor"],
                "traits": ["Pragmatic consumption", "Price-sensitive", "Family-oriented", "Community trust"],
                "consumption": ["Online-offline hybrid", "Family procurement oriented", "Promotion-sensitive", "Word-of-mouth driven"],
            },
            "llm_context": "Second-tier city family users, consumption decisions centered on family needs",
        },
        "下沉市场用户": {
            "name": "Down-Market Consumer",
            "description": "Third/fourth-tier cities and towns, price-sensitive, acquaintance-based social networking",
            "persona_type": "consumer",
            "params": {
                "age_range": (25, 55),
                "cities": [
                    "Baoding", "Linyi", "Luoyang", "Zunyi", "Jingzhou",
                    "Mianyang", "Ganzhou", "Wuhu", "Yueyang", "Qujing",
                ],
                "occupations": ["Self-employed", "Salesperson", "Worker", "Driver", "Civil Servant", "Teacher"],
                "income_range": ("30K-50K", "50K-100K"),
                "education": ["Middle School", "High School", "Associate"],
                "traits": ["Price-sensitive", "Peer recommendation", "Pragmatic consumption", "Low brand loyalty", "Offline trust"],
                "consumption": ["Offline shopping oriented", "Social commerce", "Group buying", "Market shopping"],
            },
            "llm_context": "Third and fourth-tier city residents, middle income, value-for-money oriented consumption",
        },
        "Z世代学生": {
            "name": "Gen Z Student Group",
            "description": "18-24, enrolled students, socially driven consumption",
            "persona_type": "consumer",
            "params": {
                "age_range": (18, 24),
                "cities": ["Beijing", "Shanghai", "Guangzhou", "Nanjing", "Wuhan", "Chengdu", "Xi'an"],
                "occupations": ["College Student", "Graduate Student", "Fresh Graduate", "Intern"],
                "income_range": ("10K-30K", "30K-50K"),
                "education": ["Bachelor's Student", "Master's Student"],
                "traits": ["Socially driven", "Aesthetics-first", "Subculture engagement", "Sustainability-minded"],
                "consumption": ["Social media influence", "Guochao preference", "Second-hand trading", "Virtual consumption"],
            },
            "llm_context": "Young student demographic, consumption heavily influenced by social trends and focused on personal expression",
        },
        "高净值人群": {
            "name": "High-Net-Worth Consumer",
            "description": "35-60, high assets, quality-first",
            "persona_type": "consumer",
            "params": {
                "age_range": (35, 60),
                "cities": ["Beijing", "Shanghai", "Shenzhen", "Guangzhou", "Hangzhou"],
                "occupations": [
                    "Business Owner", "Executive", "Investor", "Lawyer",
                    "Senior Doctor", "Senior Consultant", "Finance Professional",
                ],
                "income_range": ("1M+", "5M+"),
                "education": ["Bachelor", "Master", "PhD"],
                "traits": ["Quality-first", "Private service", "Customization needs", "High brand loyalty", "High time value"],
                "consumption": ["Private customization", "Membership consumption", "Overseas shopping", "Health investment"],
            },
            "llm_context": "High-net-worth individuals who prioritize quality and uniqueness in their consumption decisions and are price-insensitive",
        },
        "银发族": {
            "name": "Senior Consumer",
            "description": "60-80, retired, health-conscious",
            "persona_type": "consumer",
            "params": {
                "age_range": (60, 80),
                "cities": ["Beijing", "Shanghai", "Guangzhou", "Chengdu", "Nanjing", "Wuhan"],
                "occupations": ["Retired", "Rehired Expert", "Community Worker"],
                "income_range": ("30K-50K", "50K-100K"),
                "education": ["Middle School", "High School", "Associate"],
                "traits": ["Health-conscious", "Frugal habits", "Offline trust", "Low digital literacy", "Community-dependent"],
                "consumption": ["Health product consumption", "Offline shopping", "TV shopping", "Community group buying"],
            },
            "llm_context": "Retired elderly population, consumption centered on health and daily convenience",
        },
    }

    EXPERT_TEMPLATES: Dict[str, Dict[str, Any]] = {
        "行业分析师": {
            "name": "Industry Analyst",
            "description": "30-55, professional market research/consulting background",
            "persona_type": "expert",
            "params": {
                "age_range": (30, 55),
                "cities": ["Beijing", "Shanghai", "Shenzhen"],
                "occupations": [
                    "Market Research Director", "Industry Analyst", "Strategy Consultant",
                    "Chief Analyst", "Consulting Manager",
                ],
                "domains": ["New Energy", "Semiconductors", "Healthcare", "Consumer Retail", "Fintech"],
                "frameworks": ["PEST Analysis", "Porter's Five Forces", "SWOT", "BCG Matrix", "Value Chain Analysis"],
                "years_experience": (5, 20),
                "traits": ["Data-driven", "Macro perspective", "Logical rigor", "Trend-sensitive"],
            },
            "llm_context": "Professional market research background, skilled in macro analysis and competitive landscape assessment, data-supported insights",
        },
        "企业高管": {
            "name": "Corporate Executive",
            "description": "40-60, enterprise decision-maker, strategic perspective",
            "persona_type": "expert",
            "params": {
                "age_range": (40, 60),
                "cities": ["Beijing", "Shanghai", "Shenzhen", "Guangzhou", "Hangzhou"],
                "occupations": [
                    "CEO", "Vice President", "Business Unit General Manager",
                    "Chief Strategy Officer", "Board Member",
                ],
                "domains": ["Technology", "Manufacturing", "Consumer", "Finance", "Energy"],
                "frameworks": ["ROI Analysis", "Growth Strategy", "Competitive Strategy", "Organizational Management"],
                "years_experience": (15, 30),
                "traits": ["Strategic thinking", "Results-oriented", "Risk awareness", "Resource integration"],
            },
            "llm_context": "Senior enterprise managers focused on macro trends, competitive dynamics, and business opportunities",
        },
        "技术专家": {
            "name": "Technology Expert",
            "description": "30-50, technology domain authority",
            "persona_type": "expert",
            "params": {
                "age_range": (30, 50),
                "cities": ["Beijing", "Shanghai", "Shenzhen", "Hangzhou"],
                "occupations": [
                    "CTO", "VP of Engineering", "Chief Architect",
                    "R&D Director", "Senior Engineer",
                ],
                "domains": ["AI/ML", "Cloud Computing", "Chip Design", "Autonomous Driving", "IoT"],
                "frameworks": ["Technology Roadmap", "Architecture Review", "Technical Feasibility", "Performance Benchmarking"],
                "years_experience": (8, 20),
                "traits": ["Technical depth", "Innovation-oriented", "Pragmatism", "Frontier tracking"],
            },
            "llm_context": "Technology domain expert, skilled in technology roadmap assessment and feasibility evaluation",
        },
        "政策研究员": {
            "name": "Policy Researcher",
            "description": "30-55, policy analysis background",
            "persona_type": "expert",
            "params": {
                "age_range": (30, 55),
                "cities": ["Beijing", "Shanghai"],
                "occupations": [
                    "Policy Researcher", "Government Affairs Director", "Regulatory Advisor",
                    "Think Tank Scholar", "Public Policy Advisor",
                ],
                "domains": ["Industrial Policy", "Environmental Policy", "Digital Economy", "Trade Policy", "Technology Innovation"],
                "frameworks": ["Policy Evaluation", "Cost-Benefit Analysis", "Regulatory Impact Analysis", "Comparative Institutional Analysis"],
                "years_experience": (5, 25),
                "traits": ["Policy-sensitive", "Institutional perspective", "Balanced thinking", "Forward-looking"],
            },
            "llm_context": "Policy research background, familiar with policy-making processes and regulatory frameworks",
        },
        "一线从业者": {
            "name": "Frontline Practitioner",
            "description": "25-45, industry practitioner",
            "persona_type": "expert",
            "params": {
                "age_range": (25, 45),
                "cities": ["Beijing", "Shanghai", "Guangzhou", "Shenzhen", "Hangzhou", "Wuhan"],
                "occupations": [
                    "Product Manager", "Operations Director", "Sales Director",
                    "Project Manager", "Procurement Manager",
                ],
                "domains": ["Internet", "Consumer Goods", "Manufacturing", "Retail", "Logistics"],
                "frameworks": ["Agile Management", "OKR", "User Persona", "Supply Chain Management"],
                "years_experience": (3, 15),
                "traits": ["Hands-on experience", "Pain-point sensitive", "Efficiency-oriented", "Practical"],
            },
            "llm_context": "Frontline business operators understanding actual industry operations and real user feedback",
        },
        "学术研究者": {
            "name": "Academic Researcher",
            "description": "30-60, professor/researcher",
            "persona_type": "expert",
            "params": {
                "age_range": (30, 60),
                "cities": ["Beijing", "Shanghai", "Hong Kong", "Nanjing", "Wuhan", "Guangzhou"],
                "occupations": [
                    "Professor", "Researcher", "Postdoctoral Researcher",
                    "Lab Director", "Academic Lead",
                ],
                "domains": ["Economics", "Sociology", "Management", "Computer Science", "Public Policy"],
                "frameworks": ["Empirical Research", "Econometric Analysis", "Case Study", "Theoretical Modeling", "Randomized Experiment"],
                "years_experience": (5, 30),
                "traits": ["Theoretical foundation", "Methodological rigor", "Solid literature", "Critical thinking"],
            },
            "llm_context": "Academic researcher with focus on methodological rigor and theoretical contribution",
        },
    }

    # Consistency constraint rules
    CONSISTENCY_RULES = [
        # Income vs price sensitivity
        {"if": {"income": ["Below 50K", "30K-50K", "10K-30K"]},
            "then": {"price_sensitivity": (0.7, 1.0)}},
        {"if": {"income": ["50K-100K", "100K-200K", "150K-300K"]},
            "then": {"price_sensitivity": (0.4, 0.7)}},
        {"if": {"income": ["200K-400K", "300K-500K", "400K-600K", "1M+",
                           "5M+"]}, "then": {"price_sensitivity": (0.1, 0.4)}},
        # Age vs digital literacy
        {"if": {"age": (18, 30)}, "then": {"digital_literacy": (0.7, 1.0)}},
        {"if": {"age": (30, 50)}, "then": {"digital_literacy": (0.4, 0.8)}},
        {"if": {"age": (50, 100)}, "then": {"digital_literacy": (0.1, 0.5)}},
        # Expert persona -> low price sensitivity
        {"if": {"persona_type": "expert"}, "then": {
            "price_sensitivity": (0.1, 0.4)}},
    ]

    # ---------------------------------------------------------------- #
    # Multi-country templates (English)
    # ---------------------------------------------------------------- #
    GLOBAL_CONSUMER_TEMPLATES: Dict[str, Dict[str, Any]] = {
        "us_urban_professional": {
            "name": "US Urban Professional",
            "description": "25-45, US metro areas, college-educated, high income",
            "persona_type": "consumer",
            "region": "usa",
            "params": {
                "age_range": (25, 45),
                "cities": ["New York", "San Francisco", "Los Angeles", "Chicago", "Boston", "Seattle", "Washington DC"],
                "occupations": ["Software Engineer", "Product Manager", "Consultant", "Marketing Director", "Data Scientist", "Financial Analyst", "Business Development Manager"],
                "income_range": ("$80k-$120k", "$120k-$200k"),
                "education": ["Bachelor", "Master", "PhD"],
                "traits": ["Quality-conscious", "Brand-aware", "Time-sensitive", "Digital-native", "Sustainability-minded"],
                "consumption": ["Online shopping", "Subscription services", "Premium brands", "Experience-based spending", "Delivery apps"],
            },
            "llm_context": "High-income US urban professional, values convenience, quality, and brand reputation",
        },
        "us_suburban_family": {
            "name": "US Suburban Family",
            "description": "30-50, suburbs, household-oriented, value-conscious",
            "persona_type": "consumer",
            "region": "usa",
            "params": {
                "age_range": (30, 50),
                "cities": ["Dallas", "Atlanta", "Phoenix", "Denver", "Minneapolis", "Portland", "Charlotte", "Tampa"],
                "occupations": ["Teacher", "Nurse", "Sales Manager", "Accountant", "Engineer", "Small Business Owner", "Real Estate Agent"],
                "income_range": ("$60k-$90k", "$90k-$130k"),
                "education": ["Associate", "Bachelor", "Master"],
                "traits": ["Value-conscious", "Family-oriented", "Brand-loyal", "Community-trusting", "Deal-seeking"],
                "consumption": ["Warehouse clubs", "Online-to-offline", "Subscription boxes", "Family dining", "Home improvement"],
            },
            "llm_context": "US suburban family consumer, budget-aware, relies on peer recommendations and trusted brands",
        },
        "european_urban_consumer": {
            "name": "European Urban Consumer",
            "description": "25-50, major EU cities, quality-of-life focused",
            "persona_type": "consumer",
            "region": "deu",
            "params": {
                "age_range": (25, 50),
                "cities": ["Berlin", "Munich", "Hamburg", "London", "Paris", "Amsterdam", "Stockholm", "Copenhagen"],
                "occupations": ["Engineer", "Product Manager", "Researcher", "Consultant", "Architect", "Healthcare Professional", "Marketing Manager"],
                "income_range": ("\u20ac45k-\u20ac65k", "\u20ac65k-\u20ac100k"),
                "education": ["Bachelor", "Master", "PhD"],
                "traits": ["Quality-of-life focused", "Sustainability-driven", "Privacy-conscious", "Work-life balance", "Brand-skeptical"],
                "consumption": ["Local & organic", "Public transport", "Second-hand", "Digital services", "Travel & experiences"],
            },
            "llm_context": "European urban consumer with high environmental awareness, values sustainability and quality of life over conspicuous consumption",
        },
        "japan_urban_consumer": {
            "name": "Japan Urban Consumer",
            "description": "25-50, Japanese metro areas, quality and service focused",
            "persona_type": "consumer",
            "region": "jpn",
            "params": {
                "age_range": (25, 50),
                "cities": ["Tokyo", "Osaka", "Yokohama", "Nagoya", "Sapporo", "Fukuoka", "Kyoto"],
                "occupations": ["Salaryman", "Engineer", "Marketing Specialist", "Researcher", "Healthcare Worker", "IT Manager", "Administrative Manager"],
                "income_range": ("\u00a55M-\u00a58M", "\u00a58M-\u00a512M"),
                "education": ["Bachelor", "Master"],
                "traits": ["Quality-obsessed", "Brand-loyal", "Service-expectant", "Group-conformity", "Detail-oriented"],
                "consumption": ["Convenience stores", "Department stores", "Online marketplaces", "Seasonal gifting", "Dining out"],
            },
            "llm_context": "Japan metro consumer, high expectations for product quality and customer service, values trust and brand heritage",
        },
    }

    GLOBAL_EXPERT_TEMPLATES: Dict[str, Dict[str, Any]] = {
        "global_industry_analyst": {
            "name": "Global Industry Analyst",
            "description": "35-55, professional research/consulting, global perspective",
            "persona_type": "expert",
            "region": "usa",
            "params": {
                "age_range": (35, 55),
                "cities": ["New York", "London", "Singapore", "San Francisco", "Hong Kong"],
                "occupations": ["Industry Analyst", "Strategy Consultant", "Market Research Director", "Investment Analyst", "Economic Advisor"],
                "domains": ["Technology", "Healthcare", "Consumer Markets", "Financial Services", "Energy", "Manufacturing"],
                "frameworks": ["Porter's Five Forces", "SWOT Analysis", "PESTLE", "BCG Matrix", "Scenario Planning"],
                "years_experience": (8, 25),
                "traits": ["Data-driven", "Global perspective", "Cross-cultural", "Forward-looking", "Evidence-based"],
            },
            "llm_context": "Global market research professional with cross-border perspective, comfortable with multi-market analysis",
        },
        "global_tech_expert": {
            "name": "Global Technology Expert",
            "description": "30-55, technology leader with international experience",
            "persona_type": "expert",
            "region": "usa",
            "params": {
                "age_range": (30, 55),
                "cities": ["San Francisco", "Seattle", "Boston", "London", "Berlin", "Tokyo", "Shenzhen"],
                "occupations": ["CTO", "VP Engineering", "Chief Architect", "R&D Director", "Senior Engineer", "AI Research Scientist"],
                "domains": ["AI/ML", "Cloud Computing", "Semiconductors", "Autonomous Systems", "IoT", "Cybersecurity"],
                "frameworks": ["Technology Roadmap", "Architecture Review", "Technical Feasibility", "Patent Analysis", "R&D Benchmarking"],
                "years_experience": (8, 25),
                "traits": ["Deep-tech knowledge", "Innovation-driven", "Global R&D awareness", "Cross-border collaboration", "Open-source minded"],
            },
            "llm_context": "Global technology expert with cross-market technical knowledge, experienced in international R&D and product development",
        },
    }

    # ---------------------------------------------------------------- #
    # API
    # ---------------------------------------------------------------- #
    @classmethod
    def get_template(cls, name: str, persona_type: str = "consumer") -> Optional[Dict]:
        """Get a template by name, searching both local and global templates."""
        pool = cls.CONSUMER_TEMPLATES if persona_type == "consumer" else cls.EXPERT_TEMPLATES
        tpl = pool.get(name)
        if tpl:
            return tpl
        # Fallback to global templates
        global_pool = cls.GLOBAL_CONSUMER_TEMPLATES if persona_type == "consumer" else cls.GLOBAL_EXPERT_TEMPLATES
        return global_pool.get(name)

    @classmethod
    def list_templates(cls, persona_type: Optional[str] = None, include_global: bool = True) -> List[Dict]:
        """List all templates, optionally filtered by type."""
        result = []
        if persona_type in (None, "consumer"):
            for k, v in cls.CONSUMER_TEMPLATES.items():
                result.append({"id": k, **v})
            if include_global:
                for k, v in cls.GLOBAL_CONSUMER_TEMPLATES.items():
                    result.append({"id": k, **v})
        if persona_type in (None, "expert"):
            for k, v in cls.EXPERT_TEMPLATES.items():
                result.append({"id": k, **v})
            if include_global:
                for k, v in cls.GLOBAL_EXPERT_TEMPLATES.items():
                    result.append({"id": k, **v})
        return result

    @classmethod
    def get_consistency_rules_for(cls, persona_type: str, income: str = "", age: int = 30) -> List[Dict]:
        """Get applicable consistency rules based on persona attributes."""
        matched = []
        for rule in cls.CONSISTENCY_RULES:
            cond = rule["if"]
            match = True
            if "income" in cond and income not in cond["income"]:
                match = False
            if isinstance(cond.get("age"), tuple) and not (cond["age"][0] <= age <= cond["age"][1]):
                match = False
            if "persona_type" in cond and persona_type != cond["persona_type"]:
                match = False
            if match:
                matched.append(rule)
        return matched
