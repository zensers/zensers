"""
LLMSkill - Large Language Model Invocation Skill

Supports calling any LLM through OpenAI-compatible interface, with retry, fallback, and token statistics.
"""
from typing import Any, Dict, Optional

from src.skills.base import Skill, SkillConfig
from src.config import settings


class LLMSkill(Skill):
    """
    LLM Invocation Skill

    Features:
    - Call OpenAI-compatible interface
    - Support system prompt
    - Auto-fallback to backup model when primary fails
    - Return token usage
    - Support configuration system to manage API Key and model parameters
    """

    @property
    def name(self) -> str:
        return "llm_skill"

    @property
    def description(self) -> str:
        return "Large language model invocation, supports OpenAI-compatible interface, primary/backup model switching, token statistics"

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Execute LLM call

        Args:
            prompt: User prompt (required)
            model: Model name (default uses model from config)
            system_prompt: System prompt (optional)
            fallback_model: Fallback model (optional, default uses cheap_model from config)
            max_tokens: Maximum generation tokens (default uses max_tokens from config)
            temperature: Temperature parameter (default uses temperature from config)

        Returns:
            Result dictionary containing content, usage, model
        """
        prompt = kwargs.get("prompt", "")
        
        # Read defaults from configuration system
        model = kwargs.get("model", settings.llm.model)
        system_prompt = kwargs.get("system_prompt", "")
        fallback_model = kwargs.get("fallback_model", settings.llm.cheap_model)
        max_tokens = kwargs.get("max_tokens", settings.llm.max_tokens)
        temperature = kwargs.get("temperature", settings.llm.temperature)

        if not prompt or not prompt.strip():
            return self._failure("prompt cannot be empty")

        # Check cost limit
        if settings.llm.cost_limit_per_report > 0:
            # Simple estimation: assume ~$0.01 per 1000 tokens
            estimated_cost = (max_tokens / 1000) * 0.01
            if estimated_cost > settings.llm.cost_limit_per_report:
                return self._failure(
                    f"Estimated cost ${estimated_cost:.4f} exceeds per-report limit ${settings.llm.cost_limit_per_report:.2f}",
                    "Cost limit triggered"
                )

        # Try primary model first
        try:
            response = await self._call_llm(
                prompt=prompt,
                model=model,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return self._parse_response(response, model)

        except Exception as primary_err:
            # Try fallback model
            if fallback_model and fallback_model != model:
                try:
                    response = await self._call_llm(
                        prompt=prompt,
                        model=fallback_model,
                        system_prompt=system_prompt,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    result = self._parse_response(response, fallback_model)
                    result["fallback_used"] = True
                    return result
                except Exception as fallback_err:
                    return self._failure(
                        f"Primary: {primary_err}; Fallback: {fallback_err}",
                        "LLM call failed (both primary and fallback unavailable)"
                    )
            return self._failure(str(primary_err), "LLM call failed")

    async def _call_llm(
        self,
        prompt: str,
        model: str,
        system_prompt: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        """
        Call LLM (generic OpenAI-compatible interface)

        Supports: OpenAI, DeepSeek, GLM-4, Tongyi Qianwen, Moonshot, Ollama, etc.
        """
        from openai import AsyncOpenAI

        # Use API Key and Base URL from configuration system
        client = AsyncOpenAI(
            api_key=settings.llm.api_key,
            base_url=settings.llm.base_url,
        )

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=settings.llm.top_p,
            frequency_penalty=settings.llm.frequency_penalty,
            presence_penalty=settings.llm.presence_penalty,
        )

        return response.model_dump()

    def _parse_response(self, response: Dict[str, Any], model: str) -> Dict[str, Any]:
        """Parse LLM response"""
        try:
            content = response["choices"][0]["message"]["content"]
            usage = response.get("usage", {})
            return self._success(
                {
                    "content": content,
                    "model": model,
                    "usage": usage,
                },
                "LLM call successful"
            )
        except (KeyError, IndexError) as e:
            return self._failure(f"Response parsing failed: {e}")
