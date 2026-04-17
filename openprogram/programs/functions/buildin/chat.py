"""Built-in chat function for testing."""

__test__ = False

from openprogram.agentic_programming.function import agentic_function
from openprogram.agentic_programming.runtime import Runtime


@agentic_function(input={
    "message": {
        "description": "Message to send",
        "placeholder": "e.g. Hello, how are you?",
        "multiline": True,
    },
    "runtime": {"hidden": True},
}, no_tools=True)
def chat(message: str, runtime: Runtime = None) -> str:
    """Reply to the user's message in a helpful and concise way.

    This is a pure text chat — do NOT use any tools, commands, or file operations.
    Just read the message and respond naturally.

    Args:
        message: The user's message.

    Returns:
        A helpful response.
    """
    return runtime.exec(content=[{"type": "text", "text": message}])
