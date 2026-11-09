"""Fail-closed policy: never generate reasoning tokens for transcript cleanup.

Model support is explicit because many reasoning APIs reject "none" instead of
silently disabling thinking. Add a model here only after verifying its API docs.
Speech-to-text-only endpoints (OpenAI/Groq Whisper) are not text-generation paths.
"""

from __future__ import annotations


def text_generation_options(provider: str, model: str) -> dict:
    """Return SDK options for zero-reasoning text generation or raise ValueError."""
    if provider == "groq":
        # GPT-OSS on Groq cannot disable reasoning (low is its minimum).
        # Qwen 3.8 can switch to the native non-thinking instruct mode.
        if model == "qwen/qwen3.8-27b":
            return {"reasoning_effort": "none", "include_reasoning": False}
        raise ValueError(
            f"Groq model {model!r} is not approved for zero-reasoning cleanup. "
            "Use groq:qwen/qwen3.8-27b or openai:gpt-6-luna. "
            "GPT-OSS reasoning_effort='none' is not supported."
        )
    if provider == "openai":
        if model in {"gpt-6-luna", "gpt-6-sol", "gpt-5.4-mini", "gpt-5.4"}:
            return {"reasoning_effort": "none"}
        # Legacy standard/chat-audio models have no separate reasoning stage.
        if model in {
            "gpt-4o-mini", "gpt-4o", "gpt-4.1", "gpt-4.1-mini",
            "gpt-audio-mini", "gpt-audio-1.5",
        }:
            return {}
        raise ValueError(
            f"OpenAI model {model!r} has no verified zero-reasoning configuration. "
            "Use openai:gpt-6-luna or a supported non-reasoning model."
        )
    if provider == "gemini":
        if model in {"gemini-2.5-flash", "gemini-2.5-flash-lite"}:
            return {"thinking_budget": 0}
        raise ValueError(
            f"Gemini model {model!r} cannot be guaranteed to run with zero thinking. "
            "Gemini 3.x/Pro cannot disable thinking. Use gemini-2.5-flash "
            "or gemini-2.5-flash-lite."
        )
    raise ValueError(f"Unsupported text-generation provider: {provider}")
