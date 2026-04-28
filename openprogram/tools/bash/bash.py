"""bash tool — run a shell command, return stdout/stderr/exit code.

Single source of truth: the @tool decorator builds an AgentTool from
this function's signature + docstring. Legacy exports (NAME/SPEC/TOOL/
execute) are derived from the AgentTool so old call sites keep
working during the migration.
"""

from __future__ import annotations

from openprogram.backend import get_active_backend
from openprogram.tools._runtime import to_dict_tool, tool

from .prompt import DEFAULT_MAX_TIMEOUT_MS, DEFAULT_TIMEOUT_MS, DESCRIPTION


# Bash output can be huge (find /, full log dump). 30K matches Claude
# Code's BashTool default. persist_full=True saves the complete output
# to disk so the LLM can re-read with the read tool when the truncated
# view doesn't suffice.
@tool(
    name="bash",
    description=DESCRIPTION,
    max_result_chars=30_000,
    persist_full=True,
    toolset=["core"],
    unsafe_in=["wechat", "telegram"],   # destructive in public channels
)
def bash(command: str,
        timeout: float | None = None,
        description: str | None = None) -> str:
    """Run a shell command via the active backend (local / docker / ssh).

    Args:
        command: The shell command to execute.
        timeout: Optional timeout in milliseconds (default 30000, max 600000).
        description: Short active-voice description shown in UI (display only).
    """
    timeout_ms = min(timeout or DEFAULT_TIMEOUT_MS, DEFAULT_MAX_TIMEOUT_MS)
    timeout_sec = timeout_ms / 1000.0

    backend = get_active_backend()
    result = backend.run(command, timeout=timeout_sec)

    if result.timed_out:
        return (
            f"[timeout after {timeout_sec:.1f}s via {backend.backend_id}]\n"
            f"--- stdout (partial) ---\n{result.stdout}\n"
            f"--- stderr (partial) ---\n{result.stderr}"
        )

    parts = [f"exit_code={result.exit_code}"]
    if backend.backend_id != "local":
        parts[0] += f" (backend={backend.backend_id})"
    if result.stdout:
        parts.append(f"--- stdout ---\n{result.stdout.rstrip()}")
    if result.stderr:
        parts.append(f"--- stderr ---\n{result.stderr.rstrip()}")
    return "\n".join(parts)


# Legacy exports — derived from BASH so the dict and the AgentTool
# can never drift. Old callers (`from openprogram.tools.bash import
# SPEC, execute`) keep working until they migrate.
BASH = bash
NAME = BASH.name
_LEGACY = to_dict_tool(BASH)
SPEC = _LEGACY["spec"]
execute = _LEGACY["execute"]
