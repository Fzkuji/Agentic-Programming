# Context Engineering

> `agentic/` — Context system API reference.

---

## `agentic_function`

```python
agentic.agentic_function(fn=None, *, expose="summary", context="auto", context_policy=None)
```

Decorator that automatically records function execution into the Context tree.

**Parameters:**

- **expose** (`str`, default `"summary"`) — How this function's results appear to other functions.

  | Value | Output |
  |-------|--------|
  | `"trace"` | Prompt + full I/O + raw LLM reply + error |
  | `"detail"` | `name(params) → status \| input \| output` |
  | `"summary"` | `name: output_snippet duration` |
  | `"result"` | Return value only (JSON) |
  | `"silent"` | Not shown |

- **context** (`str`, default `"auto"`) — How this function attaches to the Context tree.

  | Value | Behavior |
  |-------|----------|
  | `"auto"` | Attach to parent if exists, create root if none |
  | `"inherit"` | Must have parent; raises `RuntimeError` if called standalone |
  | `"new"` | Always create an independent tree |
  | `"none"` | No Context tracking at all |

- **context_policy** (`ContextPolicy` or `None`, default `None`) — Controls what context gets injected when `runtime.exec()` is called inside this function. If `None`, uses default `ctx.summarize()` (all ancestors + all siblings). See [ContextPolicy](#contextpolicy).

**Example:**

```python
from agentic import agentic_function

@agentic_function
def navigate(target):
    """Navigate to a target UI element."""
    ...

@agentic_function(expose="detail", context="inherit")
def observe(task):
    """Look at the screen."""
    ...
```

---

## `runtime.exec`

```python
agentic.runtime.exec(prompt, input=None, images=None, context=None, schema=None, model="sonnet", call=None)
```

Call an LLM and auto-record to the current Context node.

**Parameters:**

- **prompt** (`str`) — Instructions for the LLM.
- **input** (`dict`, optional) — Structured data to include.
- **images** (`list[str]`, optional) — Image file paths.
- **context** (`str`, optional) — Override the auto-generated context string. If provided, used as-is. If `None`, auto-generated:
  1. From `context_policy.apply(ctx)` if the function has a policy
  2. From `ctx.summarize()` otherwise
- **schema** (`dict`, optional) — Expected JSON output schema.
- **model** (`str`, default `"sonnet"`) — Model name or alias.
- **call** (`Callable`, optional) — LLM provider function with signature `fn(messages, model) -> str`. If `None`, raises `NotImplementedError`.

**Returns:** `str` — LLM reply.

**Example:**

```python
from agentic import agentic_function, runtime

@agentic_function(context="inherit")
def observe(task):
    """Look at the screen and describe what you see."""
    img = take_screenshot()
    return runtime.exec(
        prompt=observe.__doc__,
        input={"task": task},
        images=[img],
        call=my_llm_provider,
    )
```

---

## `ContextPolicy`

```python
agentic.ContextPolicy(depth=-1, siblings=-1, level="summary", decay=False, decay_thresholds=None, decay_fallback_window=1, decay_fallback_level="result", progressive_detail=None, cache_stable=True, include=None, exclude=None, branch=None, max_tokens=None)
```

Controls what context gets injected into LLM calls for a function.

**Parameters:**

- **depth** (`int`, default `-1`) — How many ancestor levels to include.

  | Value | Effect |
  |-------|--------|
  | `-1` | All ancestors from root to parent |
  | `0` | No ancestors |
  | `1` | Parent only |
  | `N` | Up to N levels |

- **siblings** (`int`, default `-1`) — How many previous siblings to include (most recent first). Overridden by `decay` when `decay=True`.

  | Value | Effect |
  |-------|--------|
  | `-1` | All siblings |
  | `0` | No siblings |
  | `N` | Last N siblings |

- **level** (`str`, default `"summary"`) — Default render level for siblings. Same values as `expose`.

- **decay** (`bool`, default `False`) — Enable automatic recency decay. When `True`, the number of visible siblings and their render level change based on how many siblings exist.

- **decay_thresholds** (`list[tuple]`, optional) — List of `(max_n_siblings, window, level)`. Checked in order; first match wins. Default:
  ```python
  [
      (5,  -1, "detail"),     # <5 siblings: show all at detail
      (15,  3, "summary"),    # 5-14 siblings: last 3 at summary
  ]
  ```

- **decay_fallback_window** (`int`, default `1`) — Window when sibling count exceeds all thresholds.

- **decay_fallback_level** (`str`, default `"result"`) — Level when sibling count exceeds all thresholds.

- **progressive_detail** (`list[tuple]`, optional) — Vary render level by recency within the visible window. List of `(recency, level)` where recency=1 is the most recent sibling. Example:
  ```python
  [(1, "detail"), (3, "summary")]
  # Most recent → detail, 2nd-3rd → summary, older → default level
  ```

- **cache_stable** (`bool`, default `True`) — Freeze each sibling's rendering after first render. Preserves prompt cache prefixes across calls.

- **include** (`list[str]`, optional) — Path whitelist. Only show nodes matching these paths. Supports `*` wildcard.

- **exclude** (`list[str]`, optional) — Path blacklist. Hide matching nodes.

- **branch** (`list[str]`, optional) — Show entire subtree under nodes with these names.

- **max_tokens** (`int`, optional) — Token budget. Drops oldest siblings first.

**Example:**

```python
from agentic import agentic_function, ContextPolicy

policy = ContextPolicy(
    depth=1,
    siblings=3,
    level="summary",
    max_tokens=500,
)

@agentic_function(context_policy=policy)
def my_function(): ...
```

### Preset Policies

| Preset | depth | siblings | level | decay | Description |
|--------|-------|----------|-------|-------|-------------|
| `ORCHESTRATOR` | `0` | `-1` (all) | `"result"` | No | Top-level loops |
| `PLANNER` | `1` | `5` | `"summary"` | No | Decision-making, with progressive detail |
| `WORKER` | `1` | (decay) | (decay) | **Yes** | Repeated calls in loops |
| `LEAF` | `0` | `0` | `"result"` | No | Pure computation, zero overhead |
| `FOCUSED` | `1` | `1` | `"detail"` | No | Only needs the previous sibling |

```python
from agentic import ORCHESTRATOR, PLANNER, WORKER, LEAF, FOCUSED

@agentic_function(context_policy=WORKER)
def observe(task): ...
```

---

## `Context`

```python
agentic.Context
```

Dataclass representing one function execution record. Managed automatically by `@agentic_function` and `runtime.exec()`.

### Fields

| Field | Type | Set by | Description |
|-------|------|--------|-------------|
| `name` | `str` | decorator | Function name |
| `prompt` | `str` | decorator | Docstring |
| `params` | `dict` | decorator | Call arguments |
| `output` | `Any` | decorator | Return value |
| `error` | `str` | decorator | Error message |
| `status` | `str` | decorator | `"running"` / `"success"` / `"error"` |
| `parent` | `Context` | decorator | Parent node |
| `children` | `list` | decorator | Child nodes |
| `expose` | `str` | decorator | Render level hint |
| `start_time` | `float` | decorator | Start timestamp |
| `end_time` | `float` | decorator | End timestamp |
| `input` | `dict` | `runtime.exec()` | Data sent to LLM |
| `media` | `list` | `runtime.exec()` | Media file paths |
| `raw_reply` | `str` | `runtime.exec()` | LLM response text |

### Properties

- **`path`** — Auto-computed address. Format: `parent_path/name_index`. Example: `"root/navigate_0/observe_1/run_ocr_0"`.
- **`duration_ms`** — Execution duration in milliseconds.

### Methods

#### `summarize`

```python
Context.summarize(level=None, max_tokens=None, max_siblings=None, depth=-1, siblings=-1, include=None, exclude=None, branch=None)
```

Query the Context tree and generate a text summary. Parameters match [ContextPolicy](#contextpolicy) fields.

```python
ctx.summarize()                                    # all ancestors + all siblings
ctx.summarize(depth=1, siblings=3)                 # parent + last 3
ctx.summarize(depth=0, siblings=0)                 # empty (isolated)
ctx.summarize(include=["root/nav_0/observe_1"])    # specific node
ctx.summarize(branch=["observe"])                  # observe + its children
ctx.summarize(level="trace")                       # override all expose levels
ctx.summarize(max_tokens=1000)                     # with token budget
```

#### `tree`

```python
Context.tree(indent=0) -> str
```

Human-readable tree view.

```
root …
  navigate ✓ 3200ms → {'success': True}
    observe ✓ 1200ms → {'found': True}
      run_ocr ✓ 50ms → {'texts': ['Login']}
    act ✓ 820ms → {'clicked': True}
```

#### `traceback`

```python
Context.traceback() -> str
```

Error traceback, similar to Python's format.

```
Agentic Traceback:
  navigate(target="login") → error, 4523ms
    observe(task="find login") → success, 1200ms
    act(target="login") → error, 820ms
      error: element not interactable
```

#### `save`

```python
Context.save(path: str)
```

Save tree to file. `.md` for human-readable, `.jsonl` for machine-readable.

---

## Module Functions

```python
agentic.get_context() -> Context | None
```

Get the current Context node. Returns `None` if outside any `@agentic_function`.

```python
agentic.get_root_context() -> Context | None
```

Get the root of the Context tree. Walks up from current node.

```python
agentic.init_root(name="root") -> Context
```

Manually create a root node. Usually not needed — `context="auto"` handles this.
