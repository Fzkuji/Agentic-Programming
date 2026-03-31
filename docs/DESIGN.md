# Agentic Programming — Design Specification

> A programming paradigm where LLM sessions are the compute units.

---

## 1. Motivation

Current LLM agent frameworks have a fundamental problem: they treat the LLM as both the brain and the hands. The agent decides what to do, and the agent does it — all in one conversation, with context growing until it overflows or degrades.

When you need reliable, repeatable behavior — like GUI automation where every step must be verified — this is a blocker. The LLM might skip steps, take shortcuts, or decide it's done when it isn't.

### The Core Problem

Today's approaches fall into two extremes:

- **Pure code**: deterministic but rigid, can't handle ambiguity
- **Pure LLM agent**: flexible but unpredictable, context grows unbounded

Neither works for complex, real-world tasks that need both structure and intelligence.

### The Insight

What if we structured LLM execution the same way programming languages structure CPU execution?

In programming:
- A **programmer** writes functions with typed inputs and outputs
- A **runtime** executes each function
- The programmer doesn't manually move bits — the runtime handles that
- Each function call has its own scope — context doesn't leak

**Agentic Programming** applies this exact structure to LLM agents.

---

## 2. Core Concepts

There are only three concepts. Everything else is built from these.

### 2.1 Function

The fundamental unit of execution. Like a function in Python — has a name, a docstring, a body, parameters, and a return type.

| Field | Required | Description |
|-------|----------|-------------|
| name | Yes | Identifier, e.g. "observe" |
| docstring | Yes | What this function does (1-2 sentences) |
| body | Yes | How to do it — natural language instructions (the Skill) |
| return_type | Yes | Pydantic model this function MUST return |
| params | No | Which context keys to read (None = full context) |
| examples | No | Sample input/output pairs to guide the LLM |
| max_retries | No | How many times to retry if output is invalid (default: 3) |

**Key rules:**
- A Function does not complete until its output matches `return_type`
- A Function is stateless — all input comes from `params`
- A Function's `body` is natural language, not code
- A Function can be executed by ANY Session — it's runtime-agnostic

### 2.2 Runtime

The execution environment. Like a Python interpreter — it runs Functions and returns typed results.

```python
class Runtime:
    def execute(self, function: Function, context: dict) -> BaseModel:
        session = self.session_factory()  # fresh session
        result = function.call(session, context)
        # session is discarded — context gone
        return result
```

**Key rules:**
- Each execution creates a **fresh Session** (ephemeral)
- The Session is destroyed after the Function returns
- This is how context isolation works — execution details never leak out
- Only the structured return value propagates back

### 2.3 Programmer

The planning and decision-making agent. Like a human programmer — it understands the task, selects or writes Functions, sends them to the Runtime for execution, and iterates based on results.

```python
class Programmer:
    def run(self, task: str) -> ProgrammerResult:
        # Loop: think → decide → execute → check → repeat
```

**Key rules:**
- The Programmer has a **persistent Session** (it remembers what it tried)
- It only sees **structured return values** from Functions, never execution details
- It can **create new Functions** at runtime
- It is itself driven by a Function (programmer_fn) — staying within the paradigm

### How they interact

```
Programmer (persistent Session — remembers across steps)
  │
  │  "I need to see what's on screen"
  │  → picks observe Function
  │
  ├── Runtime → creates fresh Session → executes observe() → returns ObserveResult → Session destroyed
  │
  │  "Target is visible, I'll click it"
  │  → picks act Function
  │
  ├── Runtime → creates fresh Session → executes act() → returns ActResult → Session destroyed
  │
  │  "Let me verify"
  │  → picks verify Function
  │
  ├── Runtime → creates fresh Session → executes verify() → returns VerifyResult → Session destroyed
  │
  │  "Done!"
  └── returns ProgrammerResult
```

---

## 3. Context Isolation

This is the core mechanism that makes Agentic Programming work.

### Why it matters

Without isolation, every execution detail accumulates in one conversation:
- Screenshots, UI element lists, retry attempts, error messages
- Context window fills up, cost increases, performance degrades
- Irrelevant information confuses subsequent steps

With isolation:
- Each Runtime execution starts clean
- Only structured return values propagate to the Programmer
- The Programmer's context grows slowly (just summaries)

### How it works

```
Programmer Session (persistent):
  [task description]
  [decision: call observe]
  [observe returned: {current_state: "homepage", target_visible: true}]
  [decision: call act]
  [act returned: {success: true}]
  → Compact. Only structured data. Grows slowly.

Runtime Session A (ephemeral):
  [Function message: "observe the screen..."]
  [reply: {current_state: ..., elements: [...50 items...]}]
  → Destroyed. All 50 elements gone. Only the summary reached the Programmer.

Runtime Session B (ephemeral):
  [Function message: "click the login button..."]
  [reply: {action_taken: "click", success: true}]
  → Destroyed.
```

---

## 4. Execution Model

### 4.1 Single Function Execution

```
1. Extract params from context
2. Assemble call message:
   - Function name + docstring
   - Body (natural language instructions)
   - Arguments (from params)
   - Return type schema
3. Send to Session
4. Parse reply → validate against return_type
   - Valid   → return typed result
   - Invalid → retry with correction (up to max_retries)
   - Exhausted → raise FunctionError
```

### 4.2 Programmer Loop

```
1. Create persistent Session for Programmer
2. Initialize context: {task, history: [], available_functions: [...]}
3. Loop:
   a. Call programmer_fn → returns ProgrammerDecision
   b. Match decision.action:
      - "call"   → Runtime.execute(function, context) → append result to history
      - "create" → build new Function from spec → add to pool
      - "reply"  → return message to user
      - "done"   → return success
      - "fail"   → return failure with reason
   c. Continue loop
4. Safety: stop after max_iterations
```

### 4.3 Static Workflow (convenience)

For known sequences, Workflow provides a shortcut — no Programmer needed:

```python
workflow = Workflow(
    calls=[observe, learn, act, verify],
    default_session=session,
)
result = workflow.run(task="Click login")
```

Equivalent to a Programmer that always makes the same decisions in the same order.

---

## 5. Function Lifecycle

### Pre-built (standard library)

```
skills/
├── observe/SKILL.md
├── learn/SKILL.md
├── act/SKILL.md
└── verify/SKILL.md
```

Loaded at startup. Always available in the Function pool.

### Dynamically created

The Programmer can create new Functions at runtime by specifying name, docstring, body, params, and return_type_schema. The framework builds the Function and adds it to the pool.

### Persisted (optional)

Created Functions can be saved to disk as SKILL.md files for reuse across runs.

---

## 6. Session Contract

Any class that implements `send(message: str) -> str` is a valid Session:

```python
class Session(ABC):
    @abstractmethod
    def send(self, message: str) -> str:
        pass
```

The Session handles:
- Its own conversation history
- Its own connection and authentication
- Returning complete (not streamed) replies

The Session does NOT handle:
- Parsing return values (Function does that)
- Retry logic (Function does that)
- Deciding what to do next (Programmer does that)

---

## 7. Error Handling

### Function-level
If a Function can't return valid output after max_retries → raises FunctionError.
The Programmer catches this and decides: retry? different Function? fail?

### Programmer-level
If the Programmer can't make a valid decision → retry the programmer_fn.
If exhausted → task fails.

### Task-level
The Programmer can explicitly decide `action: "fail"`. This is deliberate, not an error.

---

## 8. Design Principles

| Principle | Description |
|-----------|-------------|
| **Three concepts only** | Programmer, Function, Runtime. That's it. |
| **Context isolation** | Runtime Sessions are ephemeral. Only returns propagate. |
| **Outputs are contracts** | Functions don't return until output matches the schema. |
| **Programmer is a programmer** | It plans, selects, creates, but never executes. |
| **Sessions are pluggable** | Any LLM, any platform. Functions never change. |
| **Failure is explicit** | Functions fail loudly. Programmer handles recovery. |

---

## 9. Comparison

| | Prompted Agent | Tool-calling Agent | Agentic Programming |
|---|---|---|---|
| Who decides next step | LLM (free-form) | LLM (picks from tools) | Programmer (structured) |
| Execution isolation | None | Partial | Full (separate Sessions) |
| Output guarantee | None | Tool-dependent | Pydantic schema enforced |
| Can create new capabilities | No | No | Yes (Programmer creates Functions) |
| Context growth | Unbounded | Unbounded | Controlled (only summaries) |
