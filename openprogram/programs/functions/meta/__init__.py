"""
openprogram.programs.functions.meta — LLM-powered code generation primitives.

Meta functions use LLMs to generate, edit, and scaffold agentic code:

    create()       — Generate a single @agentic_function from a description
    create_app()   — Generate a complete runnable app (runtime + functions + main)
    edit()         — Analyze and rewrite an existing function
    improve()      — Optimize an existing function based on a goal
    create_skill() — Write a SKILL.md for agent discovery

All code-generation meta functions delegate to generate_code() in _helpers.py,
which contains the complete Agentic Programming design specification.
"""

from openprogram.programs.functions.meta.create import create
from openprogram.programs.functions.meta.create_app import create_app
from openprogram.programs.functions.meta.edit import edit
from openprogram.programs.functions.meta.improve import improve
from openprogram.programs.functions.meta.create_skill import create_skill

# Backward-compatible alias used throughout the docs and examples.
fix = edit

__all__ = ["create", "create_app", "edit", "fix", "improve", "create_skill"]
