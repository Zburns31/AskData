import os

import pytest

# ---------------------------------------------------------------------------
# Disable Langfuse entirely before any askdata modules are imported.
# This must run at module level so it takes effect when pytest collects tests
# and imports agent modules (which apply @observe at decoration time).
# ---------------------------------------------------------------------------
os.environ["LANGFUSE_PUBLIC_KEY"] = ""
os.environ["LANGFUSE_SECRET_KEY"] = ""

# Replace the real langfuse.observe with a passthrough no-op so decorated
# agent methods run without any network activity during tests.
import langfuse as _langfuse_mod  # noqa: E402


def _noop_observe(*args, **kwargs):
    """No-op replacement for langfuse.observe / langfuse.trace."""

    def decorator(fn):
        return fn

    # Called as @observe or @observe(name="...")
    if args and callable(args[0]):
        return args[0]
    return decorator


_langfuse_mod.observe = _noop_observe

# Patch askdata.observability so already-imported references also get the no-op.
import askdata.observability as _obs  # noqa: E402

_obs.observe = _noop_observe
_obs.trace = _noop_observe


@pytest.fixture(autouse=True, scope="session")
def _langfuse_disabled() -> None:
    """Session-scoped marker fixture — env configuration is done at module level above."""
