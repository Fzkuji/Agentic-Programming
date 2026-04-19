# OpenClaw reference sources

TypeScript source files from [openclaw/openclaw](https://github.com/openclaw/openclaw)
(MIT license) kept here verbatim as **read-only protocol reference** for the
`openai-codex` onboarding flow in `openprogram/providers/onboarding.py` and
the `OpenAICodexRuntime` provider.

These files are NOT compiled or imported by OpenProgram. They document:
- Structure of `~/.codex/auth.json` (`auth_mode`, `tokens.*` keys)
- JWT payload shape for ChatGPT access tokens
- OAuth refresh flow at `auth.openai.com`

If you're looking for the runtime implementation, see
`openprogram/providers/openai_codex.py` and
`openprogram/providers/onboarding.py`.

## Upstream
Source: https://github.com/openclaw/openclaw (main branch)
License: MIT (see upstream repo's LICENSE file)
