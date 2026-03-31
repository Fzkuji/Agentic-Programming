"""
Session — the pluggable execution backend for Agentic Programming.

A Session is like a CPU or interpreter — it executes what it's given and returns
the result. It doesn't decide what to run or in what order.

In Agentic Programming, Sessions have two lifecycles:
    - Ephemeral: created for one Function execution, then destroyed (Runtime uses these)
    - Persistent: survives across multiple calls (Programmer uses these)

Any class that implements send() is a valid Session.

The send() interface accepts flexible input:
    - str: plain text message
    - dict: structured message (e.g. {"text": "...", "images": [...]})
    - list: multi-part message (e.g. [{"type": "text", ...}, {"type": "image", ...}])

This allows Sessions to support multimodal input (text, images, audio, etc.)
depending on the underlying model's capabilities.

Built-in implementations:
    - AnthropicSession   Direct Anthropic API (text + images)
    - OpenAISession      Direct OpenAI API (text + images)
    - ClaudeCodeSession  Claude Code CLI (--print mode)
    - CodexSession       OpenAI Codex CLI
    - OpenClawSession    OpenClaw gateway API
    - CLISession         Any CLI agent via subprocess
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Union


# Message can be plain text, a structured dict, or a list of content parts
Message = Union[str, dict, list]


class Session(ABC):
    """
    The runtime interface for Function execution.

    A Session is anything that can:
        1. Receive a message (text, multimodal, or structured)
        2. Return a reply (string)

    Input format depends on the Session implementation:
        - str: all Sessions must support plain text
        - dict/list: Sessions may support multimodal content
          (images, audio, etc.) based on their backend

    The Session is responsible for:
        - Interpreting the message format
        - Maintaining its own conversation history (if applicable)
        - Managing its own connection and authentication
        - Returning complete (not streamed) replies

    The Session is NOT responsible for:
        - Parsing return values (Function handles that)
        - Retry logic (Function handles that)
        - Deciding what to do next (Programmer does that)
    """

    @abstractmethod
    def send(self, message: Message) -> str:
        """
        Send a message and return the reply.

        Args:
            message: The input message. Can be:
                - str: plain text
                - dict: structured message, e.g.:
                    {"text": "describe this", "images": ["path/to/img.png"]}
                - list: content parts (Anthropic/OpenAI format), e.g.:
                    [{"type": "text", "text": "..."}, {"type": "image_url", ...}]

        Returns:
            The reply as a plain string
        """
        pass


# ------------------------------------------------------------------
# Direct API Sessions
# ------------------------------------------------------------------

class AnthropicSession(Session):
    """
    Direct Anthropic API session. Supports text and image input.

    Args:
        model:          Model name (default: claude-sonnet-4-6)
        max_tokens:     Max reply tokens
        system_prompt:  System prompt for the session
        api_key:        Anthropic API key (default: ANTHROPIC_API_KEY env var)
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 4096,
        system_prompt: str = "You are a helpful assistant that follows instructions precisely and always returns valid JSON when asked.",
        api_key: str = None,
    ):
        try:
            import anthropic
        except ImportError:
            raise ImportError("anthropic package required: pip install anthropic")

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens
        self._system_prompt = system_prompt
        self._history = []

    def send(self, message: Message) -> str:
        content = self._to_anthropic_content(message)
        self._history.append({"role": "user", "content": content})

        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=self._system_prompt,
            messages=self._history,
        )

        reply = response.content[0].text
        self._history.append({"role": "assistant", "content": reply})
        return reply

    def reset(self):
        """Clear conversation history to start a fresh session."""
        self._history = []

    @staticmethod
    def _to_anthropic_content(message: Message):
        """Convert flexible message format to Anthropic content format."""
        if isinstance(message, str):
            return message
        if isinstance(message, list):
            return message  # assume already in Anthropic format
        if isinstance(message, dict):
            parts = []
            if "text" in message:
                parts.append({"type": "text", "text": message["text"]})
            if "images" in message:
                import base64
                for img_path in message["images"]:
                    with open(img_path, "rb") as f:
                        data = base64.standard_b64encode(f.read()).decode()
                    # Detect media type from extension
                    ext = img_path.rsplit(".", 1)[-1].lower()
                    media_type = {
                        "png": "image/png",
                        "jpg": "image/jpeg",
                        "jpeg": "image/jpeg",
                        "gif": "image/gif",
                        "webp": "image/webp",
                    }.get(ext, "image/png")
                    parts.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": data,
                        }
                    })
            return parts if parts else message
        return message


class OpenAISession(Session):
    """
    Direct OpenAI API session. Supports text and image input.

    Args:
        model:          Model name (default: gpt-4o)
        max_tokens:     Max reply tokens
        system_prompt:  System prompt for the session
        api_key:        OpenAI API key (default: OPENAI_API_KEY env var)
        base_url:       Custom API base URL (for compatible APIs)
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        max_tokens: int = 4096,
        system_prompt: str = "You are a helpful assistant that follows instructions precisely and always returns valid JSON when asked.",
        api_key: str = None,
        base_url: str = None,
    ):
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("openai package required: pip install openai")

        kwargs = {}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url

        self._client = OpenAI(**kwargs)
        self._model = model
        self._max_tokens = max_tokens
        self._system_prompt = system_prompt
        self._history = []

    def send(self, message: Message) -> str:
        content = self._to_openai_content(message)
        self._history.append({"role": "user", "content": content})

        messages = [{"role": "system", "content": self._system_prompt}] + self._history

        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=messages,
        )

        reply = response.choices[0].message.content
        self._history.append({"role": "assistant", "content": reply})
        return reply

    def reset(self):
        """Clear conversation history."""
        self._history = []

    @staticmethod
    def _to_openai_content(message: Message):
        """Convert flexible message format to OpenAI content format."""
        if isinstance(message, str):
            return message
        if isinstance(message, list):
            return message  # assume already in OpenAI format
        if isinstance(message, dict):
            parts = []
            if "text" in message:
                parts.append({"type": "text", "text": message["text"]})
            if "images" in message:
                import base64
                for img_path in message["images"]:
                    with open(img_path, "rb") as f:
                        data = base64.standard_b64encode(f.read()).decode()
                    ext = img_path.rsplit(".", 1)[-1].lower()
                    media_type = {
                        "png": "image/png",
                        "jpg": "image/jpeg",
                        "jpeg": "image/jpeg",
                        "gif": "image/gif",
                        "webp": "image/webp",
                    }.get(ext, "image/png")
                    parts.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{data}"
                        }
                    })
            return parts if parts else message
        return message


# ------------------------------------------------------------------
# CLI Agent Sessions
# ------------------------------------------------------------------

class CLISession(Session):
    """
    Generic CLI agent session via subprocess.

    Wraps any command-line agent. Each send() runs the command as a subprocess.

    Args:
        command:    Command template. Use {message} for the input placeholder.
                    If no {message}, input is passed via stdin.
        timeout:    Seconds to wait for completion
        env:        Additional environment variables

    Examples:
        CLISession(command='my-agent --prompt "{message}"')
        CLISession(command='my-agent --stdin')
    """

    def __init__(
        self,
        command: str,
        timeout: int = 300,
        env: dict = None,
    ):
        self._command = command
        self._timeout = timeout
        self._env = env

    def send(self, message: Message) -> str:
        import subprocess
        import os

        # CLI sessions use text only — extract text from multimodal input
        text = self._extract_text(message)

        env = dict(os.environ)
        if self._env:
            env.update(self._env)

        if "{message}" in self._command:
            escaped = text.replace("'", "'\\''")
            cmd = self._command.replace("{message}", escaped)
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                timeout=self._timeout, env=env,
            )
        else:
            result = subprocess.run(
                self._command, shell=True, input=text, capture_output=True,
                text=True, timeout=self._timeout, env=env,
            )

        if result.returncode != 0:
            raise RuntimeError(
                f"CLI command failed (exit {result.returncode}): {result.stderr[:500]}"
            )
        return result.stdout.strip()

    @staticmethod
    def _extract_text(message: Message) -> str:
        if isinstance(message, str):
            return message
        if isinstance(message, dict):
            return message.get("text", str(message))
        if isinstance(message, list):
            texts = [p.get("text", "") for p in message if isinstance(p, dict) and p.get("type") == "text"]
            return "\n".join(texts) if texts else str(message)
        return str(message)


class ClaudeCodeSession(Session):
    """
    Claude Code CLI session (--print mode, non-interactive).

    Each send() is an independent invocation with full tool access.

    Args:
        model:              Model override
        max_turns:          Max agent turns per invocation
        system_prompt:      System prompt override
        allowed_tools:      List of allowed tools
        permission_mode:    Permission mode (default: bypassPermissions)
    """

    def __init__(
        self,
        model: str = None,
        max_turns: int = None,
        system_prompt: str = None,
        allowed_tools: list = None,
        permission_mode: str = "bypassPermissions",
    ):
        self._model = model
        self._max_turns = max_turns
        self._system_prompt = system_prompt
        self._allowed_tools = allowed_tools
        self._permission_mode = permission_mode

    def send(self, message: Message) -> str:
        import subprocess
        import os

        text = message if isinstance(message, str) else self._extract_text(message)

        cmd = ["claude", "--print", f"--permission-mode={self._permission_mode}"]

        if self._model:
            cmd.extend(["--model", self._model])
        if self._max_turns:
            cmd.extend(["--max-turns", str(self._max_turns)])
        if self._system_prompt:
            cmd.extend(["--system-prompt", self._system_prompt])
        if self._allowed_tools:
            for tool in self._allowed_tools:
                cmd.extend(["--allowedTools", tool])

        cmd.extend(["--prompt", text])

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600, env=os.environ,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Claude Code failed (exit {result.returncode}): {result.stderr[:500]}"
            )
        return result.stdout.strip()

    @staticmethod
    def _extract_text(message: Message) -> str:
        if isinstance(message, dict):
            return message.get("text", str(message))
        if isinstance(message, list):
            texts = [p.get("text", "") for p in message if isinstance(p, dict) and p.get("type") == "text"]
            return "\n".join(texts) if texts else str(message)
        return str(message)


class CodexSession(Session):
    """
    OpenAI Codex CLI session (full-auto mode).

    Each send() is an independent invocation.

    Args:
        model:      Model override
        provider:   Provider (openai, anthropic, etc.)
        quiet:      Suppress non-essential output (default: True)
    """

    def __init__(
        self,
        model: str = None,
        provider: str = None,
        quiet: bool = True,
    ):
        self._model = model
        self._provider = provider
        self._quiet = quiet

    def send(self, message: Message) -> str:
        import subprocess
        import os

        text = message if isinstance(message, str) else (
            message.get("text", str(message)) if isinstance(message, dict) else str(message)
        )

        cmd = ["codex", "--approval-mode", "full-auto"]

        if self._quiet:
            cmd.append("--quiet")
        if self._model:
            cmd.extend(["--model", self._model])
        if self._provider:
            cmd.extend(["--provider", self._provider])

        cmd.append(text)

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600, env=os.environ,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Codex failed (exit {result.returncode}): {result.stderr[:500]}"
            )
        return result.stdout.strip()


# ------------------------------------------------------------------
# Gateway Sessions
# ------------------------------------------------------------------

class OpenClawSession(Session):
    """
    Routes messages through an OpenClaw gateway.

    Benefits from OpenClaw's persistent memory, tools, and context.

    Args:
        gateway_url:    OpenClaw gateway URL
        session_id:     Session identifier for message routing
    """

    def __init__(
        self,
        gateway_url: str = "http://localhost:18789",
        session_id: str = "default",
    ):
        self._gateway_url = gateway_url
        self._session_id = session_id

    def send(self, message: Message) -> str:
        try:
            import httpx
        except ImportError:
            raise ImportError("httpx package required: pip install httpx")

        # Send text or structured content
        if isinstance(message, str):
            payload = {"message": message, "session_id": self._session_id}
        else:
            payload = {"message": message, "session_id": self._session_id}

        response = httpx.post(
            f"{self._gateway_url}/message",
            json=payload,
            timeout=120.0,
        )
        response.raise_for_status()
        return response.json()["reply"]
