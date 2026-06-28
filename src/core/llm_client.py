"""
LLM Client - Standalone LLM invocation utility, not a Skill.

LLM is an intrinsic agent capability, not an external tool.
Agents should call LLM directly, not through the skill registry.

Features:
- OpenAI-compatible interface
- System prompt support
- Automatic fallback to backup model
- Token usage tracking
- Configuration-driven (settings.llm.*)
"""
from typing import Any, Dict, Optional
from src.config import settings


async def call_llm(
    prompt: str,
    model: Optional[str] = None,
    system_prompt: str = "",
    fallback_model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Call LLM (standalone utility, not a skill).

    Args:
        prompt: User prompt (required)
        model: Model name (default from settings.llm.model)
        system_prompt: System prompt (optional)
        fallback_model: Fallback model (default from settings.llm.cheap_model)
        max_tokens: Max generation tokens (default from settings.llm.max_tokens)
        temperature: Temperature (default from settings.llm.temperature)

    Returns:
        Dict with keys: success, content, model, usage
        On failure: success=False, message=str, error=str
    """
    model = model or settings.llm.model
    fallback_model = fallback_model or settings.llm.cheap_model
    max_tokens = max_tokens or settings.llm.max_tokens
    temperature = temperature or settings.llm.temperature

    if not prompt or not prompt.strip():
        return {"success": False, "message": "prompt cannot be empty", "error": "empty_prompt"}

    # Cost limit check
    if settings.llm.cost_limit_per_report > 0:
        estimated_cost = (max_tokens / 1000) * 0.01
        if estimated_cost > settings.llm.cost_limit_per_report:
            return {
                "success": False,
                "message": f"Estimated cost ${estimated_cost:.4f} exceeds limit ${settings.llm.cost_limit_per_report:.2f}",
                "error": "cost_limit",
            }

    # Try primary model
    try:
        response = await _call_llm_api(prompt=prompt, model=model, system_prompt=system_prompt,
                                       max_tokens=max_tokens, temperature=temperature)
        return _parse_response(response, model)
    except Exception as primary_err:
        if fallback_model and fallback_model != model:
            try:
                response = await _call_llm_api(prompt=prompt, model=fallback_model, system_prompt=system_prompt,
                                               max_tokens=max_tokens, temperature=temperature)
                result = _parse_response(response, fallback_model)
                result["fallback_used"] = True
                return result
            except Exception as fallback_err:
                return {
                    "success": False,
                    "message": f"Primary: {primary_err}; Fallback: {fallback_err}",
                    "error": "llm_call_failed",
                }
        return {"success": False, "message": str(primary_err), "error": "llm_call_failed"}


async def _call_llm_api(
    prompt: str,
    model: str,
    system_prompt: str = "",
    max_tokens: int = 2048,
    temperature: float = 0.7,
) -> Dict[str, Any]:
    """Raw API call to OpenAI-compatible endpoint."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.llm.api_key, base_url=settings.llm.base_url)

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


def _parse_response(response: Dict[str, Any], model: str) -> Dict[str, Any]:
    """Parse LLM API response into standard format."""
    try:
        content = response["choices"][0]["message"]["content"]
        usage = response.get("usage", {})
        return {
            "success": True,
            "content": content,
            "model": model,
            "usage": usage,
            "message": "LLM call successful",
        }
    except (KeyError, IndexError) as e:
        return {"success": False, "message": f"Response parsing failed: {e}", "error": "parse_error"}
