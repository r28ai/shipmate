"""Running routines: on schedule while `shipmate run` (or a chat) is open."""

from __future__ import annotations

import asyncio
import platform
import re
import shutil
import subprocess
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage

from shipmate import routines
from shipmate.agent import build_agent, log, refuse, watch
from shipmate.apps import connected, load_tools
from shipmate.home import home


def notify(title: str, message: str) -> None:
    """A desktop notification, where the OS offers one without extra installs."""
    message = message.replace('"', "'")[:200]
    title = title.replace('"', "'")
    if platform.system() == "Darwin":
        script = f'display notification "{message}" with title "{title}"'
        subprocess.run(["osascript", "-e", script], check=False, capture_output=True)
    elif shutil.which("notify-send"):
        subprocess.run(["notify-send", title, message], check=False, capture_output=True)


def inbox() -> Path:
    path = home() / "inbox"
    path.mkdir(exist_ok=True)
    return path


async def run_routine(routine: dict, model: Any) -> Path:
    """Run one routine now and file its report. Returns where the report went."""
    started = datetime.now()
    routines.mark_run(routine["id"], started)  # before running: a failure must not loop
    apps = connected()
    agent = build_agent(model, apps, watch(load_tools(apps)), refuse, routine=routine)
    try:
        state = await agent.ainvoke({"messages": [HumanMessage(routine["task"])]})
        report = state["messages"][-1].text or "(no report)"
    except Exception as exc:  # a routine failing must not stop the others
        report = f"This run failed: {type(exc).__name__}: {exc}"
    slug = re.sub(r"[^a-z0-9]+", "-", routine["task"].lower())[:40].strip("-")
    path = inbox() / f"{started:%Y-%m-%d-%H%M}-{routine['id']}-{slug}.md"
    path.write_text(
        f"# {routine['task']}\n\n_{routine['when']} · {started:%a %d %b %H:%M}_\n\n{report}\n"
    )
    log({"routine": routine["id"], "report": str(path)})
    first_line = next((line for line in report.splitlines() if line.strip()), "")
    notify(f"Shipmate · routine #{routine['id']}", first_line.lstrip("#* "))
    return path


async def scheduler(model: Any, on_report: Callable[[dict, Path], None] | None = None) -> None:
    """Check every 30 seconds for routines that are due, and run them one at a time."""
    while True:
        for routine in routines.due():
            path = await run_routine(routine, model)
            if on_report:
                on_report(routine, path)
        await asyncio.sleep(30)
