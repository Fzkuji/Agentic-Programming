"""
Agentic Programming — Example entry point.

This example shows a simple GUI automation flow:
observe → click → verify, orchestrated by a top-level login_flow.

Usage:
    python examples/main.py
"""

import openai
from agentic import agentic_function, Runtime, get_root_context


# ── LLM Provider ────────────────────────────────────────────────
# Implement _call() or pass a `call` function to Runtime.

client = openai.OpenAI()  # reads OPENAI_API_KEY from env


def openai_call(content, model="gpt-4o-mini", response_format=None):
    """Convert content list → OpenAI messages → API call → reply text."""
    messages_content = []
    for block in content:
        if block["type"] == "text":
            messages_content.append({"type": "text", "text": block["text"]})
        elif block["type"] == "image":
            # For real usage: encode image as base64 and use image_url
            messages_content.append({"type": "text", "text": f"[Image: {block['path']}]"})

    kwargs = {
        "model": model,
        "max_tokens": 512,
        "messages": [{"role": "user", "content": messages_content}],
    }
    if response_format:
        kwargs["response_format"] = {"type": "json_object"}

    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content


# ── Runtime ─────────────────────────────────────────────────────
# Create once, use everywhere.

rt = Runtime(call=openai_call, model="gpt-4o-mini")


# ── Agentic Functions ──────────────────────────────────────────

@agentic_function
def observe(task):
    """Look at the screen and describe what you see."""
    return rt.exec(content=[
        {"type": "text", "text": f"Describe what you see. Task: {task}"},
    ])


@agentic_function
def click(element):
    """Click an element on the screen."""
    return rt.exec(content=[
        {"type": "text", "text": f"Click the element: {element}. Describe the result."},
    ])


@agentic_function
def verify(expected):
    """Verify the current state matches expectations."""
    return rt.exec(content=[
        {"type": "text", "text": f"Verify: are we on the {expected} page? Answer yes or no with reason."},
    ])


@agentic_function
def login_flow(username, password):
    """Complete login flow: observe, click login, verify dashboard."""
    observe(task="find the login form")
    click(element="login button")
    return verify(expected="dashboard")


# ── Entry Point ────────────────────────────────────────────────

if __name__ == "__main__":
    result = login_flow(username="admin", password="secret")

    print("\n── Result ──")
    print(result)

    print("\n── Context Tree ──")
    print(get_root_context().tree())
