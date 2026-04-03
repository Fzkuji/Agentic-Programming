"""
meta — Meta Agentic Function: create new agentic functions from natural language.

The single primitive: create(). Given a task description and a Runtime,
it asks the LLM to write a new @agentic_function, executes the code
safely, validates the result, and returns a callable function.

Usage:
    from agentic import Runtime
    from agentic.meta import create

    runtime = Runtime(call=my_llm, model="sonnet")

    # Create a new function from description
    summarize = create(
        "Summarize a given text into 3 bullet points",
        runtime=runtime,
    )

    # Use it like any other agentic function
    result = summarize(text="Long article here...")
"""

from __future__ import annotations

import re
import textwrap
from typing import Optional

from agentic.function import agentic_function
from agentic.runtime import Runtime


# ── Code generation prompt ──────────────────────────────────────

_GENERATE_PROMPT = """\
Write a Python function that does the following:

{description}

Rules:
1. Decorate with @agentic_function
2. Write a clear docstring — this becomes the LLM prompt
3. Use runtime.exec() to call the LLM when reasoning is needed
4. Content is a list of dicts: [{{"type": "text", "text": "..."}}]
5. Return a meaningful result (string or dict)
6. Use only standard Python — no imports needed
7. Do NOT use async/await — write a normal synchronous function

`agentic_function` and `runtime` are already available in scope.

Write ONLY the function definition. No imports, no examples, no explanation.
Start with @agentic_function and end with the return statement.
"""

# ── Validation ──────────────────────────────────────────────────

_ALLOWED_BUILTINS = {
    # Safe builtins — no file I/O, no exec, no import
    "abs", "all", "any", "bool", "chr", "dict", "dir", "divmod",
    "enumerate", "filter", "float", "format", "frozenset", "hasattr",
    "hash", "hex", "id", "int", "isinstance", "issubclass", "iter",
    "len", "list", "map", "max", "min", "next", "oct", "ord", "pow",
    "print", "range", "repr", "reversed", "round", "set", "slice",
    "sorted", "str", "sum", "tuple", "type", "zip",
    # Also allow these for practical code
    "True", "False", "None", "ValueError", "TypeError", "KeyError",
    "IndexError", "RuntimeError", "Exception",
}


def _make_safe_builtins() -> dict:
    """Create a restricted builtins dict."""
    import builtins
    safe = {}
    for name in _ALLOWED_BUILTINS:
        if hasattr(builtins, name):
            safe[name] = getattr(builtins, name)
    # Block dangerous operations
    safe["__import__"] = _blocked_import
    return safe


def _blocked_import(name, *args, **kwargs):
    raise ImportError(
        f"Import '{name}' is not allowed in generated functions. "
        f"Use runtime.exec() for any task that needs external libraries."
    )


def _extract_code(response: str) -> str:
    """Extract Python code from LLM response, stripping markdown fences."""
    # Try to find code block
    match = re.search(r"```(?:python)?\s*\n(.*?)```", response, re.DOTALL)
    if match:
        return match.group(1).strip()

    # If no code block, try to find @agentic_function
    match = re.search(r"(@agentic_function.*)", response, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Last resort: return as-is
    return response.strip()


def _find_function(namespace: dict, runtime: Runtime) -> Optional[callable]:
    """Find the generated agentic_function in the namespace."""
    for name, obj in namespace.items():
        if name.startswith("_"):
            continue
        if isinstance(obj, agentic_function):
            return obj
    return None


# ── Core: create() ──────────────────────────────────────────────

@agentic_function
def create(description: str, runtime: Runtime, name: str = None) -> callable:
    """Create a new @agentic_function from a natural language description.

    Args:
        description:  What the function should do.
        runtime:      Runtime instance for LLM calls (used both to generate
                      the code and injected into the generated function).
        name:         Optional name override for the generated function.

    Returns:
        A callable @agentic_function ready to use.

    Raises:
        ValueError:   If the LLM generates invalid or unsafe code.
        SyntaxError:  If the generated code has syntax errors.
    """
    # Step 1: Ask LLM to write the function
    response = runtime.exec(content=[
        {"type": "text", "text": _GENERATE_PROMPT.format(description=description)},
    ])

    # Step 2: Extract code from response
    code = _extract_code(response)

    # Step 3: Validate — no import or async
    for line in (response + "\n" + code).split("\n"):
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            raise ValueError(
                f"Generated code contains import statements (not allowed):\n{code}"
            )
        if stripped.startswith("async def ") or stripped.startswith("async "):
            raise ValueError(
                f"Generated code uses async (not allowed, use sync functions):\n{code}"
            )

    # Step 3b: Validate syntax before executing
    try:
        compile(code, "<generated>", "exec")
    except SyntaxError as e:
        raise SyntaxError(
            f"Generated code has syntax errors:\n{code}\n\nError: {e}"
        ) from e

    # Step 5: Execute in sandboxed namespace
    namespace = {
        "__builtins__": _make_safe_builtins(),
        "agentic_function": agentic_function,
        "runtime": runtime,
    }

    try:
        exec(code, namespace)
    except Exception as e:
        raise ValueError(
            f"Generated code failed to execute:\n{code}\n\nError: {e}"
        ) from e

    # Step 6: Find the generated function
    fn = _find_function(namespace, runtime)
    if fn is None:
        raise ValueError(
            f"Generated code does not contain an @agentic_function:\n{code}"
        )

    # Step 7: Override name if requested
    if name:
        fn.__name__ = name
        fn.__qualname__ = name

    return fn
