---
name: meta-function
description: "Create new Python functions from natural language descriptions, or fix broken ones. Use when: (1) you need a function that doesn't exist yet, (2) an existing function has bugs. Triggers: 'create a function', 'generate a function', 'fix this function', 'make a function that...'."
---

# Meta Function

Create and fix Python functions using LLM.

## Setup

```bash
pip install -e /path/to/Agentic-Programming
```

## Create a new function

```python
from agentic.meta_function import create
from agentic.providers import ClaudeCodeRuntime

runtime = ClaudeCodeRuntime()
fn = create("<DESCRIPTION>", runtime=runtime, name="<NAME>")
result = fn(<PARAMS>)
```

- Deterministic tasks → generates pure Python
- Reasoning tasks → generates `@agentic_function` with `runtime.exec()`
- Auto-saved to `agentic/functions/<NAME>.py`
- Add `as_skill=True` to also create a `skills/<NAME>/SKILL.md` for agent discovery:

```python
fn = create("...", runtime=runtime, name="my_tool", as_skill=True)
# Now skills/my_tool/SKILL.md exists and agents can find it
```

Use `as_skill=True` for top-level entry-point functions.
Don't use it for internal helpers that other functions call.

## Fix a function

```python
from agentic.meta_function import fix

fixed = fix(fn=broken_fn, runtime=runtime, instruction="<WHAT_TO_CHANGE>")
```
