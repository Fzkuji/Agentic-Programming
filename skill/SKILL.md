---
name: agentic-programming
description: "Create, run, and fix Python functions using Agentic Programming. Has two capabilities: (1) meta functions — create() to generate new functions, fix() to repair broken ones; (2) ready-made functions in agentic/functions/. Use when you need a new function, need to fix one, or want to run an existing agentic function."
---

# Agentic Programming Skill

## Available Commands

### Create a new function

```bash
python -c "
from agentic.meta_function import create
from agentic.providers import ClaudeCodeRuntime
runtime = ClaudeCodeRuntime()
fn = create('YOUR DESCRIPTION HERE', runtime=runtime, name='YOUR_NAME')
print(fn(YOUR_PARAMS))
"
```

The function is automatically saved to `agentic/functions/YOUR_NAME.py`.

### Fix an existing function

```bash
python -c "
from agentic.meta_function import fix
from agentic.providers import ClaudeCodeRuntime
from agentic.functions.FUNCTION_NAME import FUNCTION_NAME
runtime = ClaudeCodeRuntime()
fixed = fix(fn=FUNCTION_NAME, runtime=runtime, instruction='WHAT TO CHANGE')
"
```

### Run an existing function

```bash
python -c "
from agentic.functions.FUNCTION_NAME import FUNCTION_NAME
print(FUNCTION_NAME(PARAMS))
"
```

## Available Functions

Check `agentic/functions/` for all saved functions. Current examples:

- `list_files(path)` — List files and folders in a directory (pure Python)
- `sentiment(text)` — Analyze text sentiment: positive/negative/neutral (uses LLM)
