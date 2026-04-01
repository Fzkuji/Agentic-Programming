"""
Function — the core unit of Agentic Programming.

A Function is a Python function whose body is executed by an LLM.
The docstring IS the prompt — change the docstring, change the behavior.

    @function(return_type=ObserveResult)
    def observe(session, task: str):
        '''Look at the screen. Find all buttons, text fields, and links.
        Report which elements are visible and whether the target is found.'''

    result = observe(session, task="find login button")
"""

from __future__ import annotations

import functools
import json
from typing import Type, TypeVar, Callable
from pydantic import BaseModel

from harness.session import Session

T = TypeVar("T", bound=BaseModel)


class FunctionError(Exception):
    """Raised when a Function fails after all retries."""
    def __init__(self, function_name: str, message: str):
        self.function_name = function_name
        super().__init__(f"{function_name}: {message}")


def function(
    return_type: Type[T],
    max_retries: int = 3,
    examples: list[dict] = None,
) -> Callable:
    """
    Decorator: turns a Python function into an LLM-executed function.

    The docstring IS the prompt sent to the LLM.
    Change the docstring → change what the LLM does.

    Usage:
        @function(return_type=MyResult)
        def my_func(session, x: str, y: int):
            '''Tell the LLM what to do here.
            This entire docstring is sent as instructions.'''

        result = my_func(session, x="hello", y=42)
    """
    def decorator(fn: Callable) -> Callable:
        fn_name = fn.__name__
        fn_doc = fn.__doc__ or ""

        @functools.wraps(fn)
        def wrapper(session: Session, **kwargs) -> T:
            prompt = _assemble_prompt(fn_name, fn_doc, kwargs, return_type, examples)

            last_error = None
            for attempt in range(max_retries):
                reply = session.send(prompt)
                try:
                    return _parse_output(reply, return_type)
                except Exception as e:
                    last_error = str(e)
                    prompt = (
                        f"Your previous response was invalid: {last_error}\n"
                        f"Please try again. Return ONLY valid JSON matching the schema.\n"
                        f"Schema: {json.dumps(return_type.model_json_schema(), indent=2)}"
                    )

            raise FunctionError(fn_name, f"Failed after {max_retries} attempts: {last_error}")

        wrapper._is_function = True
        wrapper._return_type = return_type
        wrapper._max_retries = max_retries
        wrapper._examples = examples or []
        wrapper._fn_name = fn_name
        wrapper._fn_doc = fn_doc
        return wrapper
    return decorator


# ------------------------------------------------------------------
# Built-in functions
# ------------------------------------------------------------------

def ask(session: Session, question: str) -> str:
    """Ask a question, get a plain text answer."""
    return session.send(question)


def extract(session: Session, text: str, schema: Type[T]) -> T:
    """Extract structured data from text into a Pydantic model.

    The docstring below is sent to the LLM as the prompt.
    """
    reply = session.send(
        f"Extract the following information from the text below.\n\n"
        f"Text:\n{text}\n\n"
        f"Return ONLY valid JSON matching this schema:\n"
        f"{json.dumps(schema.model_json_schema(), indent=2)}"
    )
    return _parse_output(reply, schema)


def summarize(session: Session, text: str, max_length: int = None) -> str:
    """Summarize text. If max_length is given, limit to that many words."""
    prompt = "Summarize the following text"
    if max_length:
        prompt += f" in {max_length} words or less"
    return session.send(f"{prompt}:\n\n{text}")


def classify(session: Session, text: str, categories: list[str]) -> str:
    """Classify text into one of the given categories."""
    cats = ", ".join(f'"{c}"' for c in categories)
    reply = session.send(
        f"Classify the following text into exactly one of these categories: {cats}\n\n"
        f"Text: {text}\n\n"
        f"Reply with ONLY the category name, nothing else."
    ).strip().strip('"')
    for cat in categories:
        if cat.lower() == reply.lower():
            return cat
    return reply


def decide(session: Session, question: str, options: list[str]) -> str:
    """Choose one option from a list."""
    opts = "\n".join(f"  {i+1}. {o}" for i, o in enumerate(options))
    reply = session.send(
        f"Question: {question}\n\nOptions:\n{opts}\n\n"
        f"Reply with ONLY the option text (not the number)."
    ).strip()
    for opt in options:
        if opt.lower() == reply.lower():
            return opt
    return reply


# ------------------------------------------------------------------
# Internal
# ------------------------------------------------------------------

def _assemble_prompt(
    fn_name: str,
    fn_doc: str,
    kwargs: dict,
    return_type: Type[T],
    examples: list[dict] = None,
) -> str:
    """
    Build the prompt from:
      1. Function name
      2. Docstring (= the instructions)
      3. Arguments
      4. Return schema
    """
    parts = [f"## {fn_name}\n"]

    # Docstring IS the instructions — sent as-is
    if fn_doc:
        parts.append(fn_doc.strip())
        parts.append("")

    if kwargs:
        parts.append("### Input")
        parts.append(json.dumps(kwargs, indent=2, ensure_ascii=False, default=str))
        parts.append("")

    if examples:
        parts.append("### Examples")
        for ex in examples:
            parts.append(f"Input: {json.dumps(ex.get('input', {}), ensure_ascii=False)}")
            parts.append(f"Output: {json.dumps(ex.get('output', {}), ensure_ascii=False)}")
        parts.append("")

    parts.append("### Output format")
    parts.append("Respond with ONLY a JSON object matching this schema:")
    parts.append(json.dumps(return_type.model_json_schema(), indent=2))

    return "\n".join(parts)


def _parse_output(reply: str, return_type: Type[T]) -> T:
    """Parse LLM reply into a Pydantic model."""
    text = reply.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return return_type.model_validate_json(text)
