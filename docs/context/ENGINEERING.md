# Context Engineering

> How to use the Context system in Agentic Programming.

---

## 1. Quick Start

```python
from agentic import agentic_function, runtime, get_root_context
from agentic import WORKER, FOCUSED, LEAF

@agentic_function
def navigate(target):
    """Navigate to a target UI element."""
    obs = observe(task=f"find {target}")
    act(target=target, location=obs["location"])
    return {"success": True}

@agentic_function(context="inherit", context_policy=WORKER)
def observe(task):
    """Look at the screen and describe what you see."""
    img = take_screenshot()
    return runtime.exec(prompt=observe.__doc__, input={"task": task}, images=[img])

@agentic_function(context="inherit", context_policy=FOCUSED)
def act(target, location):
    """Click the target element."""
    click(location)
    return {"clicked": True}

navigate("login")
print(get_root_context().tree())
```

---

## 2. `@agentic_function`

Decorator that auto-tracks a function in the Context tree.

```python
@agentic_function(
    expose="summary",              # How others see my results (§3)
    context="auto",                # How I attach to the tree (§2.1)
    context_policy=None,           # What context I see (§4)
)
def my_function(): ...
```

### 2.1 `context` — Tree Attachment

| Value | Behavior |
|-------|----------|
| `"auto"` | Attach to parent if exists, create root if none. Default. |
| `"inherit"` | Must have parent. Raises `RuntimeError` if called standalone. |
| `"new"` | Create an independent tree. For background/parallel tasks. |
| `"none"` | No tracking. Pure Python execution. |

```python
@agentic_function                            # auto
def main(): ...

@agentic_function(context="inherit")         # must be sub-call
def observe(task): ...

@agentic_function(context="new")             # independent tree
def background_check(): ...

@agentic_function(context="none")            # no overhead
def pure_compute(x): ...
```

### 2.2 `expose` — How Others See Me

Controls how this function's results appear when other functions call `summarize()`.

| Value | Shows |
|-------|-------|
| `"trace"` | Prompt + full I/O + raw LLM reply |
| `"detail"` | `name(params) → status \| input \| output` |
| `"summary"` | `name: output_snippet duration` (default) |
| `"result"` | Return value only |
| `"silent"` | Not shown |

```python
@agentic_function(expose="detail")   # others see full I/O
def observe(task): ...

@agentic_function(expose="silent")   # invisible to siblings
def _helper(): ...
```

---

## 3. `runtime.exec()` — LLM Call

Calls the LLM and auto-records to the current Context node.

```python
reply = runtime.exec(
    prompt="Look at the screen...",     # LLM instructions
    input={"task": task},               # Structured data
    images=[img_path],                  # Media files
    context=None,                       # Override auto-generated context (optional)
    model="sonnet",                     # Model name
    call=my_llm_provider,              # Provider function: fn(messages, model) -> str
)
```

Context injection priority:
1. Explicit `context=` string → used as-is
2. `context_policy` on the decorator → `policy.apply(ctx)`
3. Neither → `ctx.summarize()` (all ancestors + all siblings)

---

## 4. Context Policies — Presets

Attach a policy to control what context your function sees when calling `runtime.exec()`.

```python
from agentic import ORCHESTRATOR, PLANNER, WORKER, LEAF, FOCUSED
```

| Preset | What it sees | Use case |
|--------|-------------|----------|
| `ORCHESTRATOR` | All children's return values | Top-level loops |
| `PLANNER` | Parent goal + last 5 siblings (progressive detail) | Decision-making |
| `WORKER` | Parent goal + auto-decaying siblings | Repeated calls (observe/act in loops) |
| `LEAF` | Nothing | Pure computation (OCR, detection) |
| `FOCUSED` | Parent goal + last sibling only | Sequential steps (act after observe) |

```python
@agentic_function(context_policy=ORCHESTRATOR)
def navigate(target): ...          # sees all results, no details

@agentic_function(context="inherit", context_policy=WORKER)
def observe(task): ...             # auto-decays as loop progresses

@agentic_function(context="inherit", context_policy=LEAF)
def run_ocr(img): ...              # zero context, just do OCR
```

### 4.1 Custom Policies

```python
from agentic import ContextPolicy

my_policy = ContextPolicy(
    depth=1,           # Only parent
    siblings=3,        # Last 3 siblings
    level="summary",   # One-line summaries
    max_tokens=500,    # Token budget
)

@agentic_function(context_policy=my_policy)
def my_function(): ...
```

### 4.2 Decay (for loops)

When a function is called many times, old siblings become irrelevant.

```python
policy = ContextPolicy(
    decay=True,
    decay_thresholds=[
        (5,  -1, "detail"),     # <5 calls: see all, full detail
        (15,  3, "summary"),    # 5-14 calls: last 3, summary
    ],
    decay_fallback_window=1,    # 15+ calls: only the most recent
    decay_fallback_level="result",
)
```

### 4.3 Progressive Detail

Within the visible window, closer siblings get more detail:

```python
policy = ContextPolicy(
    siblings=5,
    progressive_detail=[
        (1, "detail"),     # Most recent → detail
        (3, "summary"),    # 2nd-3rd → summary
    ],
    # 4th-5th → default level
)
```

### 4.4 Path Filtering

```python
# Only observe results, ignore act results
ContextPolicy(include=["*/observe_*"])

# Everything except a specific branch
ContextPolicy(exclude=["root/navigate_0/observe_0"])

# Show observe + all its children (run_ocr, detect_all)
ContextPolicy(branch=["observe"])
```

---

## 5. `summarize()` — Direct Query

For ad-hoc queries without a policy:

```python
from agentic import get_context

ctx = get_context()

ctx.summarize()                                    # Default: all ancestors + all siblings
ctx.summarize(depth=1, siblings=3)                 # Parent + last 3
ctx.summarize(depth=0, siblings=0)                 # Isolated (empty)
ctx.summarize(include=["root/nav_0/observe_1"])    # Specific node
ctx.summarize(branch=["observe"])                  # Subtree
ctx.summarize(level="trace")                       # Override all expose levels
ctx.summarize(max_tokens=1000)                     # Token budget
```

Full signature:

```python
ctx.summarize(
    depth=-1,              # Ancestor levels (-1=all, 0=none)
    siblings=-1,           # Sibling count (-1=all, 0=none)
    level=None,            # Override expose levels
    max_tokens=None,       # Token budget (drops oldest first)
    max_siblings=None,     # Legacy alias for siblings
    include=None,          # Path whitelist (supports * wildcard)
    exclude=None,          # Path blacklist
    branch=None,           # Show subtree of named nodes
)
```

---

## 6. Path Addressing

Every node has an auto-computed path: `parent_path/name_index`.

```python
ctx.path  # "root/navigate_0/observe_1/run_ocr_0"
```

Index counts same-name siblings (0-based). Paths support wildcards in `include`/`exclude`:

```python
"root/navigate_0/observe_1"       # Exact node
"root/navigate_0/*"               # All children of navigate_0
"root/*/observe_*"                # All observes under any parent
```

---

## 7. Tree Inspection

```python
from agentic import get_root_context

root = get_root_context()

# Tree view
print(root.tree())
# root …
#   navigate ✓ 3200ms → {'success': True}
#     observe ✓ 1200ms → {'found': True}
#     act ✓ 820ms → {'clicked': True}

# Error traceback
print(root.traceback())
# Agentic Traceback:
#   navigate(target="login") → error, 4523ms
#     act(target="login") → error, 820ms
#       error: element not interactable

# Save
root.save("run.md")       # Human-readable
root.save("run.jsonl")    # Machine-readable

# Programmatic access
root.children[0].name         # "navigate"
root.children[0].output       # {"success": True}
root.children[0].duration_ms  # 3200.0
```

---

## 8. Complete Example

```python
from agentic import agentic_function, runtime, get_root_context
from agentic import ORCHESTRATOR, WORKER, FOCUSED, LEAF

@agentic_function(context_policy=ORCHESTRATOR)
def navigate(target):
    """Navigate to a target UI element."""
    for step in range(20):
        obs = observe(task=f"find {target}")
        if obs.get("found"):
            act(target=target, location=obs["location"])
            if verify(target):
                return {"success": True, "steps": step}
    return {"success": False}

@agentic_function(context="inherit", expose="summary", context_policy=WORKER)
def observe(task):
    """Look at the screen and describe what you see."""
    img = take_screenshot()
    return runtime.exec(prompt=observe.__doc__, input={"task": task},
                        images=[img], call=my_llm)

@agentic_function(context="inherit", expose="result", context_policy=FOCUSED)
def act(target, location):
    """Click the target element."""
    click(location)
    return {"clicked": True}

@agentic_function(context="inherit", expose="result", context_policy=LEAF)
def verify(target):
    """Check if navigation succeeded."""
    img = take_screenshot()
    return runtime.exec(prompt=verify.__doc__, input={"target": target},
                        images=[img], call=my_llm)

navigate("login")
get_root_context().save("navigation.jsonl")
```
