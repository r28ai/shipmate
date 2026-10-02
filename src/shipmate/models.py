"""Which model Shipmate talks to.

`shipmate connect <provider>` saves the provider's key and makes its default
model the one in use. `--model` or $SHIPMATE_MODEL picks any other model,
written as LangChain spells it: `<provider>:<model>`.

Fireworks, OpenRouter and Together default to GLM-5.3 Flash, the model the
Charter harness measured at 99% task success with ToolSearch. Ollama uses a
model you have already pulled.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx


@dataclass(frozen=True)
class Provider:
    key: str
    label: str
    env: str | None  # the API key's variable; None for a model on this computer
    how: str
    default: str | None  # None: chosen when connecting


PROVIDERS: tuple[Provider, ...] = (
    Provider(
        "anthropic",
        "Anthropic (Claude)",
        "ANTHROPIC_API_KEY",
        "console.anthropic.com → API keys",
        "anthropic:claude-sonnet-5",
    ),
    Provider(
        "openai",
        "OpenAI",
        "OPENAI_API_KEY",
        "platform.openai.com/api-keys",
        "openai:gpt-5.5",
    ),
    Provider(
        "fireworks",
        "Fireworks (open models)",
        "FIREWORKS_API_KEY",
        "fireworks.ai → Settings → API Keys",
        "fireworks:accounts/fireworks/models/glm-5p3-flash",
    ),
    Provider(
        "openrouter",
        "OpenRouter (hundreds of models, one key)",
        "OPENROUTER_API_KEY",
        "openrouter.ai/settings/keys",
        "openrouter:z-ai/glm-5.3-flash",
    ),
    Provider(
        "together",
        "Together (open models)",
        "TOGETHER_API_KEY",
        "api.together.ai → Settings → API Keys",
        "together:zai-org/GLM-5.3-Flash",
    ),
    Provider(
        "ollama",
        "Ollama (on this computer, no key)",
        None,
        "ollama.com/download, then `ollama pull <model>`",
        None,
    ),
)


def find(key: str) -> Provider | None:
    return next((p for p in PROVIDERS if p.key == key), None)


def model_name(explicit: str | None = None) -> str | None:
    """The model to use: --model, then $SHIPMATE_MODEL, then the first provider with a key."""
    if explicit or os.environ.get("SHIPMATE_MODEL"):
        return explicit or os.environ["SHIPMATE_MODEL"]
    return next((p.default for p in PROVIDERS if p.env and os.environ.get(p.env)), None)


def load_model(name: str, **kwargs: Any) -> Any:
    from langchain.chat_models import init_chat_model

    return init_chat_model(name, **kwargs)


def ollama_url() -> str:
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    return host if "://" in host else f"http://{host}"


def ollama_models() -> list[str] | None:
    """The models pulled into the local Ollama, or None when it isn't running."""
    try:
        response = httpx.get(f"{ollama_url()}/api/tags", timeout=3)
        response.raise_for_status()
    except httpx.HTTPError:
        return None
    return [m["name"] for m in response.json().get("models", [])]


def model_host(model: Any) -> str:
    """Where a model's requests go, for `shipmate hosts`."""
    for attr in (
        "anthropic_api_url",
        "openai_api_base",
        "fireworks_api_base",
        "openrouter_api_base",
        "together_api_base",
        "base_url",
    ):
        value = getattr(model, attr, None)
        if isinstance(value, str) and value:
            return urlparse(value).netloc or value
    known = {
        "ChatOpenAI": "api.openai.com",
        "ChatFireworks": "api.fireworks.ai",
        "ChatOpenRouter": "openrouter.ai",
        "ChatTogether": "api.together.xyz",
        "ChatOllama": urlparse(ollama_url()).netloc,
    }
    return known.get(type(model).__name__, type(model).__name__)
