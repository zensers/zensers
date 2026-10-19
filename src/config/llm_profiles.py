from dataclasses import dataclass, field
from typing import Optional, Dict, List
import os
import yaml


@dataclass
class LLMProfile:
    name: str
    display_name: str = ""
    provider: str = "openai"
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o"
    fallback_model: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    max_context_tokens: int = 128000
    cost_limit_per_call: float = 0.0
    max_concurrency: int = 3
    is_default: bool = False
    enabled: bool = True
    created_at: str = ""
    updated_at: str = ""


@dataclass
class LLMProfileRegistry:
    profiles: Dict[str, LLMProfile] = field(default_factory=dict)
    default_profile: str = "mimo"
    fallback_chain: List[str] = field(default_factory=lambda: ["mimo", "deepseek", "local"])
    fixed_agent_routing: Dict[str, str] = field(default_factory=dict)
    action_routing: Dict[str, str] = field(default_factory=dict)


@dataclass
class RoutingHint:
    agent_type: Optional[str] = None
    action: Optional[str] = None
    profile_name: Optional[str] = None
    force_profile: bool = False


@dataclass
class CatalogProvider:
    id: str
    name: str
    description: str = ""
    default_endpoint: str = ""


@dataclass
class CatalogModel:
    id: str
    name: str
    provider: str
    max_tokens: int = 128000
    supports_vision: bool = False


def load_llm_catalog(catalog_path: str = "") -> Dict:
    if not catalog_path:
        catalog_path = os.path.join(os.path.dirname(__file__), "..", "..", "config", "llm_catalog.yaml")
    if not os.path.exists(catalog_path):
        return {"providers": {}, "models": []}
    with open(catalog_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    providers = {}
    for pid, pinfo in data.get("providers", {}).items():
        providers[pid] = CatalogProvider(
            id=pid,
            name=pinfo.get("name", pid),
            description=pinfo.get("description", ""),
            default_endpoint=pinfo.get("default_endpoint", ""),
        )
    models = []
    for m in data.get("models", []):
        models.append(CatalogModel(
            id=m.get("id", ""),
            name=m.get("name", m.get("id", "")),
            provider=m.get("provider", ""),
            max_tokens=m.get("max_tokens", 128000),
            supports_vision=m.get("supports_vision", False),
        ))
    return {"providers": providers, "models": models}
