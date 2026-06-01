"""LLM-enhanced persona generator."""
import asyncio, json, logging, random, re
from typing import Dict, Any, List, Optional, Tuple
from .persona_models import PersonaV2, PersonaType
from .persona_templates import PersonaTemplateRegistry
from .data import AGE_DISTRIBUTION, CITY_TIER_DISTRIBUTION, GENDER_DISTRIBUTION

logger = logging.getLogger(__name__)

_MAX_CONTEXT_LENGTH = 500
_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(above\s+)?instructions",
    r"system\s*:", r"you\s+are\s+(now|currently)\s+",
]


def sanitize_context(context, max_len=_MAX_CONTEXT_LENGTH):
    if not context:
        return ""
    safe = context.strip()[:max_len]
    for pat in _INJECTION_PATTERNS:
        safe = re.sub(pat, "[filtered]", safe, flags=re.IGNORECASE)
    return f"<context>{safe}</context>"


class PersonaGenerationError(Exception):
    pass


_SYSTEM_PROMPT = """You are a professional persona generator. Generate a persona with logical consistency.
Output JSON only with fields: name, age, gender, city, occupation, income, education,
personality_traits (list), interests (list), values (list), decision_style,
consumption_habits (list), brand_preferences (dict), price_sensitivity (0-1),
digital_literacy (0-1), risk_tolerance (0-1),
big_five (dict: openness, conscientiousness, extraversion, agreeableness, neuroticism),
background_story (300 chars)."""


class PersonaGeneratorV2:
    def __init__(self, llm_skill=None, random_seed: Optional[int] = None):
        self.llm_skill = llm_skill
        self._templates = PersonaTemplateRegistry()
        self._random_seed = random_seed
        if random_seed is not None:
            random.seed(random_seed)

    async def generate_batch(self, template_name, count, persona_type="consumer",
                             context=None, max_concurrent=5):
        template = self._templates.get_template(template_name, persona_type)
        if not template:
            raise PersonaGenerationError(f"Unknown template: {template_name}")
        params = template["params"]
        stats = {"total": 0, "llm_success": 0, "rule_fallback": 0, "filtered": 0}
        stats_lock = asyncio.Lock()
        safe_context = sanitize_context(context) if context else ""
        sem = asyncio.Semaphore(max_concurrent)

        async def gen_one(idx):
            async with sem:
                async with stats_lock:
                    stats["total"] += 1
                p = await self._generate_single_with_llm(params, persona_type, idx, safe_context)
                if p:
                    async with stats_lock:
                        stats["llm_success"] += 1
                    return p
                async with stats_lock:
                    stats["rule_fallback"] += 1
                return self._generate_with_rules(params, persona_type, idx, template_name)

        tasks = [gen_one(i) for i in range(count)]
        results = await asyncio.gather(*tasks)
        valid = [p for p in results if p is not None]
        stats["filtered"] = count - len(valid)
        logger.info(f"Persona gen: template={template_name}, total={count}, llm={stats['llm_success']}, rule={stats['rule_fallback']}")
        return valid, stats

    async def _generate_single_with_llm(self, params, persona_type, index, context):
        if not self.llm_skill:
            return None
        age = random.randint(*params["age_range"])
        gender = random.choices(["Male", "Female"], weights=[0.512, 0.488])[0]
        city = random.choice(params.get("cities", ["Beijing"]))
        prompt = f"Generate a persona for: {params.get('llm_context', '')}. Age:{age}, Gender:{gender}, City:{city}."
        if context:
            prompt += f" Research context: {context}"
        try:
            result = await asyncio.wait_for(
                self.llm_skill.execute(prompt=prompt, system_prompt=_SYSTEM_PROMPT,
                                       temperature=0.9, max_tokens=2048), timeout=30)
            if result.get("success"):
                data = json.loads(self._clean_json(result["content"]))
                return self._build_persona(data, params, persona_type, city, age, gender)
        except Exception as e:
            logger.warning(f"LLM persona gen failed: {e}")
        return None

    def _clean_json(self, content):
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)
        return content

    def _build_persona(self, data, params, persona_type, city, age, gender):
        ptype = PersonaType(persona_type)
        ps = data.get("price_sensitivity", 0.5)
        income = data.get("income", "")
        if not isinstance(income, str):
            income = str(income)
        if any(k in income for k in ["5wan", "3-5", "1-3"]):
            ps = max(ps, 0.7)
        dl = data.get("digital_literacy", 0.5)
        if age >= 60:
            dl = min(dl, 0.5)
        # Ensure string fields (LLM sometimes returns numbers)
        occupation = data.get("occupation", "")
        education = data.get("education", "Bachelor")
        if not isinstance(occupation, str):
            occupation = str(occupation)
        if not isinstance(education, str):
            education = str(education)

        return PersonaV2(
            persona_id=f"p_{persona_type}_{hash(str(data)) % 100000:05d}",
            persona_type=ptype, template_name=data.get("_template", ""),
            name=data.get("name", "Unknown"), age=age, gender=gender, city=city,
            occupation=occupation, income=income,
            education=education,
            personality_traits=data.get("personality_traits", []),
            interests=data.get("interests", []), values=data.get("values", []),
            decision_style=data.get("decision_style", "Rational"),
            background_story=data.get("background_story", ""),
            consumption_habits=data.get("consumption_habits", []),
            brand_preferences=data.get("brand_preferences", {}),
            price_sensitivity=ps, digital_literacy=dl,
            risk_tolerance=data.get("risk_tolerance", 0.5),
            big_five=data.get("big_five", {"openness": 5, "conscientiousness": 5,
                                            "extraversion": 5, "agreeableness": 5, "neuroticism": 5}))

    def _generate_with_rules(self, params, persona_type, index, template_name=""):
        age = random.randint(*params["age_range"])
        gender = random.choices(["Male", "Female"], weights=[0.512, 0.488])[0]
        city = random.choice(params.get("cities", ["Beijing"]))
        occ = random.choice(params.get("occupations", [""]))
        edu = random.choice(params.get("education", ["Bachelor"]))
        inc = random.choice(params.get("income_range", ("50k-100k", "100k-200k")))
        traits = random.sample(params.get("traits", []) + ["Outgoing", "Reserved", "Rational", "Emotional"],
                               k=min(3, len(params.get("traits", [])) + 3))
        return PersonaV2(
            persona_id=f"p_{persona_type}_{index:04d}", persona_type=PersonaType(persona_type),
            template_name=template_name, name=f"Respondent{index+1:03d}",
            age=age, gender=gender, city=city, occupation=occ, income=inc, education=edu,
            personality_traits=traits, decision_style=random.choice(["Impulsive", "Research", "Cautious"]),
            interests=random.sample(["Tech", "Travel", "Food", "Sports", "Reading"], k=2),
            values=random.sample(["Family", "Career", "Health", "Wealth"], k=2),
            background_story=f"From {city}, works as {occ}, age {age}.",
            price_sensitivity=0.6 if "low" in inc.lower() else 0.4,
            digital_literacy=0.8 if age < 30 else (0.4 if age > 60 else 0.6))
