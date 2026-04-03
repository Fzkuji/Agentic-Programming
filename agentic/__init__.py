"""
Agentic Programming — Python functions that call LLMs with automatic context.

Three things:

    @agentic_function    Decorator. Records every call into a Context tree.
    runtime.exec()       Calls the LLM. Auto-reads context, auto-records I/O.
    Context              The tree of execution records. Query it with summarize().

Quick start:

    from agentic import agentic_function, runtime

    @agentic_function
    def observe(task):
        '''Look at the screen and describe what you see.'''
        img = take_screenshot()
        return runtime.exec(
            prompt=observe.__doc__,
            input={"task": task},
            images=[img],
            call=my_llm_provider,
        )

    @agentic_function(compress=True)
    def navigate(target):
        '''Navigate to a target element.'''
        obs = observe(f"find {target}")
        action = plan(obs)
        act(action)
        return verify(target)
"""

from agentic.context import Context, get_context, get_root_context, init_root
from agentic.function import agentic_function
from agentic import runtime

__all__ = [
    "agentic_function",
    "runtime",
    "Context",
    "get_context",
    "get_root_context",
    "init_root",
]
