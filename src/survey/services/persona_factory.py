"""
Persona Factory

Used to generate virtual respondent personas, supporting AI simulation mode.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import random


@dataclass
class Persona:
    """Persona"""
    persona_id: str
    name: str
    age: int
    gender: str
    city: str
    occupation: str
    income: str
    education: str
    personality_traits: List[str]
    interests: List[str]
    values: List[str]
    decision_style: str
    background_story: str = ""
    contradictions: List[str] = field(default_factory=list)
    
    def to_prompt(self) -> str:
        """Convert to LLM prompt"""
        return f"""
You are a survey respondent. Please answer the questionnaire based on the following persona profile:

【Basic Information】
Name: {self.name}
Age: {self.age}
Gender: {self.gender}
City: {self.city}
Occupation: {self.occupation}
Education: {self.education}
Income: {self.income}

【Personality Traits】
{', '.join(self.personality_traits)}

【Interests】
{', '.join(self.interests)}

【Values】
{', '.join(self.values)}

【Decision Style】
{self.decision_style}

【Background Story】
{self.background_story}

Always stay in character. Your answers should match this persona's characteristics.
Remember: real people have preferences, biases, and may even contradict themselves.
"""


class PersonaFactory:
    """Persona Factory"""
    
    # Predefined population templates
    POPULATION_TEMPLATES = {
        "white_collar": {
            "age_range": (25, 40),
            "cities": ["Beijing", "Shanghai", "Guangzhou", "Shenzhen"],
            "occupations": ["Software Engineer", "Product Manager", "Marketing Manager", "Accountant", "HR Manager"],
            "education": ["Bachelor", "Master"],
            "income_range": ("150k-300k", "200k-400k"),
            "traits": ["Rational", "Quality-oriented", "Time-sensitive"],
        },
        "suburban_family": {
            "age_range": (30, 50),
            "cities": ["Chengdu", "Hangzhou", "Wuhan", "Xi'an", "Nanjing"],
            "occupations": ["Teacher", "Civil Servant", "Salesperson", "Small Business Owner"],
            "education": ["High School", "Associate", "Bachelor"],
            "income_range": ("50k-100k", "100k-200k"),
            "traits": ["Pragmatic", "Price-sensitive", "Family-oriented"],
        },
    }
    
    # Name pools
    FIRST_NAMES_MALE = ["Wei Zhang", "Qiang Li", "Gang Wang", "Yang Liu", "Ming Chen", "Fan Yang", "Lei Zhao", "Jie Zhou"]
    FIRST_NAMES_FEMALE = ["Na Li", "Fang Wang", "Min Zhang", "Ting Liu", "Jing Chen", "Xue Yang", "Lin Zhao", "Li Zhou"]
    
    def __init__(self, llm_skill=None):
        self.llm_skill = llm_skill
    
    def generate_population(
        self,
        template_name: str,
        count: int,
        context: Optional[str] = None
    ) -> List[Persona]:
        """
        Generate population sample

        Args:
            template_name: Template name
            count: Count
            context: Context (e.g. "new energy vehicle purchase intention")
        """
        template = self.POPULATION_TEMPLATES.get(template_name)
        if not template:
            # Use default template
            template = self.POPULATION_TEMPLATES["white_collar"]
        
        personas = []
        for i in range(count):
            persona = self._generate_single(
                template,
                f"persona_{i}",
                context
            )
            personas.append(persona)
        
        return personas
    
    def _generate_single(
        self,
        template: Dict[str, Any],
        persona_id: str,
        context: Optional[str]
    ) -> Persona:
        """Generate a single persona"""
        
        # Randomly generate basic attributes
        age = random.randint(*template["age_range"])
        gender = random.choice(["Male", "Female"])
        city = random.choice(template["cities"])
        occupation = random.choice(template["occupations"])
        education = random.choice(template["education"])
        income = random.choice(template["income_range"])
        
        # Generate name
        if gender == "Male":
            name = random.choice(self.FIRST_NAMES_MALE)
        else:
            name = random.choice(self.FIRST_NAMES_FEMALE)
        
        # Generate personality traits
        personality_traits = random.sample(
            template["traits"] + ["Outgoing", "Introverted", "Rational", "Emotional", "Open-minded", "Conservative"],
            k=min(3, len(template["traits"]) + 6)
        )
        
        # Generate interests
        interests = random.sample(
            ["Technology", "Travel", "Food", "Sports", "Reading", "Music", "Movies", "Shopping"],
            k=random.randint(2, 4)
        )
        
        # Generate values
        values = random.sample(
            ["Family", "Career", "Health", "Wealth", "Freedom", "Stability"],
            k=random.randint(2, 3)
        )
        
        # Decision style
        decision_style = random.choice(["Impulsive", "Research-oriented", "Follows the crowd", "Cautious"])
        
        # Background story
        background_story = f"{name} is {age} years old, works as a {occupation} in {city}."
        
        return Persona(
            persona_id=persona_id,
            name=name,
            age=age,
            gender=gender,
            city=city,
            occupation=occupation,
            income=income,
            education=education,
            personality_traits=personality_traits,
            interests=interests,
            values=values,
            decision_style=decision_style,
            background_story=background_story,
        )
