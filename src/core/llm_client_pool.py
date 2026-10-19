import asyncio
from typing import Dict
from openai import AsyncOpenAI
from src.config.llm_profiles import LLMProfile


class LLMClientPool:
    def __init__(self):
        self._clients: Dict[str, AsyncOpenAI] = {}
        self._lock = asyncio.Lock()

    async def get_client(self, profile: LLMProfile) -> AsyncOpenAI:
        async with self._lock:
            if profile.name not in self._clients:
                self._clients[profile.name] = AsyncOpenAI(
                    api_key=profile.api_key,
                    base_url=profile.base_url,
                    max_retries=0,
                )
            return self._clients[profile.name]

    def invalidate(self, profile_name: str) -> None:
        self._clients.pop(profile_name, None)

    def invalidate_all(self) -> None:
        self._clients.clear()
