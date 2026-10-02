"""shipmate — your own personal agent, on your laptop.

shipmate                     chat
shipmate connect [app]       connect Gmail, Slack, GitHub… or a model key
shipmate routines            list, add, remove or run scheduled tasks
shipmate run                 keep routines running in the background
shipmate inbox               what the routines reported
shipmate log                 every API request it made
shipmate egress [app]        exactly which fields the model can see
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import shutil
import subprocess
import sys

from rich.console import Console

from shipmate.home import home, load_secrets, save_secret

console = Console()


# ------------------------------------------------------------------ helpers


def need_model(explicit: str | None) -> tuple[object, str]:
    from shipmate.agent import load_model, model_name

    name = model_name(explicit)
    if name is None:
        console.print(
            "No model key yet. Run [bold]shipmate connect anthropic[/] (or openai), "
            "or pass [bold]--model[/] (e.g. ollama:qwen3 with `pip install 'shipmate\\[ollama]'`)."
        )
        raise SystemExit(1)
    try:
        return load_model(name), name
    except (ValueError, ImportError) as exc:
        console.print(f"Can't load model {name!r}: {str(exc).splitlines()[0]}", markup=False)
        raise SystemExit(1) from None


def status_table() -> None:
    from shipmate.apps import APPS, MODELS

    for app in APPS:
        mark = "[green]●[/]" if app.is_connected() else "[dim]○[/]"
        console.print(f" {mark} [bold]{app.key:<10}[/] {app.label}")
    for key, (env, _) in MODELS.items():
        mark = "[green]●[/]" if os.environ.get(env) else "[dim]○[/]"
        console.print(f" {mark} [bold]{key:<10}[/] model key")
    console.print("\n[dim]shipmate connect <name> to add one.[/]")


async def verify(app_key: str) -> None:
    """Make one cheap read with the new key, so a typo shows up now, not mid-task."""
    from charter import CharterError, ToolValidationError

    from shipmate.apps import find, pack_tools

    app = find(app_key)
    if app is None or app.verify is None:
        return
    pack, name = app.verify.split(".")
    tool = next(t for t in pack_tools(pack) if t.name == name)
    try:
        await tool.ainvoke({})
    except ToolValidationError:
        console.print("[dim]Saved (no quick check available for this app).[/]")
    except CharterError as exc:
        console.print(f"[red]Saved, but the check failed:[/] {exc}", markup=False)
        raise SystemExit(1) from None
    else:
        console.print(f"[green]✓ {app.label} connected.[/]")


def github_cli_token() -> str | None:
    if not shutil.which("gh"):
        return None
    out = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=False)
    return out.stdout.strip() or None


# ----------------------------------------------------------------- commands


def cmd_chat(args: argparse.Namespace) -> None:
    from shipmate.chat import chat

    model, name = need_model(args.model)
    asyncio.run(chat(model, name))


def cmd_connect(args: argparse.Namespace) -> None:
    from shipmate.apps import MODELS, find

    if not args.app:
        status_table()
        return
    key = args.app.lower()

    if key in MODELS:
        env, how = MODELS[key]
        console.print(f"[dim]{how}[/]")
        save_secret(env, getpass.getpass(f"{env}: ").strip())
        console.print(f"[green]✓ saved {env}[/]")
        return

    app = find(key)
    if app is None:
        console.print(f"No app called {key!r}.\n")
        status_table()
        raise SystemExit(1)

    if app.key == "google":
        from shipmate import google

        path = asyncio.run(google.connect(console))
        console.print(f"[dim]Saved the grant to {path}[/]")
    else:
        console.print(f"[dim]{app.how}[/]")
        for env in app.env:
            if env == "GITHUB_TOKEN":
                value = getpass.getpass(f"{env} (Enter to use `gh auth token`): ").strip()
                value = value or github_cli_token() or ""
            elif env == "SHOPIFY_SHOP":
                value = input(f"{env} (your-store.myshopify.com): ").strip()
            else:
                value = getpass.getpass(f"{env}: ").strip()
            if not value:
                raise SystemExit(f"Nothing entered for {env}.")
            save_secret(env, value)
    asyncio.run(verify(app.key))


def cmd_routines(args: argparse.Namespace) -> None:
    from shipmate import routines

    if args.action == "add":
        if not args.rest or len(args.rest) < 2:
            raise SystemExit('Usage: shipmate routines add "weekdays 08:00" "Brief me on my inbox"')
        try:
            r = routines.add(args.rest[0], " ".join(args.rest[1:]), args.allow or [])
        except ValueError as exc:
            raise SystemExit(str(exc)) from None
        console.print(f"Routine #{r['id']} saved. It runs while `shipmate run` or a chat is open.")
    elif args.action in ("rm", "remove"):
        ok = args.rest and routines.remove(args.rest[0].lstrip("#"))
        console.print("Removed." if ok else "No routine with that number.")
    elif args.action == "run":
        from shipmate.background import run_routine

        routine = next((r for r in routines.load() if args.rest and r["id"] == args.rest[0]), None)
        if routine is None:
            raise SystemExit("Which one? shipmate routines run <number>")
        model, _ = need_model(args.model)
        path = asyncio.run(run_routine(routine, model))
        console.print(path.read_text(), markup=False)
    else:
        rs = routines.load()
        for r in rs:
            allow = f"  [dim](may: {', '.join(r['allow'])})[/]" if r["allow"] else ""
            console.print(f"#{r['id']}  [bold]{r['when']:<16}[/] {r['task']}{allow}")
        if not rs:
            console.print(
                'No routines. Ask in chat, or: shipmate routines add "weekdays 08:00" "…"'
            )


def cmd_run(args: argparse.Namespace) -> None:
    from shipmate.background import scheduler

    model, name = need_model(args.model)
    console.print(f"[bold]Shipmate[/] running routines with {name}. Ctrl-C to stop.")
    asyncio.run(scheduler(model, lambda r, p: console.print(f"routine #{r['id']} → {p}")))


def cmd_inbox(args: argparse.Namespace) -> None:
    from rich.markdown import Markdown

    reports = (
        sorted((home() / "inbox").glob("*.md"))[-args.n :] if (home() / "inbox").exists() else []
    )
    for path in reports:
        console.rule(f"[dim]{path.name}[/]")
        console.print(Markdown(path.read_text()))
    if not reports:
        console.print("Nothing yet.")


def cmd_log(args: argparse.Namespace) -> None:
    path = home() / "log.jsonl"
    lines = path.read_text().splitlines()[-args.n :] if path.exists() else []
    for line in lines:
        entry = json.loads(line)
        if "call" in entry:
            console.print(f"[dim]{entry['at']}[/]  {entry['call']}", highlight=False)
        elif "decision" in entry:
            console.print(
                f"[dim]{entry['at']}[/]  [yellow]you said {entry['decision']}[/] to {entry['tool']}"
            )
        elif "routine" in entry:
            console.print(f"[dim]{entry['at']}[/]  routine #{entry['routine']} → {entry['report']}")
    if not lines:
        console.print("No calls yet.")


def cmd_egress(args: argparse.Namespace) -> None:
    from charter import ToolSession, format_egress_map

    from shipmate.apps import APPS, connected, find, load_tools

    if args.app:
        app = find(args.app)
        if app is None:
            raise SystemExit(f"No app called {args.app!r}.")
        apps = [app]
    else:
        apps = connected() or list(APPS)
    session = ToolSession(load_tools(apps))
    console.print(format_egress_map(session.tools), markup=False, highlight=False)


def main(argv: list[str] | None = None) -> None:
    load_secrets()  # before any pack is imported: API-key packs read the environment then

    model_help = "e.g. anthropic:claude-sonnet-5, openai:gpt-5.5, ollama:qwen3"
    parser = argparse.ArgumentParser(prog="shipmate", description="Your own personal agent.")
    parser.add_argument("--model", help=model_help)
    # Also accepted after the command; SUPPRESS keeps a missing one from erasing the first.
    with_model = argparse.ArgumentParser(add_help=False)
    with_model.add_argument("--model", default=argparse.SUPPRESS, help=model_help)
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("chat", parents=[with_model], help="talk to it (the default)")
    p = sub.add_parser("connect", help="connect an app or a model key")
    p.add_argument("app", nargs="?")
    p = sub.add_parser("routines", parents=[with_model], help="scheduled tasks")
    p.add_argument(
        "action", nargs="?", choices=["list", "add", "rm", "remove", "run"], default="list"
    )
    p.add_argument("rest", nargs="*")
    p.add_argument("--allow", action="append", help="a tool this routine may run without asking")
    sub.add_parser("run", parents=[with_model], help="run routines in the background")
    p = sub.add_parser("inbox", help="what routines reported")
    p.add_argument("-n", type=int, default=3)
    p = sub.add_parser("log", help="every API request it made")
    p.add_argument("-n", type=int, default=40)
    p = sub.add_parser("egress", help="which fields the model can see, per tool")
    p.add_argument("app", nargs="?")

    args = parser.parse_args(argv)
    commands = {
        None: cmd_chat,
        "chat": cmd_chat,
        "connect": cmd_connect,
        "routines": cmd_routines,
        "run": cmd_run,
        "inbox": cmd_inbox,
        "log": cmd_log,
        "egress": cmd_egress,
    }
    try:
        commands[args.command](args)
    except KeyboardInterrupt:
        console.print()
        sys.exit(130)
