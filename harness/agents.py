"""Agent factory: build Pydantic AI agents for DBOS durable execution.

Jobs that need a :class:`DBOSAgent` wrap the result of :func:`build_agent` themselves
(see ``agents.py``), because per-agent setup like ``@agent.instructions``
hooks must be registered before wrapping.

Important constraints (from the Pydantic AI ⇄ DBOS integration):
- Every agent needs a unique ``name`` (its durable identity).
- Agent inputs/outputs/deps must be pickle-serializable and kept under ~2 MB.
- HTTP-level client retries should be disabled so DBOS solely owns retry behavior.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from .config import get_settings

DepsT = TypeVar("DepsT")
OutputT = TypeVar("OutputT")


def build_agent(
    *,
    name: str,
    output_type: type[OutputT],
    deps_type: type[DepsT],
    instructions: str,
    model: str | None = None,
    temperature: float = 0.3,
) -> Agent[DepsT, OutputT]:
    """Build a plain Pydantic AI agent (unwrapped)."""
    settings = get_settings()
    return Agent(
        model or settings.llm_model,
        name=name,
        output_type=output_type,
        deps_type=deps_type,
        instructions=instructions,
        model_settings=ModelSettings(temperature=temperature),
    )
