from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["AgentConfig"]

# Canonical default model shared across agents.
DEFAULT_GOOGLE_MODEL = "gemini-3.1-flash-lite"


@dataclass
class AgentConfig:
    """Runtime configuration shared by all agents.

    Attributes:
        model: Google Generative AI model identifier.
        temperature: Sampling temperature (0 = deterministic).
        thinking_level: Gemini thinking budget — one of "none", "low", "medium", "high".
        debug: When True, intermediate thinking tokens are captured as a trace step.
    """

    model: str = field(default=DEFAULT_GOOGLE_MODEL)
    temperature: float = 0.0
    thinking_level: str = "medium"
    debug: bool = True
