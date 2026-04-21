"""
OpenAICodexRuntime — thin Runtime subclass that burns ChatGPT subscription.

Reads ~/.codex/auth.json (written by `codex login --device-auth`), refreshes
the OAuth access_token against auth.openai.com/oauth/token when near expiry,
and feeds it to the standard openai-codex-responses provider as `api_key`.

All streaming / tool-loop / exec-tree recording flows through the default
Runtime → AgentSession → provider path. This class only handles OAuth.

Usage:
    from openprogram.providers.openai_codex import OpenAICodexRuntime
    rt = OpenAICodexRuntime(model="gpt-5.4-mini")
    reply = rt.exec([{"type": "text", "text": "hi"}])
"""
from __future__ import annotations

import base64
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from openprogram.agentic_programming.runtime import Runtime


OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
JWT_CLAIM_PATH = "https://api.openai.com/auth"


def _codex_home() -> Path:
    """Honor $CODEX_HOME, default ~/.codex (matches Codex CLI)."""
    configured = os.environ.get("CODEX_HOME", "").strip()
    if not configured:
        return Path.home() / ".codex"
    if configured in ("~", "~/"):
        return Path.home()
    if configured.startswith("~/"):
        return Path.home() / configured[2:]
    return Path(configured).resolve()


def _auth_path() -> Path:
    return _codex_home() / "auth.json"


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWT: not 3 segments")
    padded = parts[1] + "=" * (-len(parts[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))


def _extract_account_id(access_token: str) -> str:
    payload = _decode_jwt_payload(access_token)
    auth = payload.get(JWT_CLAIM_PATH) or {}
    account_id = auth.get("chatgpt_account_id")
    if not isinstance(account_id, str) or not account_id.strip():
        raise RuntimeError("JWT has no chatgpt_account_id — re-run `codex login --device-auth`")
    return account_id.strip()


def _jwt_expiry_epoch(access_token: str) -> int | None:
    try:
        exp = _decode_jwt_payload(access_token).get("exp")
        return int(exp) if isinstance(exp, (int, float)) else None
    except Exception:
        return None


def _refresh_oauth_token(refresh_token: str, timeout: float = 30.0) -> dict[str, Any]:
    r = httpx.post(
        OAUTH_TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": OAUTH_CLIENT_ID,
        },
        timeout=timeout,
    )
    if r.status_code != 200:
        raise RuntimeError(f"OAuth refresh failed {r.status_code}: {r.text[:200]}")
    data = r.json()
    for k in ("access_token", "refresh_token", "expires_in"):
        if k not in data:
            raise RuntimeError(f"OAuth refresh response missing {k!r}")
    return data


def _write_auth_json_atomic(data: dict[str, Any]) -> None:
    path = _auth_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


class _AuthState:
    """Cached auth.json (chatgpt mode) + refresh.

    Process-wide singleton (see ``_auth_state`` at module bottom). Sharing
    one instance across every ``OpenAICodexRuntime`` is load-bearing: the
    OAuth refresh_token rotates on every refresh, so if two runtimes each
    read ``auth.json`` independently and both try to refresh near expiry,
    the second refresh fails with 400 and the user gets booted to the
    login screen. Centralizing the cache + lock serializes the refresh.

    Refresh also races against a concurrently-running ``codex`` CLI that
    shares the same file. We mitigate by re-reading ``auth.json`` under
    the lock if our cached refresh_token is rejected; that's cheap and
    handles the "CLI rotated it while webui was idle" case without a
    forced re-login.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._auth: dict[str, Any] | None = None

    def resolve(self) -> tuple[str, str]:
        """Return (access_token, account_id), refreshing if near expiry."""
        with self._lock:
            return self._resolve_locked()

    def _load_from_disk(self) -> dict[str, Any]:
        path = _auth_path()
        if not path.exists():
            raise RuntimeError(
                f"{path} not found. OpenAICodexRuntime requires the "
                "ChatGPT subscription. Run: codex login --device-auth"
            )
        return json.loads(path.read_text(encoding="utf-8"))

    def _resolve_locked(self) -> tuple[str, str]:
        if self._auth is None:
            self._auth = self._load_from_disk()

        auth = self._auth
        if auth.get("auth_mode") != "chatgpt":
            raise RuntimeError(
                f"{_auth_path()} has auth_mode={auth.get('auth_mode')!r}, "
                "need 'chatgpt'. OpenAICodexRuntime is subscription-only. "
                "Run: codex login --device-auth"
            )

        tokens = auth.get("tokens") or {}
        access = tokens.get("access_token")
        refresh = tokens.get("refresh_token")
        if not access or not refresh:
            raise RuntimeError(
                f"{_auth_path()} is in chatgpt mode but missing tokens. "
                "Run: codex login --device-auth"
            )

        exp = _jwt_expiry_epoch(access)
        if exp is None or exp - 60 >= time.time():
            account_id = tokens.get("account_id") or _extract_account_id(access)
            return access, account_id

        # Near expiry — refresh. If the refresh_token we have was already
        # consumed (codex CLI rotated it out from under us), reload the
        # file and try once more before surrendering.
        try:
            new_tokens = _refresh_oauth_token(refresh)
        except RuntimeError as first_err:
            try:
                self._auth = self._load_from_disk()
            except Exception:
                raise first_err
            fresh_tokens = self._auth.get("tokens") or {}
            fresh_refresh = fresh_tokens.get("refresh_token")
            fresh_access = fresh_tokens.get("access_token")
            if fresh_refresh and fresh_refresh != refresh:
                # Someone else already rotated it. Trust the rotated
                # access_token if it's still valid; otherwise refresh with
                # the fresh refresh_token.
                fresh_exp = _jwt_expiry_epoch(fresh_access) if fresh_access else None
                if fresh_access and fresh_exp is not None and fresh_exp - 60 >= time.time():
                    account_id = fresh_tokens.get("account_id") or _extract_account_id(fresh_access)
                    return fresh_access, account_id
                new_tokens = _refresh_oauth_token(fresh_refresh)
            else:
                raise first_err

        auth = self._auth
        auth["tokens"]["access_token"] = new_tokens["access_token"]
        auth["tokens"]["refresh_token"] = new_tokens["refresh_token"]
        if "id_token" in new_tokens:
            auth["tokens"]["id_token"] = new_tokens["id_token"]
        _write_auth_json_atomic(auth)
        access = new_tokens["access_token"]
        account_id = auth["tokens"].get("account_id") or _extract_account_id(access)
        return access, account_id


# Process-wide singleton — see docstring on _AuthState for why this must
# not be per-runtime.
_auth_state = _AuthState()


_KNOWN_CODEX_MODELS = [
    "gpt-5.4", "gpt-5.4-mini", "gpt-5.4-pro",
    "gpt-5.3-codex", "gpt-5.3-codex-spark",
    "gpt-5.2-codex", "gpt-5.1-codex", "gpt-5.1-codex-mini",
]


def _augment_registry_with_codex_models() -> None:
    """Inject Codex-route model ids into the provider registry if the
    generated catalog is missing them. The ChatGPT backend has no public
    model-listing endpoint, so OpenClaw / pi-ai maintain their lists by
    hand; we mirror that list here and let the registry carry the rest
    (name, cost, context window) for whichever ids already exist. New
    entries get a sensible Codex default."""
    from openprogram.providers.models_generated import MODELS
    from openprogram.providers.types import Model, ModelCost

    template = next(
        (m for m in MODELS.values()
         if m.provider == "openai-codex" and m.api == "openai-codex-responses"),
        None,
    )
    if template is None:
        return  # registry has no Codex entries at all; nothing to mirror.

    for mid in _KNOWN_CODEX_MODELS:
        key = f"openai-codex/{mid}"
        if key in MODELS:
            continue
        # Prettify: "gpt-5.4-mini" -> "GPT-5.4 mini", "gpt-5.3-codex-spark" -> "GPT-5.3 Codex Spark"
        parts = mid.replace("gpt-", "").split("-")
        head = "GPT-" + parts[0]
        tail = " ".join(p.capitalize() if p != "codex" else "Codex" for p in parts[1:])
        display = (head + " " + tail).strip()

        MODELS[key] = template.model_copy(update={
            "id": mid,
            "name": display,
        })


_augment_registry_with_codex_models()


class OpenAICodexRuntime(Runtime):
    """
    Args:
        model:   Default model id (e.g. "gpt-5.4-mini", "gpt-5.4").
        system:  Optional system prompt (forwarded as `instructions`).

    Extra kwargs are accepted-and-ignored for compatibility with callers
    that still pass subprocess-era fields (sandbox, full_auto, session_id).
    """

    def __init__(
        self,
        model: str = "gpt-5.4-mini",
        system: str | None = None,
        **_ignored: Any,
    ) -> None:
        self._auth = _auth_state  # process-wide singleton; see class docstring
        access, account_id = self._auth.resolve()

        super().__init__(model=f"openai-codex:{model}", api_key=access)

        # ChatGPT backend wants extra headers alongside Bearer. Attach them
        # to a per-runtime Model copy so we don't mutate the registry.
        self.api_model = self.api_model.model_copy(update={
            "headers": {
                "chatgpt-account-id": account_id,
                "originator": "openprogram",
                "OpenAI-Beta": "responses=experimental",
            },
        })

        self.system = system

    def list_models(self) -> list[str]:
        return list(_KNOWN_CODEX_MODELS)

    def exec(self, *args: Any, **kwargs: Any) -> Any:
        # Refresh the access_token (and account header) if close to expiry.
        access, account_id = self._auth.resolve()
        if access != self.api_key:
            self.api_key = access
            new_headers = dict(self.api_model.headers or {})
            new_headers["chatgpt-account-id"] = account_id
            self.api_model = self.api_model.model_copy(update={"headers": new_headers})
        return super().exec(*args, **kwargs)
