"""The agent: a model, your apps as Charter tools, and the gate in between.

LangChain runs the loop. Charter turns every API endpoint into a tool the
model can call, and its ToolSearch keeps the hundreds of them out of the
prompt until one is needed. Shipmate adds three things on top: the gate that
asks before anything changes, a log of every request, and a few tools of its
own (memory, routines, reading a web page).
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import os
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import httpx
from charter import Tool, ToolCall, ToolSession, format_call_line, html_to_text
from charter.adapters.langchain import CharterMiddleware
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, ModelRequest, dynamic_prompt
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool

from shipmate import routines
from shipmate.apps import App
from shipmate.home import home
from shipmate.policy import Policy, is_read

# (tool name, the tool, its arguments) -> "yes" | "no" | "always"
Ask = Callable[[str, Tool, dict], Awaitable[str]]

DEFAULT_MODELS = (
    ("ANTHROPIC_API_KEY", "anthropic:claude-sonnet-5"),
    ("OPENAI_API_KEY", "openai:gpt-5.5"),
)


def model_name(explicit: str | None = None) -> str | None:
    if explicit or os.environ.get("SHIPMATE_MODEL"):
        return explicit or os.environ["SHIPMATE_MODEL"]
    return next((name for key, name in DEFAULT_MODELS if os.environ.get(key)), None)


def load_model(name: str) -> Any:
    from langchain.chat_models import init_chat_model

    return init_chat_model(name)


# ------------------------------------------------------------------ the log


def log(entry: dict) -> None:
    try:
        with open(home() / "log.jsonl", "a") as f:
            f.write(
                json.dumps({"at": datetime.now().isoformat(timespec="seconds"), **entry}) + "\n"
            )
    except OSError:
        pass


def host_of(tool: Tool) -> str:
    base = tool.base_url
    try:
        base = base() if callable(base) else base  # a Shopify store's URL is per-store
    except Exception:
        return tool.pack or "unknown"
    return urlparse(str(base)).netloc


def model_host(model: Any) -> str:
    for attr in ("anthropic_api_url", "openai_api_base", "base_url", "fireworks_api_base"):
        value = getattr(model, attr, None)
        if isinstance(value, str) and value:
            return urlparse(value).netloc or value
    known = {"ChatOpenAI": "api.openai.com", "ChatFireworks": "api.fireworks.ai"}
    return known.get(type(model).__name__, type(model).__name__)


def audit(call: ToolCall, host: str) -> None:
    """Charter hands every finished call here: what was sent where, and how it went."""
    log({"call": format_call_line(call), "host": host, **dataclasses.asdict(call)})


def watch(tools: list[Tool]) -> list[Tool]:
    for t in tools:
        t.on_call = lambda call, t=t: audit(call, host_of(t))
    return tools


class Ledger(AgentMiddleware):
    """Logs each model call's destination, so `shipmate hosts` can list it."""

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        log({"model": model_host(request.model)})
        return await handler(request)


# ----------------------------------------------------------------- the gate


class Gate(AgentMiddleware):
    """Reads run. Everything else waits for a yes."""

    def __init__(self, session: ToolSession, ask: Ask, allow: set[str] | None = None) -> None:
        super().__init__()
        self.session = session
        self.ask = ask
        self.allow = allow or set()
        self.policy = Policy()
        # Models call tools in parallel; two questions at once would interleave.
        self._one_question = asyncio.Lock()

    async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
        call = request.tool_call
        name = call["name"]
        target = self.session.visible().get(name)
        if (
            target is None  # one of Shipmate's own tools, or ToolSearch
            or is_read(target)
            or name in self.allow
            or self.policy.allows(name)
        ):
            return await handler(request)

        async with self._one_question:
            answer = await self.ask(name, target, call.get("args", {}))
        log({"decision": answer, "tool": name})
        if answer == "always":
            self.policy.allow_always(name)
        if answer in ("yes", "always"):
            return await handler(request)
        return ToolMessage(
            content=(
                f"Not run: the user said no to {name}. Don't retry it or work around it. "
                "Tell them what you were going to do, and ask if they want something else."
            ),
            tool_call_id=call["id"],
            name=name,
            status="error",
        )


async def refuse(name: str, target: Tool, args: dict) -> str:
    """The answer when nobody is watching: a routine never acts on its own."""
    return "no"


# -------------------------------------------------------- Shipmate's own tools


@tool
def remember(fact: str) -> str:
    """Save one lasting fact about the user: a person, a preference, an account, a habit.
    It is shown to you at the start of every conversation from now on."""
    with open(home() / "memory.md", "a") as f:
        f.write(f"- {fact.strip()}\n")
    return "Saved."


@tool
def forget(text: str) -> str:
    """Delete every remembered fact that contains this text."""
    path = home() / "memory.md"
    lines = path.read_text().splitlines(keepends=True) if path.exists() else []
    kept = [line for line in lines if text.lower() not in line.lower()]
    path.write_text("".join(kept))
    return f"Forgot {len(lines) - len(kept)} fact(s)."


@tool
async def read_web_page(url: str) -> str:
    """Fetch a web page and return its text. For reading a link, not for searching."""
    if not url.startswith(("http://", "https://")):
        return "Only http and https links can be read."
    log({"web": urlparse(url).netloc})
    async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
        response = await client.get(url, headers={"user-agent": "shipmate/0.1"})
    text = response.text
    if "html" in response.headers.get("content-type", ""):
        text = html_to_text(text)
    return f"HTTP {response.status_code}\n\n{text[:20_000]}"


@tool
def add_routine(when: str, task: str) -> str:
    """Run a task on a schedule, e.g. when='weekdays 08:00', task='Brief me on unread email and
    today's meetings'. `when` is 'daily HH:MM', 'weekdays HH:MM', 'weekends HH:MM', days like
    'mon,thu HH:MM', or 'every 30m' / 'every 2h'. Write the task as instructions to yourself."""
    try:
        r = routines.add(when, task)
    except ValueError as exc:
        return str(exc)
    return f"Routine #{r['id']} saved: {when} — {task}"


@tool
def list_routines() -> str:
    """List the scheduled routines."""
    rs = routines.load()
    return "\n".join(f"#{r['id']} {r['when']}: {r['task']}" for r in rs) or "No routines yet."


@tool
def remove_routine(routine_id: str) -> str:
    """Delete a routine by its number."""
    return "Removed." if routines.remove(routine_id.lstrip("#")) else "No routine with that number."


OWN_TOOLS = [remember, forget, read_web_page, add_routine, list_routines, remove_routine]


# ---------------------------------------------------------------- the prompt


def system_prompt(apps: list[App], routine: dict | None = None) -> str:
    now = datetime.now().astimezone()
    memory_path = home() / "memory.md"
    memory = memory_path.read_text().strip() if memory_path.exists() else ""
    connected = "; ".join(app.label for app in apps) or (
        "none yet. If the user asks for something an app would do, tell them to run "
        "`shipmate connect` in a terminal."
    )
    lines = [
        "You are Shipmate, a personal agent running on the user's own computer, "
        "with their own keys.",
        f"It is {now:%A %d %B %Y, %H:%M} ({now.tzname()}).",
        f"Connected apps: {connected}.",
        "",
        "How you work:",
        "- App tools load on demand. Call ToolSearch with a few words "
        "('unread gmail threads', 'create calendar event') to load them, then call them.",
        "- Reading is free. Anything that sends, posts, creates, changes or deletes waits "
        "for the user's yes. If they say no, don't retry.",
        "- Only say you did something if a tool call did it. Shipmate shows the user a count "
        "of what actually ran after every reply, so a claim with no call behind it is caught.",
        "- Do the work instead of describing it. Ask only when the choice is the user's.",
        "- Never guess an email address, ID or date. Look it up (for the user's own address, "
        "their Gmail profile).",
        "- Lead with the answer. Keep it short. Name people, dates and amounts exactly.",
        "- When the user tells you something lasting about themselves, call remember.",
        "- When they want something done on a schedule, call add_routine.",
    ]
    if routine is not None:
        lines += [
            "",
            f"This is a scheduled run of routine #{routine['id']} ({routine['when']}). "
            "Nobody is watching, so don't ask questions. Actions that change things will be "
            "refused unless this routine was allowed to take them; say what you would have "
            "done instead. End with a short report for the user to read later.",
        ]
    if memory:
        lines += ["", "What you remember about the user:", memory]
    return "\n".join(lines)


def build_agent(
    model: Any,
    apps: list[App],
    tools: list[Tool],
    ask: Ask,
    *,
    routine: dict | None = None,
) -> Any:
    session = ToolSession(tools)

    @dynamic_prompt
    def prompt(request: ModelRequest) -> str:
        return system_prompt(apps, routine)

    allow = set(routine.get("allow", [])) if routine else set()
    return create_agent(
        model,
        tools=OWN_TOOLS,
        middleware=[prompt, Ledger(), Gate(session, ask, allow), CharterMiddleware(session)],
    )
