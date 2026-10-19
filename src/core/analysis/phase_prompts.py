from typing import Optional


class PhasePrompts:
    def __init__(self):
        self._phases = ["data_collection", "data_validation", "deep_analysis", "synthesis", "report_generation"]

    def list_available_phases(self) -> list:
        return self._phases


def get_prompt_for_phase(phase: str, topic: str = "", aspect: str = "") -> str:
    return f"角色定义\n你是一个专业的研究分析师。\n主题: {topic}\n方面: {aspect}"
