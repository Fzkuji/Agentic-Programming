"""
Programmer — the planning and decision-making agent.

In traditional programming:
    - A programmer reads requirements
    - Looks at available libraries/functions
    - Writes new functions if needed
    - Calls functions in the right order
    - Checks results, handles errors, iterates

In Agentic Programming:
    - The Programmer (an LLM with a persistent Session) does the same thing
    - It sees the task, browses the Function pool, selects or creates Functions
    - It hands Functions to the Runtime for execution
    - It only sees structured return values — never the execution details
    - It iterates until the task is done or it determines it can't be done

The Programmer is itself driven by a Function (the programmer_fn), which defines
how it thinks and what decisions it can make. This keeps even the Programmer
within the typed, structured paradigm.
"""

from __future__ import annotations

import json
from typing import Optional
from pydantic import BaseModel

from harness.function import Function, FunctionError
from harness.session import Session
from harness.runtime import Runtime


# ------------------------------------------------------------------
# Decision schema — what the Programmer returns each iteration
# ------------------------------------------------------------------

class NewFunctionSpec(BaseModel):
    """Specification for a dynamically created Function."""
    name: str
    docstring: str
    body: str
    params: Optional[list[str]] = None
    return_type_schema: dict  # JSON Schema


class ProgrammerDecision(BaseModel):
    """
    The Programmer's decision each iteration.

    action:
        - "call"   → call an existing Function
        - "create" → create a new Function, then (optionally) call it
        - "reply"  → send a message back to the user
        - "done"   → task is complete
        - "fail"   → task cannot be completed
    """
    action: str
    reasoning: str

    # for action == "call"
    function_name: Optional[str] = None
    function_args: Optional[dict] = None

    # for action == "create"
    new_function: Optional[NewFunctionSpec] = None

    # for action == "reply"
    reply_text: Optional[str] = None

    # for action == "fail"
    failure_reason: Optional[str] = None


# ------------------------------------------------------------------
# Result
# ------------------------------------------------------------------

class ProgrammerResult(BaseModel):
    """Final result of a Programmer run."""
    success: bool
    context: dict
    reply: Optional[str] = None
    failure_reason: Optional[str] = None
    iterations: int = 0


# ------------------------------------------------------------------
# Programmer
# ------------------------------------------------------------------

class Programmer:
    """
    The planning agent. Like a human programmer:
    - Reads the task
    - Selects or writes Functions
    - Sends them to the Runtime for execution
    - Checks results, iterates

    The Programmer has a persistent Session (it remembers what it tried).
    The Runtime has ephemeral Sessions (each execution is isolated).

    Args:
        session:          Persistent LLM Session for the Programmer's thinking
        runtime:          Runtime that executes Functions (ephemeral Sessions)
        functions:        Initial pool of available Functions
        programmer_fn:    The Function that defines how the Programmer thinks
                          (if None, a default is used)
        max_iterations:   Safety limit on how many iterations to run
    """

    def __init__(
        self,
        session: Session,
        runtime: Runtime,
        functions: Optional[list[Function]] = None,
        programmer_fn: Optional[Function] = None,
        max_iterations: int = 50,
    ):
        self.session = session
        self.runtime = runtime
        self.functions: dict[str, Function] = {}
        if functions:
            for fn in functions:
                self.functions[fn.name] = fn
        self.programmer_fn = programmer_fn or self._default_programmer_fn()
        self.max_iterations = max_iterations

    def run(self, task: str, initial_context: Optional[dict] = None) -> ProgrammerResult:
        """
        Run the Programmer on a task.

        The Programmer loops: think → decide → execute → observe result → repeat.

        Args:
            task:             The task description
            initial_context:  Optional starting context

        Returns:
            ProgrammerResult with success status, context, and optional reply
        """
        context = dict(initial_context or {})
        context["task"] = task
        context["history"] = []

        for iteration in range(1, self.max_iterations + 1):
            # Build the Programmer's input
            programmer_context = self._build_programmer_context(context)

            # Ask the Programmer what to do next
            try:
                decision = self.programmer_fn.call(
                    session=self.session,
                    context=programmer_context,
                )
            except FunctionError as e:
                return ProgrammerResult(
                    success=False,
                    context=context,
                    failure_reason=f"Programmer failed to make a decision: {e}",
                    iterations=iteration,
                )

            # Execute the decision
            action = decision.action

            if action == "call":
                result = self._execute_call(decision, context)
                context["history"].append({
                    "iteration": iteration,
                    "action": "call",
                    "function": decision.function_name,
                    "reasoning": decision.reasoning,
                    "result": result,
                })

            elif action == "create":
                fn_name = self._execute_create(decision)
                context["history"].append({
                    "iteration": iteration,
                    "action": "create",
                    "function": fn_name,
                    "reasoning": decision.reasoning,
                })

            elif action == "reply":
                return ProgrammerResult(
                    success=True,
                    context=context,
                    reply=decision.reply_text,
                    iterations=iteration,
                )

            elif action == "done":
                return ProgrammerResult(
                    success=True,
                    context=context,
                    iterations=iteration,
                )

            elif action == "fail":
                return ProgrammerResult(
                    success=False,
                    context=context,
                    failure_reason=decision.failure_reason or decision.reasoning,
                    iterations=iteration,
                )

            else:
                context["history"].append({
                    "iteration": iteration,
                    "action": "unknown",
                    "reasoning": f"Unknown action: {decision.action}",
                })

        return ProgrammerResult(
            success=False,
            context=context,
            failure_reason=f"Max iterations ({self.max_iterations}) reached",
            iterations=self.max_iterations,
        )

    # ------------------------------------------------------------------
    # Private methods
    # ------------------------------------------------------------------

    def _build_programmer_context(self, context: dict) -> dict:
        """Build the context that the Programmer Function sees."""
        available_functions = []
        for name, fn in self.functions.items():
            available_functions.append({
                "name": name,
                "docstring": fn.docstring,
                "params": fn.params,
                "return_type": fn.return_type.model_json_schema(),
            })

        return {
            "task": context["task"],
            "history": context.get("history", []),
            "available_functions": available_functions,
        }

    def _execute_call(self, decision: ProgrammerDecision, context: dict) -> dict:
        """Execute a Function call via the Runtime."""
        fn_name = decision.function_name
        if fn_name not in self.functions:
            return {"error": f"Function '{fn_name}' not found in pool"}

        fn = self.functions[fn_name]

        # Merge function_args into context for param extraction
        call_context = dict(context)
        if decision.function_args:
            call_context.update(decision.function_args)

        try:
            result = self.runtime.execute(fn, call_context)
            return result.model_dump()
        except FunctionError as e:
            return {"error": str(e)}

    def _execute_create(self, decision: ProgrammerDecision) -> str:
        """Create a new Function and add it to the pool."""
        spec = decision.new_function
        if spec is None:
            return "(no spec provided)"

        # Build a dynamic Pydantic model from the JSON schema
        return_type = self._schema_to_model(spec.name, spec.return_type_schema)

        new_fn = Function(
            name=spec.name,
            docstring=spec.docstring,
            body=spec.body,
            return_type=return_type,
            params=spec.params,
        )
        self.functions[new_fn.name] = new_fn
        return new_fn.name

    @staticmethod
    def _schema_to_model(name: str, schema: dict) -> type:
        """
        Build a Pydantic model from a JSON Schema dict.

        Simple implementation that handles basic types.
        For complex schemas, consider using pydantic's schema-based construction.
        """
        from pydantic import create_model

        type_map = {
            "string": str,
            "integer": int,
            "number": float,
            "boolean": bool,
        }

        fields = {}
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))

        for field_name, field_schema in properties.items():
            field_type_str = field_schema.get("type", "string")

            if field_type_str == "array":
                item_type_str = field_schema.get("items", {}).get("type", "string")
                item_type = type_map.get(item_type_str, str)
                field_type = list[item_type]
            else:
                field_type = type_map.get(field_type_str, str)

            if field_name in required:
                fields[field_name] = (field_type, ...)
            else:
                fields[field_name] = (Optional[field_type], None)

        model_name = f"Dynamic_{name}"
        return create_model(model_name, **fields)

    @staticmethod
    def _default_programmer_fn() -> Function:
        """Create the default Programmer Function."""
        default_body = """You are a Programmer. Your job is to accomplish the given task
by selecting and calling available Functions, or creating new ones when needed.

## How to think

1. Read the task carefully
2. Look at the available functions — is there one that helps with the next step?
3. If yes → call it
4. If no → create a new function that does what you need
5. After each function returns, check the result
6. Decide: continue? try something else? done? give up?

## Rules

- You NEVER execute tasks yourself. You ALWAYS delegate to Functions via the Runtime.
- You only see structured return values from Functions, not their internal execution.
- Think step by step. Don't try to do everything at once.
- If a Function fails, analyze why and try a different approach.
- If the task is impossible, say so clearly (action: "fail").

## Available actions

- "call": call an existing Function from the pool
- "create": define a new Function and add it to the pool
- "reply": send a message back to the user
- "done": task is complete
- "fail": task cannot be completed
"""
        return Function(
            name="programmer",
            docstring="Decide the next step to accomplish the task.",
            body=default_body,
            return_type=ProgrammerDecision,
            params=["task", "history", "available_functions"],
        )
