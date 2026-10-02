"""The terminal chat."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from charter import Tool
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from rich.syntax import Syntax

from shipmate import routines
from shipmate.agent import build_agent, watch
from shipmate.apps import connected, load_tools
from shipmate.background import scheduler

console = Console()

HELP = """\
[bold]/apps[/]      what's connected        [bold]/routines[/]  what runs on a schedule
[bold]/new[/]       start a fresh chat      [bold]/quit[/]      leave (or Ctrl-D)
Anything else is a message. Connect apps with `shipmate connect` in another terminal."""


def short(args: dict, limit: int = 90) -> str:
    text = ", ".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in args.items())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def show(message: BaseMessage) -> None:
    if isinstance(message, AIMessage):
        for call in message.tool_calls:
            if call["name"] == "ToolSearch":
                console.print(
                    f"  [dim]⌕ looking for tools: {escape(str(call['args'].get('query', '')))}[/]"
                )
            else:
                console.print(f"  [dim]↳ {call['name']}({escape(short(call['args']))})[/]")
        if message.text.strip():
            console.print()
            console.print(Markdown(message.text))
            console.print()
    elif isinstance(message, ToolMessage) and message.status == "error":
        first = str(message.content).splitlines()[0] if message.content else ""
        console.print(f"  [red dim]✗ {escape(first[:160])}[/]")


async def ask(name: str, target: Tool, args: dict) -> str:
    """Show exactly what is about to be sent, and wait for an answer."""
    body = json.dumps(args, indent=2, ensure_ascii=False)
    if len(body) > 3000:
        body = body[:3000] + "\n…"
    console.print(
        Panel(
            Syntax(body, "json", theme="ansi_dark", word_wrap=True),
            title=f"[bold]{name}[/]  [dim]{target.method} {target.url_template}[/]",
            subtitle="this changes something",
            border_style="yellow",
        )
    )
    while True:
        reply = await asyncio.to_thread(
            console.input, "  Run it? [bold]y[/]es / [bold]n[/]o / [bold]a[/]lways for this tool › "
        )
        reply = reply.strip().lower()
        if reply in ("y", "yes"):
            return "yes"
        if reply in ("n", "no", ""):
            return "no"
        if reply in ("a", "always"):
            return "always"


def on_report(routine: dict, path: Path) -> None:
    console.print(f"\n[green]📬 routine #{routine['id']} finished[/] [dim]→ {path}[/]")


async def chat(model: Any, model_label: str) -> None:
    apps = connected()
    tools = watch(load_tools(apps))
    agent = build_agent(model, apps, tools, ask)
    names = ", ".join(app.key for app in apps) or "none (run `shipmate connect`)"
    console.print(
        f"[bold]Shipmate[/] [dim]· {model_label} · apps: {names} · {len(tools)} tools · /help[/]"
    )

    background = asyncio.create_task(scheduler(model, on_report))
    history: list[BaseMessage] = []
    try:
        while True:
            try:
                line = (await asyncio.to_thread(console.input, "[bold cyan]›[/] ")).strip()
            except EOFError:
                break
            if not line:
                continue
            if line in ("/quit", "/exit", "/q"):
                break
            if line == "/help":
                console.print(HELP)
                continue
            if line == "/new":
                history = []
                console.print("[dim]Fresh chat.[/]")
                continue
            if line == "/apps":
                console.print(names)
                continue
            if line == "/routines":
                for r in routines.load():
                    console.print(f"#{r['id']}  {r['when']:<16} {r['task']}", markup=False)
                continue

            before = history
            history = [*before, HumanMessage(line)]
            seen = len(history)
            try:
                async for state in agent.astream({"messages": history}, stream_mode="values"):
                    messages = state["messages"]
                    for message in messages[seen:]:
                        show(message)
                    seen = len(messages)
                    history = messages
            except Exception as exc:  # a failed turn should not end the chat
                # Back to before this message: a turn cut off between a tool call
                # and its result would be refused by the model on the next one.
                console.print(f"{type(exc).__name__}: {exc}", style="red", markup=False)
                history = before
    finally:
        background.cancel()
