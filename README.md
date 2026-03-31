# Agentic Programming

A programming paradigm where LLM sessions are the compute units.

## Core Idea

Current agent frameworks let the LLM decide everything — what to do, in what order, when to stop — all in one conversation with unbounded context growth.

**Agentic Programming** structures LLM execution the same way programming languages structure CPU execution:

- **Programmer** (LLM): like a human developer — understands the task, selects or writes Functions, checks results, iterates
- **Function**: like source code — has a name, typed inputs/outputs, and natural language instructions
- **Runtime** (LLM Session): like a CPU — executes a single Function, returns a typed result, context destroyed

The Programmer never executes. The Runtime never plans. Context is isolated between them.

```python
# A Function is like a Python function — but executed by an LLM
observe = Function(
    name="observe",
    docstring="Observe the current screen state.",
    body="Take a screenshot and identify all visible UI elements...",
    params=["task"],
    return_type=ObserveResult,   # must return this, or retry
)

# Execute with any Runtime
result = runtime.execute(observe, context)  # returns ObserveResult — guaranteed
```

## The Programming Analogy

| Programming | Agentic Programming |
|-------------|---------------------|
| Programmer | Programmer (LLM) |
| Function / source code | Function (name + body + return_type) |
| Type signature | return_type (Pydantic schema) |
| CPU / interpreter | Runtime (ephemeral LLM Session) |
| Standard library | Function Pool (pre-built Skills) |
| Type checker | Schema Validator |

## Three Concepts

Everything is built from three primitives:

| Concept | Description |
|---------|-------------|
| **Function** | Typed unit of execution — name, docstring, body, params, return_type |
| **Runtime** | Executes a Function in an isolated Session — ephemeral, context destroyed after |
| **Programmer** | Plans and iterates — selects/creates Functions, sends to Runtime, checks results |

Plus a convenience layer:

| Concept | Description |
|---------|-------------|
| **Workflow** | Static mode — fixed sequence of Functions, no Programmer needed |

## Quick Start

### Static Mode (Workflow)

For tasks where the execution order is known:

```python
from harness import Function, Workflow, FunctionCall
from harness.session import AnthropicSession

observe = Function(
    name="observe",
    docstring="Observe the current screen state.",
    body=open("skills/observe/SKILL.md").read(),
    return_type=ObserveResult,
    params=["task"],
)

workflow = Workflow(
    calls=[
        FunctionCall(function=observe),
        FunctionCall(function=learn),
        FunctionCall(function=act),
        FunctionCall(function=verify),
    ],
    default_session=AnthropicSession(),
)
result = workflow.run(task="Click the login button")
```

### Dynamic Mode (Programmer + Runtime)

For complex tasks where the plan isn't known upfront:

```python
from harness import Function, Programmer, Runtime
from harness.session import AnthropicSession

programmer = Programmer(
    session=AnthropicSession(model="claude-sonnet-4-6"),
    runtime=Runtime(
        session_factory=lambda: AnthropicSession(model="claude-haiku")
    ),
    functions=[observe, learn, act, verify],
)

result = programmer.run("Open Safari and search for 'hello world' on Google")
# Programmer decides what to call, creates new Functions if needed,
# handles failures, and iterates until done.
```

## Context Isolation

The key mechanism:

```
Programmer Session (persistent):
  "observe returned: {target_visible: true}"
  "act returned: {success: true}"
  → Only structured summaries. Grows slowly.

Runtime Session A (ephemeral):
  "Function: observe. Take a screenshot..."
  → Created, executed, destroyed. Context gone.

Runtime Session B (ephemeral):
  "Function: act. Click the login button..."
  → Created, executed, destroyed. Context gone.
```

## Project Structure

```
harness/
├── function/      # Function definition and execution
├── session/       # Session interface and implementations
├── runtime/       # Runtime: isolated Function execution
├── programmer/    # Programmer: planning and decision loop
└── workflow/      # Static Workflow (convenience layer)

skills/            # Natural language Skill files (Function bodies)
├── programmer/SKILL.md
├── observe/SKILL.md
├── learn/SKILL.md
├── act/SKILL.md
└── verify/SKILL.md
```

## Sessions

Any class that implements `send(message: str) -> str` is a valid Session:

| Session | Description |
|---------|-------------|
| `AnthropicSession` | Direct Anthropic API |
| `OpenAISession` | Direct OpenAI API |
| `OpenClawSession` | Routes through OpenClaw agent |

## Install

```bash
pip install -r requirements.txt
```

## Run Tests

```bash
pip install pytest
pytest tests/ -v
```

## Design

See [docs/DESIGN.md](docs/DESIGN.md) for the full design specification.
