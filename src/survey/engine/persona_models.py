"""Persona V2 Data Model - 20+ field persona."""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum


class PersonaType(Enum):
    CONSUMER = "consumer"
    EXPERT = "expert"
    HYBRID = "hybrid"


class PromptLevel(Enum):
    MINIMAL = "minimal"
    STANDARD = "standard"
    ENHANCED = "enhanced"
    FULL = "full"


@dataclass
class PersonaV2:
    persona_id: str
    persona_type: PersonaType = PersonaType.CONSUMER
    template_name: str = ""
    name: str = ""
    age: int = 30
    gender: str = "Male"
    city: str = "Beijing"
    occupation: str = ""
    income: str = ""
    education: str = "Bachelor"
    personality_traits: List[str] = field(default_factory=list)
    interests: List[str] = field(default_factory=list)
    values: List[str] = field(default_factory=list)
    decision_style: str = "Rational"
    background_story: str = ""
    contradictions: List[str] = field(default_factory=list)
    consumption_habits: List[str] = field(default_factory=list)
    brand_preferences: Dict[str, str] = field(default_factory=dict)
    price_sensitivity: float = 0.5
    channel_preference: List[str] = field(default_factory=list)
    digital_literacy: float = 0.5
    purchase_frequency: str = "medium"
    industry: str = ""
    expertise_domain: str = ""
    years_experience: int = 0
    analytical_framework: str = ""
    opinion_orientation: str = "balanced"
    reputation_level: str = "medium"
    big_five: Dict[str, float] = field(default_factory=lambda: {
        "openness": 5.0, "conscientiousness": 5.0,
        "extraversion": 5.0, "agreeableness": 5.0, "neuroticism": 5.0})
    risk_tolerance: float = 0.5
    cognitive_style: str = "balanced"
    social_influence: str = "follower"
    created_at: str = ""

    def to_prompt(self, style="interview"):
        if style == "interview":
            return self._interview_prompt()
        elif style == "profile":
            return self._profile_prompt()
        return self._minimal_prompt()

    def _interview_prompt(self):
        lines = [f"Name: {self.name}, {self.age}yo, {self.gender}"]
        lines.append(
            f"Job: {
                self.occupation}, City: {
                self.city}, Edu: {
                self.education}, Income: {
                    self.income}")
        if self.persona_type in (PersonaType.CONSUMER, PersonaType.HYBRID):
            habits = ",".join(self.consumption_habits[:3]) or "-"
            ps = "H" if self.price_sensitivity > 0.6 else "M" if self.price_sensitivity > 0.3 else "L"
            dl = "H" if self.digital_literacy > 0.6 else "M" if self.digital_literacy > 0.3 else "L"
            lines.append(
                f"Consumption: {habits}, PriceSensitivity={ps}, DigitalLiteracy={dl}")
        if self.persona_type in (PersonaType.EXPERT, PersonaType.HYBRID):
            lines.append(
                f"Expertise: {
                    self.expertise_domain}, {
                    self.years_experience}yr, Framework: {
                    self.analytical_framework}")
        traits = ",".join(self.personality_traits[:4]) or "-"
        lines.append(f"Personality: {traits}, Decision: {self.decision_style}")
        return "\n".join(lines)

    def _profile_prompt(self):
        chunks = [
            f"You are a {
                self.age}yo {
                self.gender} living in {
                self.city}, working as {
                    self.occupation}."]
        if self.background_story:
            chunks.append(self.background_story[:200])
        return "\n".join(chunks)

    def _minimal_prompt(self):
        return f"{
            self.name}, {
            self.age}yo, {
            self.gender}, {
                self.city}, {
                    self.occupation}"

    def to_dict(self):
        d = {k: v for k, v in self.__dict__.items()}
        d["persona_type"] = self.persona_type.value
        return d

    def to_legacy_dict(self):
        return {
            "persona_id": self.persona_id,
            "name": self.name,
            "age": self.age,
            "gender": self.gender,
            "city": self.city,
            "occupation": self.occupation,
            "income": self.income,
            "education": self.education,
            "personality_traits": self.personality_traits,
            "interests": self.interests,
            "values": self.values,
            "decision_style": self.decision_style,
            "background_story": self.background_story}

    @classmethod
    def from_dict(cls, data):
        data = dict(data)
        pt = data.pop("persona_type", "consumer")
        data["persona_type"] = PersonaType(pt) if isinstance(pt, str) else pt
        return cls(**{k: v for k, v in data.items()
                   if k in cls.__dataclass_fields__})
