"""Provider-agnostic LLM gateway with ordered failover (docs/03, docs/04).

Preference order starts at settings.llm_provider, then the remaining providers.
Each provider is only a candidate if (a) its API key is configured and (b) its
LangChain integration package is installed. All imports are lazy so the app and
test suite run without these heavy deps installed — callers must handle
`LLMUnavailable` and fall back to a deterministic path.
"""

from __future__ import annotations

import logging
from typing import TypeVar

from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Fallback model ids per provider (product choices, see docs/03 comparison).
_MODEL_IDS = {
    "gemini": "gemini-2.0-flash",
    "anthropic": "claude-sonnet-4-6",  # high-stakes adjudicator fallback
    "openai": "gpt-4o-mini",
}


class LLMUnavailable(RuntimeError):
    """Raised when no provider can serve the request (no keys / libs / all failed)."""


def _provider_order() -> list[str]:
    primary = settings.llm_provider
    rest = [p for p in ("gemini", "anthropic", "openai") if p != primary]
    return [primary, *rest]


def _make_model(provider: str, temperature: float):
    """Instantiate a LangChain chat model for `provider`, or return None if unavailable."""
    try:
        if provider == "gemini" and settings.gemini_api_key:
            from langchain_google_genai import ChatGoogleGenerativeAI

            return ChatGoogleGenerativeAI(
                model=_MODEL_IDS["gemini"],
                google_api_key=settings.gemini_api_key,
                temperature=temperature,
            )
        if provider == "anthropic" and settings.anthropic_api_key:
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(
                model=_MODEL_IDS["anthropic"],
                api_key=settings.anthropic_api_key,
                temperature=temperature,
            )
        if provider == "openai" and settings.openai_api_key:
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=_MODEL_IDS["openai"],
                api_key=settings.openai_api_key,
                temperature=temperature,
            )
    except ImportError as exc:
        logger.warning("LLM provider '%s' library not installed: %s", provider, exc)
    return None


def _candidate_models(temperature: float = 0.2) -> list[tuple[str, object]]:
    out: list[tuple[str, object]] = []
    for provider in _provider_order():
        model = _make_model(provider, temperature)
        if model is not None:
            out.append((provider, model))
    return out


async def complete_structured(
    system: str, user: str, schema: type[T], temperature: float = 0.2
) -> T:
    """Return an instance of `schema`, trying providers in order until one succeeds."""
    candidates = _candidate_models(temperature)
    if not candidates:
        raise LLMUnavailable("No LLM provider configured (missing API keys or libraries).")

    from langchain_core.messages import HumanMessage, SystemMessage

    messages = [SystemMessage(content=system), HumanMessage(content=user)]
    last_err: Exception | None = None
    for name, model in candidates:
        try:
            structured = model.with_structured_output(schema)
            result = await structured.ainvoke(messages)
            logger.info("LLM structured completion via provider=%s", name)
            return result  # type: ignore[return-value]
        except Exception as exc:  # noqa: BLE001 — failover across providers
            logger.warning("LLM provider '%s' failed, trying next: %s", name, exc)
            last_err = exc
    raise LLMUnavailable(f"All LLM providers failed. Last error: {last_err}")
