"""The apps Shipmate can reach, and which of them you have connected.

Every app is one or more Charter packs. Charter reads each pack's credential
from the environment, so "connected" means "its variables are set", and
connecting an app means saving those variables to ~/.shipmate/secrets.env.
"""

from __future__ import annotations

import importlib
import os
from collections.abc import Callable
from dataclasses import dataclass

from charter import Tool


@dataclass(frozen=True)
class App:
    key: str
    label: str
    packs: tuple[str, ...]
    env: tuple[str, ...]
    how: str
    verify: str | None = None  # a cheap read, "pack.tool", run once after connecting
    connected_if: Callable[[], bool] | None = None

    def is_connected(self) -> bool:
        if self.connected_if is not None:
            return self.connected_if()
        return all(os.environ.get(name) for name in self.env)


def _google_connected() -> bool:
    return any(
        os.environ.get(name)
        for name in ("GOOGLE_TOKEN_FILE", "GOOGLE_REFRESH_TOKEN", "GOOGLE_ACCESS_TOKEN")
    )


GOOGLE_PACKS = ("gmail", "gcalendar", "gdrive", "gsheets", "gdocs", "gforms")

APPS: tuple[App, ...] = (
    App(
        "google",
        "Gmail, Calendar, Drive, Sheets, Docs, Forms",
        GOOGLE_PACKS,
        ("GOOGLE_TOKEN_FILE",),
        "Signs in through your browser with your own Google OAuth client. "
        "`shipmate connect google` walks you through it.",
        verify="gmail.labels_list",
        connected_if=_google_connected,
    ),
    App(
        "slack",
        "Slack",
        ("slack",),
        ("SLACK_BOT_TOKEN",),
        "api.slack.com/apps → your app → OAuth & Permissions → Bot User OAuth Token (xoxb-…)",
        verify="slack.users_list",
    ),
    App(
        "github",
        "GitHub",
        ("github",),
        ("GITHUB_TOKEN",),
        "github.com/settings/tokens, or press Enter to reuse the GitHub CLI's login",
        verify="github.users_get_authenticated",
    ),
    App(
        "linear",
        "Linear",
        ("linear",),
        ("LINEAR_API_KEY",),
        "linear.app → Settings → Security & access → Personal API keys",
        verify="linear.viewer",
    ),
    App(
        "notion",
        "Notion",
        ("notion",),
        ("NOTION_API_KEY",),
        "notion.so/profile/integrations → New integration → Internal secret "
        "(then share the pages it may read with that integration)",
        verify="notion.users_retrieve_me",
    ),
    App(
        "stripe",
        "Stripe",
        ("stripe",),
        ("STRIPE_API_KEY",),
        "dashboard.stripe.com/apikeys. A restricted key, or a test-mode key to start.",
        verify="stripe.balance_retrieve",
    ),
    App(
        "shopify",
        "Shopify",
        ("shopify",),
        ("SHOPIFY_SHOP", "SHOPIFY_ACCESS_TOKEN"),
        "Your store's admin → Apps → Develop apps → Admin API access token",
        verify="shopify.shop_get",
    ),
    App(
        "granola",
        "Granola meeting notes",
        ("granola",),
        ("GRANOLA_API_KEY",),
        "Granola → Settings → API",
        verify="granola.notes_list",
    ),
    App(
        "tavily",
        "Web search (Tavily)",
        ("tavily",),
        ("TAVILY_API_KEY",),
        "app.tavily.com → API keys",
        verify="tavily.usage",
    ),
    App(
        "firecrawl",
        "Web scraping (Firecrawl)",
        ("firecrawl",),
        ("FIRECRAWL_API_KEY",),
        "firecrawl.dev/app/api-keys",
        verify="firecrawl.credit_usage",
    ),
)

# The model is an app too: it needs a key, and the key lives with the others.
MODELS: dict[str, tuple[str, str]] = {
    "anthropic": ("ANTHROPIC_API_KEY", "console.anthropic.com → API keys"),
    "openai": ("OPENAI_API_KEY", "platform.openai.com/api-keys"),
}


def find(key: str) -> App | None:
    return next((app for app in APPS if app.key == key), None)


def connected() -> list[App]:
    return [app for app in APPS if app.is_connected()]


def pack_tools(pack: str) -> list[Tool]:
    return list(importlib.import_module(f"charter.packs.{pack}").TOOLS)


def load_tools(apps: list[App]) -> list[Tool]:
    return [tool for app in apps for pack in app.packs for tool in pack_tools(pack)]
