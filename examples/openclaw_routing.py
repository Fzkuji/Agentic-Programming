"""
OpenClaw Routing — Route OpenClaw chat through Claude Code CLI.

When Anthropic blocks OpenClaw from using Claude subscription directly,
this routes requests through Claude Code CLI (which is still covered).

Architecture:
    OpenClaw → openclaw_routing.chat() → Claude Code CLI → response → OpenClaw

Usage:
    # As a standalone script
    python examples/openclaw_routing.py "What is prompt caching?"

    # As a module
    from examples.openclaw_routing import chat, analyze, summarize_conversation
    result = chat(message="Explain KV cache eviction")

    # With conversation history
    result = chat(
        message="What did I just ask about?",
        history=[
            {"role": "user", "content": "Explain KV cache"},
            {"role": "assistant", "content": "KV cache is..."},
        ],
    )
"""

import sys
from agentic import agentic_function
from agentic.providers import ClaudeCodeRuntime


# ── Runtime ─────────────────────────────────────────────────────

runtime = ClaudeCodeRuntime(model="sonnet", timeout=120)


# ── Core Functions ──────────────────────────────────────────────

@agentic_function
def chat(message: str, history: list = None, system_prompt: str = None):
    """Route a chat message through Claude Code.

    Args:
        message:       The user's message.
        history:       Optional conversation history.
                       List of {"role": "user"|"assistant", "content": "..."}.
        system_prompt: Optional system prompt to prepend.

    Returns:
        str — Claude's response.
    """
    content = []

    # System prompt
    if system_prompt:
        content.append({"type": "text", "text": f"System: {system_prompt}\n"})

    # Conversation history
    if history:
        history_text = "\n".join(
            f"{'User' if h['role'] == 'user' else 'Assistant'}: {h['content']}"
            for h in history
        )
        content.append({"type": "text", "text": f"Conversation so far:\n{history_text}\n"})

    # Current message
    content.append({"type": "text", "text": f"User: {message}"})

    return runtime.exec(content=content)


@agentic_function
def analyze(text: str, task: str = "Analyze this text"):
    """Analyze text with a specific task instruction.

    Args:
        text: The text to analyze.
        task: What to do with it (e.g., "Summarize", "Find bugs", "Translate").

    Returns:
        str — Analysis result.
    """
    return runtime.exec(content=[
        {"type": "text", "text": f"Task: {task}\n\nText:\n{text}"},
    ])


@agentic_function
def code_review(code: str, language: str = "Python"):
    """Review code and suggest improvements.

    Args:
        code:     Source code to review.
        language: Programming language.

    Returns:
        str — Review with suggestions.
    """
    return runtime.exec(content=[
        {"type": "text", "text": f"Review this {language} code. Point out bugs, suggest improvements, and rate quality 1-10.\n\n```{language.lower()}\n{code}\n```"},
    ])


@agentic_function
def summarize_conversation(history: list):
    """Summarize a conversation history.

    Args:
        history: List of {"role": "user"|"assistant", "content": "..."}.

    Returns:
        str — Summary of the conversation.
    """
    history_text = "\n".join(
        f"{'User' if h['role'] == 'user' else 'Assistant'}: {h['content']}"
        for h in history
    )
    return runtime.exec(content=[
        {"type": "text", "text": f"Summarize this conversation in 3 bullet points:\n\n{history_text}"},
    ])


@agentic_function
def multi_step_task(goal: str):
    """Break down and execute a multi-step task.

    Uses the full agentic function pipeline:
    plan → execute steps → summarize.

    Args:
        goal: What to accomplish.

    Returns:
        str — Final summary.
    """
    # Step 1: Plan
    plan = plan_steps(goal=goal)
    print(f"📋 Plan:\n{plan}\n")

    # Step 2: Execute each step
    steps = [line.strip() for line in plan.split("\n") if line.strip() and line.strip()[0].isdigit()]
    results = []
    for step in steps[:5]:  # Max 5 steps
        result = execute_step(step=step)
        results.append(result)
        print(f"  ✅ {step[:60]}")

    # Step 3: Summarize
    return summarize_results(goal=goal)


@agentic_function
def plan_steps(goal: str):
    """Break a goal into 3-5 concrete steps."""
    return runtime.exec(content=[
        {"type": "text", "text": f"Break this goal into 3-5 concrete steps. One line per step, numbered.\n\nGoal: {goal}"},
    ])


@agentic_function
def execute_step(step: str):
    """Execute one step and describe the result."""
    return runtime.exec(content=[
        {"type": "text", "text": f"Execute this step and describe what happens:\n\n{step}"},
    ])


@agentic_function
def summarize_results(goal: str):
    """Summarize what was accomplished."""
    return runtime.exec(content=[
        {"type": "text", "text": "Based on the execution context above, summarize what was accomplished in 2-3 sentences."},
    ])


# ── Entry Point ────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1:
        message = " ".join(sys.argv[1:])
        print(f"💬 {message}\n")
        result = chat(message=message)
        print(f"🤖 {result}")
    else:
        # Demo: multi-step task
        print("🚀 OpenClaw Routing Demo\n")
        result = multi_step_task(goal="Explain how Agentic Programming differs from traditional tool-calling agents")
        print(f"\n📝 Summary:\n{result}")
        print(f"\n🌳 Context Tree:")
        print(multi_step_task.context.tree())
