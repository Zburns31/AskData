"""Lightweight Langfuse observability helper for agent tracing."""

import os
from typing import Optional

from langfuse import observe
from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler

# langfuse v4 removed the `trace` decorator; `observe` covers both use cases.
trace = observe

__all__ = ["observe", "trace", "get_langfuse_callback", "is_tracing_enabled"]


def is_tracing_enabled() -> bool:
    """Check if Langfuse credentials are configured."""
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    return bool(public_key and secret_key)


def get_langfuse_callback() -> Optional[LangfuseCallbackHandler]:
    """Get a Langfuse callback handler for LangChain integrations.

    Returns None if tracing credentials are not configured.
    """
    if not is_tracing_enabled():
        return None

    return LangfuseCallbackHandler()
