import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from src.skills.base import Skill, SkillConfig
from src.core.memory import KnowledgeManager

logger = logging.getLogger(__name__)


class KnowledgeQuerySkill(Skill):
    def __init__(self, config: SkillConfig = None,
                 knowledge_manager: KnowledgeManager = None):
        super().__init__(config or SkillConfig(
            name="knowledge_query",
            version="1.0.0",
        ))
        self._km = knowledge_manager
        self._pending_observations: List[Dict] = []

    @property
    def name(self) -> str:
        return "knowledge_query"

    @property
    def description(self) -> str:
        return ("Query existing knowledge before analysis. "
                "Provides entity references, historical patterns, and analytical frameworks.")

    async def execute(self, **kwargs) -> Dict[str, Any]:
        action = kwargs.get("action")

        if action == "enrich":
            return await self._enrich(
                kwargs.get("topic", ""),
                kwargs.get("aspect", "")
            )
        elif action == "record_observation":
            return await self._record_observation(
                kwargs.get("content", ""),
                kwargs.get("category", "pattern")
            )

        return self._failure(f"Unknown action: {action}")

    def drain_observations(self) -> List[Dict]:
        old = self._pending_observations
        self._pending_observations = []
        return old

    async def _enrich(self, topic: str, aspect: str) -> Dict[str, Any]:
        if not self._km:
            return self._success({"data": {}}, "no knowledge manager")

        _match_frameworks = None
        try:
            from src.methodologies.registry import match_for_aspect as _match_frameworks
        except ImportError:
            pass

        async def _search_entities():
            result = self._km.search(topic, {"limit": 5})
            return result.get("entities", [])

        async def _query_patterns():
            cm = self._km.core_memory
            patterns = getattr(cm, 'learned_patterns', [])
            if not patterns:
                return []
            scored = [(self._relevance(p.content, topic), p) for p in patterns]
            scored.sort(key=lambda x: x[0], reverse=True)
            scored = [(s, p) for s, p in scored if s > 0.2]
            return [
                {"content": p.content, "recurrence": p.recurrence_count}
                for score, p in scored[:3]
            ]

        async def _match_methodologies():
            if _match_frameworks is not None:
                return _match_frameworks(aspect)[:3]
            return []

        results = await asyncio.gather(
            _search_entities(),
            _query_patterns(),
            _match_methodologies(),
            return_exceptions=True
        )

        data = {}
        names = ["entities", "patterns", "methodologies"]
        for name, result in zip(names, results):
            if isinstance(result, Exception):
                logger.warning(f"{name} query failed: {result}")
            elif result:
                data[name] = result

        return self._success({"data": data})

    def _relevance(self, text: str, topic: str) -> float:
        if not topic or not text:
            return 0

        def bigrams(s: str) -> set:
            s = s.replace(' ', '')
            return {s[i:i + 2] for i in range(len(s) - 1)}

        topic_grams = bigrams(topic)
        text_grams = bigrams(text)
        if not topic_grams:
            return 0
        overlap = len(topic_grams & text_grams)
        return overlap / len(topic_grams)

    async def _record_observation(self, content: str, category: str) -> Dict:
        self._pending_observations.append({
            "content": content,
            "category": category,
            "timestamp": datetime.now().isoformat()
        })
        return self._success({"buffered": len(self._pending_observations)})


_RESOLVE_FAILED = object()
"""_LazyKM resolve failure sentinel"""


class _LazyKM:
    def __init__(self):
        self._resolved = None

    def __getattribute__(self, name):
        if name == '_resolved':
            return super().__getattribute__(name)
        resolved = super().__getattribute__('_resolved')
        if resolved is None:
            try:
                from src.core.container import get_container
                from src.core.memory import KnowledgeManager
                resolved = get_container().resolve(KnowledgeManager)
            except Exception:
                logger.warning("KM resolve failed, queries will return empty")
                resolved = _RESOLVE_FAILED
            object.__setattr__(self, '_resolved', resolved)
        return getattr(resolved, name)
