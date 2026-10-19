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
- Multimodal/Vision support (call_llm_vision)
"""
import base64
import asyncio
import inspect
import json
import logging
import os
from contextvars import ContextVar
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Union
from src.config import settings
from src.config.llm_profiles import LLMProfile, LLMProfileRegistry, RoutingHint
from src.core.llm_retry import (
    Budget, CandidateDesc, LLMBudgetExhausted, LLMStreamCommitted,
    RetryEngine, RetryVariations,
)

logger = logging.getLogger(__name__)

# Profiles returning authentication failures remain unavailable for this
# process.  This prevents an expired optional profile from producing a 401 on
# every Agent call while healthy fallback profiles are available.
_UNAVAILABLE_PROFILES = set()
_PROFILE_SEMAPHORES = {}
_RATE_LIMIT_RETRIES = 2
_TIMEOUT_RETRIES = 2


def ban_profile(name: str) -> None:
    """Durably blacklist a profile for this process.

    Used by the RetryEngine integration: the engine's per-instance ``_banned``
    set dies with the engine, while ``_UNAVAILABLE_PROFILES`` persists across
    engine instances so a proven-bad profile stays out of the candidate list.
    """
    _UNAVAILABLE_PROFILES.add(name)


def _direct_candidate_desc() -> CandidateDesc:
    """CandidateDesc for the legacy no-router settings.llm path."""
    return CandidateDesc(
        name="direct",
        model=settings.llm.model,
        fallback_model=settings.llm.cheap_model,
    )


def _selection_first_enabled() -> bool:
    """LLM_SELECTION_FIRST=0 restores the pure profile-chain behaviour."""
    return os.environ.get("LLM_SELECTION_FIRST", "1").strip().lower() not in {
        "0", "false", "no", "off",
    }


def _usable_profile_key(profile: LLMProfile) -> bool:
    """LLMRouter._has_usable_api_key semantics: unresolved YAML environment
    placeholders count as missing keys; local/ollama endpoints need none."""
    provider = str(getattr(profile, "provider", "") or "").lower()
    if provider in {"local", "ollama"}:
        return True
    key = str(getattr(profile, "api_key", "") or "").strip()
    return bool(key) and not (key.startswith("${") and key.endswith("}"))


def _profile_to_candidate_desc(profile: LLMProfile) -> CandidateDesc:
    return CandidateDesc(
        name=profile.name,
        model=profile.model,
        fallback_model=profile.fallback_model or "",
        max_context_tokens=int(getattr(profile, "max_context_tokens", 0) or 0),
        api_key=profile.api_key or "",
        base_url=profile.base_url or "",
        temperature=getattr(profile, "temperature", None),
        top_p=getattr(profile, "top_p", None),
    )


def _selection_candidate_desc() -> Optional[CandidateDesc]:
    """CandidateDesc for the user's UI provider/model selection.

    Empty/whitespace ``settings.llm.model`` means no explicit selection ->
    pure chain.  Empty base_url/api_key fall back to settings.llm inside the
    transport (``api_key or settings.llm.api_key``), exactly like the legacy
    "direct" candidate.
    """
    model = str(settings.llm.model or "").strip()
    if not model:
        return None
    return CandidateDesc(
        name="selection",
        model=model,
        fallback_model="",
        max_context_tokens=0,
        api_key=settings.llm.api_key or "",
        base_url=settings.llm.base_url or "",
        temperature=getattr(settings.llm, "temperature", None),
        top_p=getattr(settings.llm, "top_p", None),
    )


def _same_endpoint(a: CandidateDesc, b: CandidateDesc) -> bool:
    """Exact-duplicate test: same model AND same base_url."""
    return a.model == b.model and a.base_url == b.base_url


def _retry_candidate_descs(routing_hint: Optional[RoutingHint] = None) -> List[CandidateDesc]:
    """Resolve the current router-ordered candidate list for the RetryEngine.

    Returns lightweight CandidateDesc entries (not LLMProfile) so llm_retry
    stays import-cycle free.  Profiles already in _UNAVAILABLE_PROFILES are
    skipped here; the engine also bans candidates at runtime via
    ``ban_profile``.  Falls back to the single "direct" settings-based
    candidate when no router/profiles are configured.

    Selection-first routing (EXCLUSIVE): the user's UI selection
    (settings.llm.model/base_url/api_key) becomes the ONLY serving candidate;
    when settings.llm.provider names an enabled, keyed profile in the
    registry, that profile is added as the second candidate so its parameter
    constraints (temperature/top_p) still apply.  The profile chain is NOT
    used as a fallback when a selection exists — failures surface honestly
    for the selected provider.  Set env LLM_SELECTION_FIRST=0 to restore the
    pure chain behaviour (no selection candidate).
    """
    if _router is None:
        _ensure_llm_infrastructure()
    descs: List[CandidateDesc] = []
    if _router is not None:
        for profile in _router.resolve_candidates(routing_hint or RoutingHint()):
            if profile is None:
                descs.append(_direct_candidate_desc())
                continue
            if profile.name in _UNAVAILABLE_PROFILES:
                continue
            descs.append(_profile_to_candidate_desc(profile))
    if not descs:
        descs.append(_direct_candidate_desc())

    if not _selection_first_enabled():
        return descs
    selection = _selection_candidate_desc()
    if selection is None:
        return descs

    # EXCLUSIVE semantics (user ruling 2026-10-17): an explicit selection
    # means ONLY the selected provider serves — settings endpoint/key plus
    # the provider's own registry profile (for parameter constraints like
    # kimi temperature=1/top_p=0.95).  The profile chain is NOT a fallback:
    # silently polling other providers' keys would spend their quotas and
    # blur which provider actually failed.  Failures surface honestly.
    ordered: List[CandidateDesc] = [selection]
    provider = str(settings.llm.provider or "").strip()
    registry = getattr(_router, "registry", None) if _router is not None else None
    if provider and registry is not None:
        profile = registry.profiles.get(provider)
        if (profile is not None and getattr(profile, "enabled", False)
                and _usable_profile_key(profile)):
            preferred = _profile_to_candidate_desc(profile)
            if not _same_endpoint(preferred, selection):
                ordered.append(preferred)
    return ordered


def _is_auth_error(error: Exception) -> bool:
    text = str(error).lower()
    return any(marker in text for marker in ("401", "unauthorized", "invalid api key", "authentication"))


def _iter_json_objects(text: str):
    """Yield balanced JSON object candidates without crossing nested braces."""
    start = None
    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                yield text[start:index + 1]
                start = None


def _profile_max_concurrency(profile: Optional[LLMProfile]) -> int:
    value = getattr(profile, "max_concurrency", 3) if profile is not None else 3
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 3


def _profile_semaphore(profile: Optional[LLMProfile]) -> asyncio.Semaphore:
    """Return a loop-local semaphore shared by all calls to one profile."""
    loop = asyncio.get_running_loop()
    key = (id(loop), getattr(profile, "name", "direct"))
    semaphore = _PROFILE_SEMAPHORES.get(key)
    if semaphore is None:
        semaphore = asyncio.Semaphore(_profile_max_concurrency(profile))
        _PROFILE_SEMAPHORES[key] = semaphore
    return semaphore


def _is_rate_limit_error(error: Exception) -> bool:
    text = str(error).lower()
    return "429" in text or "too many requests" in text or "rate limit" in text


def _is_timeout_error(error: Exception) -> bool:
    text = str(error).lower()
    return isinstance(error, (asyncio.TimeoutError, TimeoutError)) or "timeout" in text or "timed out" in text


async def _call_profile_api(*, profile: Optional[LLMProfile], **kwargs):
    """Call a provider under its concurrency gate with bounded 429 backoff."""
    semaphore = _profile_semaphore(profile)
    for attempt in range(max(_RATE_LIMIT_RETRIES, _TIMEOUT_RETRIES) + 1):
        try:
            async with semaphore:
                return await _call_llm_api(**kwargs)
        except Exception as exc:
            retry_limit = (
                _RATE_LIMIT_RETRIES if _is_rate_limit_error(exc)
                else _TIMEOUT_RETRIES if _is_timeout_error(exc)
                else -1
            )
            if retry_limit < 0 or attempt >= retry_limit:
                raise
            delay = min(2 ** attempt, 8)
            logger.warning(
                "LLM profile '%s' transient failure; retrying after %ss (%s/%s): %s",
                getattr(profile, "name", "direct"), delay, attempt + 1, retry_limit, exc,
            )
            await asyncio.sleep(delay)

_router: Optional[Any] = None
_client_pool: Optional[Any] = None
_client: Optional[Any] = None

# Per-request completion hook used by telemetry/tests. Context-local so
# concurrent requests cannot call each other's callbacks.
_on_complete_var: ContextVar[Optional[Any]] = ContextVar("llm_on_complete", default=None)


def _finish(result: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize the result and notify the optional per-context callback."""
    result.setdefault("content", "")
    callback = _on_complete_var.get()
    if callback is not None:
        try:
            callback(result)
        except Exception:
            logger.exception("LLM completion callback failed")
    return result


def _get_client() -> Any:
    """Return the process-local OpenAI-compatible client used by legacy callers."""
    global _client
    if _client is None:
        from openai import AsyncOpenAI
        _client = AsyncOpenAI(api_key=settings.llm.api_key, base_url=settings.llm.base_url,
                              max_retries=0)
    return _client


def _reset_client() -> None:
    """Reset the cached client; primarily useful for configuration changes/tests."""
    global _client
    old, _client = _client, None
    if old is not None:
        close = getattr(old, "close", None)
        if callable(close):
            try:
                close_result = close()
                if inspect.isawaitable(close_result):
                    try:
                        asyncio.get_running_loop()
                    except RuntimeError:
                        asyncio.run(close_result)
                    else:
                        # _reset_client is synchronous; do not leave an
                        # un-awaited coroutine in an active event loop.
                        close_result.close()
            except Exception:
                logger.debug("Failed to close cached LLM client", exc_info=True)


def init_llm_infrastructure(registry: LLMProfileRegistry):
    global _router, _client_pool
    from src.core.llm_router import LLMRouter
    from src.core.llm_client_pool import LLMClientPool
    _router = LLMRouter(registry)
    _client_pool = LLMClientPool()


def _ensure_llm_infrastructure() -> None:
    """Initialize profile routing for standalone workers as well as the API."""
    global _router
    if _router is not None:
        return
    try:
        registry = getattr(settings, "llm_profiles", None)
        if not isinstance(registry, LLMProfileRegistry):
            return
        init_llm_infrastructure(registry)
        logger.info("LLM infrastructure lazily initialized with %d profiles", len(registry.profiles))
    except Exception as exc:
        # Default settings remain a valid last-resort path; callers will still
        # receive a structured LLM error if that endpoint is unavailable.
        logger.warning("LLM infrastructure lazy initialization failed: %s", exc)


async def call_llm_stream(
    prompt: str,
    model: Optional[str] = None,
    system_prompt: str = "",
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    top_p: Optional[float] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    routing_hint: Optional[RoutingHint] = None,
    max_timeout_retries: int = 2,
) -> AsyncGenerator[str, None]:
    """Streaming variant of call_llm. Yields content tokens as they arrive.

    When no model/credentials/endpoint are explicitly supplied, use the same
    configured profile chain as ``call_llm``.  A stream can only be retried
    before its first token is yielded; retrying after partial output would
    duplicate user-visible content.
    ``max_timeout_retries`` bounds the inner same-profile timeout retry loop
    BEFORE failures escape to the caller: the legacy default (2) preserves
    standalone behaviour, while the RetryEngine stream transport passes 0 —
    the engine owns TIMEOUT retries, so one engine attempt must hit the
    provider exactly once (spec §3.2 single-shot transport).
    Does NOT trigger _on_complete_var (not defined in this module).
    """
    max_tokens = settings.llm.max_tokens if max_tokens is None else max_tokens
    temperature = settings.llm.temperature if temperature is None else temperature

    if not prompt or not prompt.strip():
        return

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    # Unconfigured callers use the registry's primary/fallback chain.  Do not
    # hardcode a provider here: the configured default may be MiMo today and a
    # different provider tomorrow.
    explicit_transport = any(value is not None for value in (model, api_key, base_url))
    if routing_hint is None and not explicit_transport and _router is None:
        _ensure_llm_infrastructure()
    if routing_hint is not None and _router is None:
        _ensure_llm_infrastructure()

    if _router is not None and (routing_hint is not None or not explicit_transport):
        candidates = _router.resolve_candidates(routing_hint or RoutingHint())
    else:
        candidates = [None]

    from openai import AsyncOpenAI
    last_error = None

    async def _stream_profile(profile, p_model, p_api_key, p_base_url):
        """Yield one provider attempt; the caller owns retry semantics."""
        request_timeout = float(os.environ.get("LLM_REQUEST_TIMEOUT_SECONDS", "600"))
        # Newer kwargs first; degrade for older OpenAI-compatible shims that
        # reject either kwarg (mirrors the historical timeout-only guard).
        constructor_kwargs = dict(
            api_key=p_api_key,
            base_url=p_base_url,
            timeout=request_timeout,
            max_retries=0,
        )
        while True:
            try:
                client_context = AsyncOpenAI(**constructor_kwargs)
                break
            except TypeError as constructor_error:
                error_text = str(constructor_error).lower()
                if "timeout" in error_text and "timeout" in constructor_kwargs:
                    constructor_kwargs.pop("timeout")
                elif "max_retries" in error_text and "max_retries" in constructor_kwargs:
                    constructor_kwargs.pop("max_retries")
                else:
                    raise
        async with client_context as client:
            response = await client.chat.completions.create(
                model=p_model,
                messages=messages,
                max_tokens=max_tokens if profile is None else (profile.max_tokens if max_tokens is None else max_tokens),
                temperature=temperature if profile is None else (profile.temperature if temperature is None else temperature),
                # Explicit caller top_p (profile-constrained candidates such
                # as kimi-k3, which only accepts 0.95) wins; None keeps the
                # historical behaviour: profile.top_p when profiled, else
                # settings.llm.top_p.
                top_p=(top_p if top_p is not None
                       else (settings.llm.top_p if profile is None else profile.top_p)),
                frequency_penalty=settings.llm.frequency_penalty if profile is None else profile.frequency_penalty,
                presence_penalty=settings.llm.presence_penalty if profile is None else profile.presence_penalty,
                stream=True,
            )
            # Reasoning-first providers (MIMO 2.5/2.6) may stream the whole
            # answer through delta.reasoning_content while delta.content
            # stays empty.  Content is still yielded incrementally; only
            # when the stream ends with no content at all is the buffered
            # reasoning surfaced, mirroring _parse_response's fallback so
            # streams stop failing with "returned empty content" and
            # burning full re-generation retries.
            reasoning_parts: List[str] = []
            emitted_content = False
            async for chunk in response:
                choices = chunk.choices if chunk.choices else []
                if choices:
                    delta = choices[0].delta
                    if not delta:
                        continue
                    content_text = getattr(delta, "content", None)
                    if content_text:
                        emitted_content = True
                        yield content_text
                    reasoning_text = getattr(delta, "reasoning_content", None)
                    if reasoning_text:
                        reasoning_parts.append(str(reasoning_text))
            if not emitted_content and reasoning_parts:
                yield "".join(reasoning_parts).strip()

    for profile in candidates:
        if profile is not None and profile.name in _UNAVAILABLE_PROFILES:
            continue
        p_model = model or (profile.model if profile is not None else settings.llm.model)
        p_api_key = api_key or (profile.api_key if profile is not None else settings.llm.api_key)
        p_base_url = (base_url or (profile.base_url if profile is not None else settings.llm.base_url) or '').strip()
        emitted = False
        for attempt in range(max_timeout_retries + 1):
            try:
                # This is an inactivity/read timeout, not a total generation
                # deadline. Each received chunk resets the provider timer.
                async for token in _stream_profile(profile, p_model, p_api_key, p_base_url):
                    emitted = True
                    yield token
                return
            except Exception as exc:
                last_error = exc
                if emitted:
                    raise
                if _is_timeout_error(exc) and attempt < max_timeout_retries:
                    delay = min(2 ** attempt, 8)
                    logger.warning(
                        "Streaming LLM timeout on profile '%s'; retrying same profile after %ss (%s/%s)",
                        getattr(profile, "name", "direct"), delay, attempt + 1, max_timeout_retries,
                    )
                    await asyncio.sleep(delay)
                    continue
                if profile is not None and _is_auth_error(exc):
                    _UNAVAILABLE_PROFILES.add(profile.name)
                    logger.error("Disabling streaming LLM profile '%s' after authentication failure", profile.name)
                logger.warning("Streaming LLM call failed on profile '%s': %s; trying configured fallback", getattr(profile, 'name', 'direct'), exc)
                break
    if last_error is not None:
        raise last_error


async def call_llm(
    prompt: str,
    model: Optional[str] = None,
    system_prompt: str = "",
    fallback_model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    routing_hint: Optional[RoutingHint] = None,
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
        api_key: API key (default from settings.llm.api_key)
        base_url: API base URL (default from settings.llm.base_url)
        routing_hint: Optional routing hint for profile-based routing

    Returns:
        Dict with keys: success, content, model, usage
        On failure: success=False, message=str, error=str
    """
    if not prompt or not prompt.strip():
        return _finish({"success": False, "message": "prompt cannot be empty", "error": "empty_prompt"})

    # Calls without an explicit model/credential/endpoint are ordinary
    # application calls, not a request to bypass routing.  Route them through
    # the configured default profile so a stale provider in legacy settings
    # cannot bypass the configured fallback chain.
    if (
        routing_hint is None
        and _router is not None
        and model is None
        and api_key is None
        and base_url is None
    ):
        routing_hint = RoutingHint()

    if routing_hint is not None and _router is None:
        _ensure_llm_infrastructure()

    if routing_hint is not None and _router is not None:
        candidates = _router.resolve_candidates(routing_hint)
        first_err = None
        for profile in candidates:
            if profile.name in _UNAVAILABLE_PROFILES:
                continue
            p_model = model or profile.model
            p_fallback = fallback_model or profile.fallback_model
            p_max_tokens = profile.max_tokens if max_tokens is None else max_tokens
            p_temperature = profile.temperature if temperature is None else temperature
            p_api_key = api_key or profile.api_key
            p_base_url = (base_url or profile.base_url or '').strip()
            if profile.cost_limit_per_call > 0:
                estimated_cost = (p_max_tokens / 1000) * 0.01
                if estimated_cost > profile.cost_limit_per_call:
                    if first_err is None:
                        first_err = f"Profile {profile.name}: estimated cost ${estimated_cost:.4f} exceeds limit ${profile.cost_limit_per_call:.2f}"
                    continue
            try:
                response = await _call_profile_api(profile=profile, prompt=prompt, model=p_model,
                                                   system_prompt=system_prompt, max_tokens=p_max_tokens,
                                                   temperature=p_temperature, api_key=p_api_key,
                                                   base_url=p_base_url)
                result = _parse_response(response, p_model)
                if not result.get("success"):
                    # Some reasoning-first gateways occasionally return a
                    # successful HTTP envelope with an empty message. Give
                    # the selected profile one immediate retry before
                    # declaring it unavailable; this is especially important
                    # when the configured primary is the only usable model.
                    if result.get("error") == "empty_content":
                        logger.warning("LLM profile '%s' returned empty content; retrying once", profile.name)
                        response = await _call_profile_api(profile=profile, prompt=prompt, model=p_model,
                                                           system_prompt=system_prompt, max_tokens=p_max_tokens,
                                                           temperature=p_temperature, api_key=p_api_key,
                                                           base_url=p_base_url)
                        result = _parse_response(response, p_model)
                if not result.get("success"):
                    raise RuntimeError(result.get("message") or result.get("error") or "LLM response unusable")
                if profile != candidates[0]:
                    result["fallback_used"] = True
                    result["fallback_profile"] = profile.name
                    logger.info(f"LLM call succeeded on fallback profile '{profile.name}' (model: {p_model})")
                return _finish(result)
            except Exception as err:
                if first_err is None:
                    first_err = str(err)
                logger.warning(f"LLM call failed on profile '{profile.name}' (model: {p_model}): {err}")
                auth_failed = _is_auth_error(err)
                if auth_failed:
                    _UNAVAILABLE_PROFILES.add(profile.name)
                    logger.error(
                        "Disabling LLM profile '%s' for this process after authentication failure",
                        profile.name,
                    )
                # A profile-level fallback uses the same credentials and
                # endpoint.  After 401/unauthorized it can only repeat the
                # same failure; continue directly to the next provider
                # candidate (normally the configured default profile).
                if not auth_failed and p_fallback and p_fallback != p_model:
                    try:
                        response = await _call_profile_api(profile=profile, prompt=prompt, model=p_fallback,
                                                           system_prompt=system_prompt, max_tokens=p_max_tokens,
                                                           temperature=p_temperature, api_key=p_api_key,
                                                           base_url=p_base_url)
                        result = _parse_response(response, p_fallback)
                        if not result.get("success"):
                            raise RuntimeError(result.get("message") or result.get("error") or "LLM fallback response unusable")
                        result["fallback_used"] = True
                        if profile != candidates[0]:
                            result["fallback_profile"] = profile.name
                        logger.info(f"LLM call succeeded on profile '{profile.name}' fallback model '{p_fallback}'")
                        return _finish(result)
                    except Exception as fb_err:
                        logger.warning(f"LLM fallback model '{p_fallback}' also failed on profile '{profile.name}': {fb_err}")
                        if _is_auth_error(fb_err):
                            _UNAVAILABLE_PROFILES.add(profile.name)
                continue
        return _finish({"success": False, "message": first_err or "All LLM profiles failed", "error": "llm_call_failed"})
    elif routing_hint is not None and _router is None:
        logger.warning("routing_hint provided but LLM router not initialized; using default settings")

    model = model or settings.llm.model
    fallback_model = fallback_model or settings.llm.cheap_model
    max_tokens = settings.llm.max_tokens if max_tokens is None else max_tokens
    temperature = settings.llm.temperature if temperature is None else temperature
    api_key = api_key or settings.llm.api_key
    base_url = (base_url or settings.llm.base_url or '').strip()

    # Cost limit check
    if settings.llm.cost_limit_per_report > 0:
        estimated_cost = (max_tokens / 1000) * 0.01
        if estimated_cost > settings.llm.cost_limit_per_report:
            return _finish({
                "success": False,
                "message": f"Estimated cost ${estimated_cost:.4f} exceeds limit ${settings.llm.cost_limit_per_report:.2f}",
                "error": "cost_limit",
            })

    # Try primary model
    try:
        response = await _call_profile_api(profile=None, prompt=prompt, model=model,
                                           system_prompt=system_prompt, max_tokens=max_tokens,
                                           temperature=temperature, api_key=api_key, base_url=base_url)
        result = _parse_response(response, model)
        if not result.get("success"):
            raise RuntimeError(result.get("message") or result.get("error") or "LLM response unusable")
        return _finish(result)
    except Exception as primary_err:
        if _is_auth_error(primary_err):
            # The legacy direct path has no trustworthy same-provider
            # fallback after an authentication failure.  Do not repeat the
            # invalid credential with another model.
            return _finish({
                "success": False,
                "message": str(primary_err),
                "error": "authentication_failed",
            })
        if fallback_model and fallback_model != model:
            try:
                response = await _call_profile_api(profile=None, prompt=prompt, model=fallback_model,
                                                   system_prompt=system_prompt, max_tokens=max_tokens,
                                                   temperature=temperature, api_key=api_key, base_url=base_url)
                result = _parse_response(response, fallback_model)
                result["fallback_used"] = True
                return _finish(result)
            except Exception as fallback_err:
                return _finish({
                    "success": False,
                    "message": f"Primary: {primary_err}; Fallback: {fallback_err}",
                    "error": "llm_call_failed",
                })
        return _finish({"success": False, "message": str(primary_err), "error": "llm_call_failed"})


def _ex_transport_factory(stream: bool = False, on_token: Optional[Callable[[str], None]] = None):
    """Build the single-shot transport callable the RetryEngine drives.

    The engine owns ALL retry policy (classify -> mutate -> attempt).  This
    transport must therefore stay single-shot: it deliberately bypasses
    ``_call_profile_api``'s internal 429/timeout retry loop, which is
    legacy-only and would double-retry underneath the engine.
    """
    if stream:
        async def stream_transport(candidate, *, prompt, model, max_tokens, temperature):
            # Profile-constrained temperature (e.g. kimi only accepts 1) beats
            # the settings default on the base attempt; explicit engine
            # variations still win (mutation ladder's right to override).
            effective_temperature = (temperature
                                     if temperature is not None
                                     else getattr(candidate, "temperature", None))
            # Profile-constrained top_p (kimi-k3 rejects top_p != 0.95):
            # None keeps call_llm_stream's settings/profile fallback.
            effective_top_p = getattr(candidate, "top_p", None)
            buffer: List[str] = []
            emitted = False
            try:
                async for token in call_llm_stream(
                        prompt, model=model, max_tokens=max_tokens,
                        temperature=effective_temperature,
                        top_p=effective_top_p,
                        api_key=candidate.api_key or None,
                        base_url=candidate.base_url or None,
                        # Engine owns TIMEOUT retries (spec §3.2): this
                        # transport stays single-shot, so one engine attempt
                        # must hit the provider exactly once.
                        max_timeout_retries=0):
                    buffer.append(token)
                    emitted = True
                    if on_token is not None:
                        on_token(token)
            except Exception as exc:
                if emitted:
                    # C1: token 已到达用户；任何重试（同候选或换候选）都会重复
                    # 可见内容，整个 run 必须终止（引擎对 LLMStreamCommitted
                    # 立即 re-raise，不分类不重试）。
                    raise LLMStreamCommitted(str(exc)) from exc
                raise
            # Do NOT raise for an empty stream.  Returning "" lets the
            # engine's shape check classify it as no_json -> BAD_JSON_FORMAT
            # ladder (strict_json -> switch_model); an explicit raise would
            # classify as UNKNOWN and buy only a blind same-params retry.
            return "".join(buffer)

        return stream_transport

    async def transport(candidate, *, prompt, model, max_tokens, temperature):
        # Same precedence as the stream branch: explicit engine variation >
        # profile-constrained temperature > settings default.
        effective_temperature = (temperature
                                 if temperature is not None
                                 else getattr(candidate, "temperature", None))
        response = await _call_llm_api(
            prompt=prompt,
            model=model,
            system_prompt="",
            max_tokens=settings.llm.max_tokens if max_tokens is None else max_tokens,
            temperature=(settings.llm.temperature if effective_temperature is None
                         else effective_temperature),
            api_key=candidate.api_key or None,
            base_url=candidate.base_url or None,
            top_p=getattr(candidate, "top_p", None),
        )
        result = _parse_response(response, model)
        if not result.get("success"):
            raise RuntimeError(result.get("message") or result.get("error") or "LLM response unusable")
        return result.get("content") or ""

    return transport


async def call_llm_ex(
    prompt_builder,
    *,
    output_contract: str = "prose",
    expected_output_chars: int = 2000,
    budget: Optional[Budget] = None,
    parse: Optional[Callable] = None,
    stream: bool = False,
    on_token: Optional[Callable[[str], None]] = None,
    routing_hint: Optional[RoutingHint] = None,
    task_tag: str = "",
    allow_prompt_compression: bool = False,
):
    """Failure-mode-aware LLM entry point driving the RetryEngine (spec §3.2).

    Returns the usable raw output string on success; raises
    ``LLMBudgetExhausted`` (carrying the final Classification, attempt count,
    elapsed time and per-profile notes) when every candidate/budget path is
    spent without a usable result.

    prompt_builder contract: a callable receiving a RetryVariations instance
    and returning the prompt string (parameter-level mutations always apply);
    a plain string is also accepted and wrapped so only parameter/model-level
    mutations apply.  ``output_contract`` is "prose" (default) or "json"
    ("json" enables the strict-JSON shape check and STRICT_JSON_PREFIX
    mutation).  In stream mode the transport buffers chunks, forwards each
    chunk to ``on_token`` when provided, and returns the joined text.
    """
    # Legacy escape hatch (spec §3.3 rollback path).
    if os.environ.get("LLM_RETRY_ENGINE") == "legacy":
        # Contract-compliant builders expect a RetryVariations instance
        # (reading .temperature etc.); None would crash them.
        legacy_prompt = (prompt_builder(RetryVariations())
                         if callable(prompt_builder) else prompt_builder)
        result = await call_llm(legacy_prompt)
        if not result.get("success"):
            raise RuntimeError(result.get("message") or result.get("error") or "LLM call failed")
        return result.get("content") or ""

    if not callable(prompt_builder):
        plain_prompt = prompt_builder
        prompt_builder = lambda variations, _p=plain_prompt: _p  # noqa: E731

    engine_budget = budget or Budget.scale_to(expected_output_chars)
    # R2 scale rule: 21k chars -> ~18.2k tokens, never below the config default.
    base_max_tokens = max(int(getattr(settings.llm, "max_tokens", 0) or 0),
                          int(expected_output_chars / 1.5 * 1.3))
    # The engine consumes candidates once at run start, so eager resolution
    # here is semantically identical to a lazy callable.
    if routing_hint is not None:
        candidate_descs = _retry_candidate_descs(routing_hint)
    else:
        candidate_descs = _retry_candidate_descs()
    engine = RetryEngine(
        transport=_ex_transport_factory(stream, on_token),
        candidates=lambda: candidate_descs,
        parse=parse,
        budget=engine_budget,
        base_max_tokens=base_max_tokens,
        allow_prompt_compression=allow_prompt_compression,
        task_tag=task_tag,
        # I1: engine-level bans must outlive the engine instance, otherwise
        # ban_profile stays dead code and dead profiles come back next call.
        ban_hook=ban_profile,
    )
    try:
        return await engine.run(prompt_builder=prompt_builder, output_contract=output_contract)
    except LLMBudgetExhausted as exhausted:
        # M5: prefix the message with the task_tag so downstream handlers can
        # attribute the exhaustion; the structured payload attributes
        # (classification/attempts/elapsed/profile_notes) stay untouched.
        if task_tag:
            exhausted.args = (f"[{task_tag}] {exhausted}",)
        raise


async def call_llm_with_tools(
    prompt: str,
    tools: List[Dict[str, Any]],
    tool_handler: Callable[[str, Dict[str, Any]], Any],
    *,
    model: Optional[str] = None,
    system_prompt: str = "",
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    max_tool_rounds: int = 6,
) -> Dict[str, Any]:
    """Call an OpenAI-compatible model with a bounded read-only tool loop.

    This is intentionally separate from ``call_llm`` so legacy callers keep
    the exact response contract.  The handler is owned by the caller and is
    responsible for enforcing its own path/security policy.
    """
    from openai import AsyncOpenAI

    if not prompt or not prompt.strip():
        return _finish({"success": False, "message": "prompt cannot be empty", "error": "empty_prompt"})

    messages: List[Dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    client_timeout = float(os.environ.get("LLM_REQUEST_TIMEOUT_SECONDS", "600"))
    # Newer kwargs first; degrade for older OpenAI-compatible shims that
    # reject either kwarg (mirrors the historical timeout-only guard), so
    # real clients still receive the configured 600s transport timeout and
    # no hidden SDK-level retries under the RetryEngine.
    constructor_kwargs = dict(
        api_key=settings.llm.api_key,
        base_url=(settings.llm.base_url or "").strip(),
        timeout=client_timeout,
        max_retries=0,
    )
    while True:
        try:
            client = AsyncOpenAI(**constructor_kwargs)
            break
        except TypeError as constructor_error:
            error_text = str(constructor_error).lower()
            if "timeout" in error_text and "timeout" in constructor_kwargs:
                constructor_kwargs.pop("timeout")
            elif "max_retries" in error_text and "max_retries" in constructor_kwargs:
                constructor_kwargs.pop("max_retries")
            else:
                raise
    try:
        for _ in range(max(0, int(max_tool_rounds)) + 1):
            response = await client.chat.completions.create(
                model=model or settings.llm.model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                max_tokens=settings.llm.max_tokens if max_tokens is None else max_tokens,
                temperature=settings.llm.temperature if temperature is None else temperature,
                top_p=settings.llm.top_p,
                frequency_penalty=settings.llm.frequency_penalty,
                presence_penalty=settings.llm.presence_penalty,
            )
            message = response.choices[0].message
            tool_calls = getattr(message, "tool_calls", None) or []
            if not tool_calls:
                return _finish(_parse_response(response.model_dump(), model or settings.llm.model))

            messages.append(message.model_dump(exclude_none=True))
            for call in tool_calls:
                try:
                    arguments = json.loads(call.function.arguments or "{}")
                    result = tool_handler(call.function.name, arguments)
                    if inspect.isawaitable(result):
                        result = await result
                    payload = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
                except Exception as exc:
                    payload = json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": payload,
                })
        return _finish({"success": False, "message": "tool call limit exceeded", "error": "tool_call_limit"})
    except Exception as exc:
        logger.warning("LLM tool call failed: %s", exc)
        return _finish({"success": False, "message": str(exc), "error": "llm_tool_call_failed"})
    finally:
        await client.close()


def call_llm_sync(
    prompt: str,
    model: Optional[str] = None,
    system_prompt: str = "",
    fallback_model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    routing_hint: Optional[RoutingHint] = None,
) -> Dict[str, Any]:
    """Synchronous wrapper for call_llm().

    Handles async event loop bridging automatically:
    - If no event loop is running: uses asyncio.run()
    - If an event loop is already running: runs in a background thread
    """
    import asyncio
    import concurrent.futures

    coro = call_llm(
        prompt=prompt,
        model=model,
        system_prompt=system_prompt,
        fallback_model=fallback_model,
        max_tokens=max_tokens,
        temperature=temperature,
        api_key=api_key,
        base_url=base_url,
        routing_hint=routing_hint,
    )

    try:
        asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            # Do not impose a hidden Agent/business timeout in the sync
            # compatibility bridge.  The owning task controls cancellation;
            # provider-level request timeouts remain the provider's concern.
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        try:
            return asyncio.run(coro)
        except Exception as e:
            return {"success": False, "message": str(e), "error": "sync_call_failed"}
    except Exception as e:
        return {"success": False, "message": str(e), "error": "sync_call_failed"}


async def _call_llm_api(
    prompt: str,
    model: str,
    system_prompt: str = "",
    max_tokens: int = 2048,
    temperature: float = 0.7,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    top_p: Optional[float] = None,
) -> Dict[str, Any]:
    """Raw API call to OpenAI-compatible endpoint.

    ``top_p`` defaults to None → settings.llm.top_p (historical behaviour);
    profile-constrained candidates (kimi-k3 only accepts 0.95) pass their
    explicit value which then wins over settings.
    """
    from openai import AsyncOpenAI

    _api_key = api_key or settings.llm.api_key
    _base_url = base_url or settings.llm.base_url
    request_timeout = float(os.environ.get("LLM_REQUEST_TIMEOUT_SECONDS", "600"))
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    # Same kwargs-degradation as the streaming/with_tools constructors:
    # newer kwargs first (timeout, max_retries=0), drop whichever kwarg an
    # older shim rejects.
    constructor_kwargs = dict(
        api_key=_api_key,
        base_url=_base_url,
        timeout=request_timeout,
        max_retries=0,
    )
    while True:
        try:
            client = AsyncOpenAI(**constructor_kwargs)
            break
        except TypeError as constructor_error:
            error_text = str(constructor_error).lower()
            if "timeout" in error_text and "timeout" in constructor_kwargs:
                constructor_kwargs.pop("timeout")
            elif "max_retries" in error_text and "max_retries" in constructor_kwargs:
                constructor_kwargs.pop("max_retries")
            else:
                raise
    async with client:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=settings.llm.top_p if top_p is None else top_p,
            frequency_penalty=settings.llm.frequency_penalty,
            presence_penalty=settings.llm.presence_penalty,
        )
        return response.model_dump()


def _parse_response(response: Dict[str, Any], model: str) -> Dict[str, Any]:
    """Parse LLM API response into standard format."""
    try:
        message = response["choices"][0]["message"]
        content = message.get("content") or ""
        reasoning_content = message.get("reasoning_content") or ""
        usage = response.get("usage", {})
        # Reasoning-first providers may put the final structured answer in
        # reasoning_content.  Recover it only when it is demonstrably a
        # routing result; never expose arbitrary chain-of-thought as content.
        if not content.strip() and reasoning_content:
            for candidate in _iter_json_objects(reasoning_content):
                try:
                    parsed = json.loads(candidate)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict) and any(
                    key in parsed for key in (
                        "action", "topic", "framework_sections",
                        "primary_intent", "complexity", "research_types",
                    )
                ):
                    content = json.dumps(parsed, ensure_ascii=False)
                    break
        # If still no content but reasoning_content exists, use it as content
        # (MIMO 2.5 and similar models may put the answer in reasoning_content)
        if not content.strip() and reasoning_content.strip():
            content = reasoning_content.strip()
        if not content.strip():
            return {
                "success": False,
                "content": "",
                "reasoning_content": reasoning_content,
                "model": model,
                "usage": usage,
                "message": "LLM response contained no usable content",
                "error": "empty_content",
            }
        return {
            "success": True,
            "content": content,
            # Some OpenAI-compatible reasoning models return the final
            # structured answer in reasoning_content while content is empty.
            # Preserve it for callers that explicitly opt into this fallback;
            # never replace a non-empty content value with it.
            "reasoning_content": reasoning_content,
            "model": model,
            "usage": usage,
            "message": "LLM call successful",
        }
    except (KeyError, IndexError) as e:
        return {"success": False, "message": f"Response parsing failed: {e}", "error": "parse_error"}


async def call_llm_vision(
    prompt: str,
    images: Optional[List[Union[str, bytes]]] = None,
    model: Optional[str] = None,
    system_prompt: str = "",
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    routing_hint: Optional[RoutingHint] = None,
) -> Dict[str, Any]:
    """
    Call multimodal/Vision LLM with text + images.

    Args:
        prompt: Text prompt
        images: List of image data — each item is either:
            - str: base64-encoded image data (without data: prefix)
            - bytes: raw image bytes (will be base64-encoded)
            - str starting with "http": URL to fetch
        model: Vision model name (default from settings.llm.vision_model or settings.llm.model)
        system_prompt: System prompt
        max_tokens: Max generation tokens
        temperature: Temperature
        api_key: API key
        base_url: API base URL

    Returns:
        Same format as call_llm: {success, content, model, usage}
    """
    max_tokens = settings.llm.max_tokens if max_tokens is None else max_tokens
    temperature = settings.llm.temperature if temperature is None else temperature

    if not prompt or not prompt.strip():
        return {"success": False, "message": "prompt cannot be empty", "error": "empty_prompt"}

    content_parts: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]

    if images:
        for img in images:
            if isinstance(img, bytes):
                b64 = base64.b64encode(img).decode("utf-8")
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"},
                })
            elif isinstance(img, str):
                if img.startswith(("http://", "https://")):
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {"url": img},
                    })
                elif img.startswith("data:"):
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {"url": img},
                    })
                else:
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img}"},
                    })

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": content_parts})

    explicit_transport = any(value is not None for value in (model, api_key, base_url))
    if not explicit_transport or routing_hint is not None:
        _ensure_llm_infrastructure()
    if _router is not None and (routing_hint is not None or not explicit_transport):
        candidates = _router.resolve_candidates(routing_hint or RoutingHint())
    else:
        candidates = [None]

    from openai import AsyncOpenAI
    last_error = None
    for profile in candidates:
        if profile is not None and profile.name in _UNAVAILABLE_PROFILES:
            continue
        p_model = model or (profile.model if profile is not None else getattr(settings.llm, 'vision_model', None) or settings.llm.model)
        p_api_key = api_key or (profile.api_key if profile is not None else settings.llm.api_key)
        p_base_url = (base_url or (profile.base_url if profile is not None else settings.llm.base_url) or '').strip()
        try:
            # Keep the client direct rather than relying on ``async with``;
            # this also supports compatible clients whose context manager
            # returns a different proxy object.
            client = AsyncOpenAI(api_key=p_api_key, base_url=p_base_url, max_retries=0)
            try:
                response = await client.chat.completions.create(
                    model=p_model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature if profile is None else (profile.temperature if temperature is None else temperature),
                    top_p=settings.llm.top_p if profile is None else profile.top_p,
                )
            finally:
                # finally ONLY closes the client: parsing/returning must never
                # run here, otherwise a create() failure leaves ``response``
                # unbound and the NameError inside finally masks the original
                # provider error.
                close = getattr(client, "close", None)
                if callable(close):
                    close_result = close()
                    if inspect.isawaitable(close_result):
                        await close_result
            result = _parse_response(response.model_dump(), p_model)
            if not result.get("success"):
                raise RuntimeError(result.get("message") or result.get("error") or "Vision LLM response unusable")
            if profile is not None and profile != candidates[0]:
                result["fallback_used"] = True
                result["fallback_profile"] = profile.name
            return result
        except Exception as exc:
            last_error = exc
            if profile is not None and _is_auth_error(exc):
                _UNAVAILABLE_PROFILES.add(profile.name)
                logger.error("Disabling vision LLM profile '%s' after authentication failure", profile.name)
            logger.warning("Vision LLM call failed on profile '%s': %s; trying configured fallback", getattr(profile, 'name', 'direct'), exc)
    return {"success": False, "message": str(last_error) if last_error else "All vision LLM profiles failed", "error": "vision_call_failed"}
