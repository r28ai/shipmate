"""The whole loop, offline: a scripted model, the real agent, real Charter tools, fake Gmail."""

import asyncio
import base64
import json
from typing import Any

import httpx
import pytest
import respx
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from shipmate.agent import build_agent, refuse, watch
from shipmate.apps import connected, find, load_tools

GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"

SEND = {
    "name": "gmail_messages_send",
    "args": {
        "userId": "me",
        "body": {"raw": {"to": "ana@example.com", "subject": "Late", "body": "Ten minutes late."}},
    },
    "id": "send-1",
}


class Scripted(GenericFakeChatModel):
    """Says what it is told to, in order, and accepts any tools it is given."""

    def bind_tools(self, tools: Any, **kwargs: Any) -> "Scripted":
        return self


def script(*calls: dict, final: str = "Done.") -> Scripted:
    turns = [AIMessage("", tool_calls=[call]) for call in calls] + [AIMessage(final)]
    return Scripted(messages=iter(turns))


def search(query: str) -> dict:
    return {"name": "ToolSearch", "args": {"query": query}, "id": f"search-{query}"}


@pytest.fixture(autouse=True)
def google(tmp_path, monkeypatch):
    monkeypatch.setenv("SHIPMATE_HOME", str(tmp_path))
    for name in ("GOOGLE_TOKEN_FILE", "GOOGLE_REFRESH_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GOOGLE_ACCESS_TOKEN", "test-token")


def run(model: Scripted, ask: Any, routine: dict | None = None) -> list:
    apps = [find("google")]
    agent = build_agent(model, apps, watch(load_tools(apps)), ask, routine=routine)
    state = asyncio.run(agent.ainvoke({"messages": [HumanMessage("go")]}))
    return state["messages"]


def answer(reply: str):
    asked: list[str] = []

    async def ask(name, tool, args):
        asked.append(name)
        return reply

    return ask, asked


@respx.mock
def test_a_read_runs_without_asking():
    route = respx.get(f"{GMAIL}/threads").respond(json={"threads": [{"id": "t1"}]})
    ask, asked = answer("no")

    messages = run(
        script(
            search("list gmail threads"),
            {"name": "gmail_threads_list", "args": {"q": "is:unread"}, "id": "r1"},
        ),
        ask,
    )

    assert route.called and asked == []
    assert (
        "t1"
        in next(
            m for m in messages if isinstance(m, ToolMessage) and m.name == "gmail_threads_list"
        ).text
    )


@respx.mock
def test_no_means_nothing_is_sent(tmp_path):
    route = respx.post(f"{GMAIL}/messages/send").respond(json={"id": "m1"})
    ask, asked = answer("no")

    messages = run(script(search("send an email"), SEND), ask)

    assert asked == ["gmail_messages_send"]
    assert not route.called
    refusal = next(m for m in messages if isinstance(m, ToolMessage) and m.tool_call_id == "send-1")
    assert refusal.status == "error" and "said no" in refusal.text
    entries = [json.loads(line) for line in (tmp_path / "log.jsonl").read_text().splitlines()]
    decisions = [e for e in entries if "decision" in e]
    assert [(d["decision"], d["tool"]) for d in decisions] == [("no", "gmail_messages_send")]


@respx.mock
def test_yes_sends_exactly_what_was_shown(tmp_path):
    route = respx.post(f"{GMAIL}/messages/send").respond(json={"id": "m1", "threadId": "t1"})
    ask, asked = answer("yes")

    run(script(search("send an email"), SEND), ask)

    assert asked == ["gmail_messages_send"] and route.call_count == 1
    sent: httpx.Request = route.calls.last.request
    raw = base64.urlsafe_b64decode(json.loads(sent.content)["raw"] + "==").decode()
    assert "To: ana@example.com" in raw and "Subject: Late" in raw
    assert sent.headers["authorization"] == "Bearer test-token"
    calls = [json.loads(line) for line in (tmp_path / "log.jsonl").read_text().splitlines()]
    assert any(c.get("tool") == "messages_send" and c.get("status_code") == 200 for c in calls)


@respx.mock
def test_always_is_remembered():
    respx.post(f"{GMAIL}/messages/send").respond(json={"id": "m1"})
    ask, asked = answer("always")
    run(script(search("send an email"), SEND), ask)

    ask, asked = answer("no")
    run(script(search("send an email"), SEND), ask)
    assert asked == []  # the second time it did not ask


@respx.mock
def test_a_routine_never_acts_unless_allowed():
    route = respx.post(f"{GMAIL}/messages/send").respond(json={"id": "m1"})
    routine = {"id": "1", "when": "daily 08:00", "task": "go", "allow": []}
    run(script(search("send an email"), SEND), refuse, routine=routine)
    assert not route.called

    routine["allow"] = ["gmail_messages_send"]
    run(script(search("send an email"), SEND), refuse, routine=routine)
    assert route.call_count == 1


def test_google_counts_as_connected_with_any_grant_shape(monkeypatch):
    from shipmate.apps import APPS

    for app in APPS:
        for name in app.env:
            if name != "GOOGLE_TOKEN_FILE":
                monkeypatch.delenv(name, raising=False)
    assert [app.key for app in connected()] == ["google"]


@respx.mock
def test_hosts_lists_every_server_it_talked_to(tmp_path, capsys):
    from shipmate.cli import main

    respx.post(f"{GMAIL}/messages/send").respond(json={"id": "m1"})
    ask, _ = answer("yes")
    run(script(search("send an email"), SEND), ask)

    main(["hosts"])
    out = capsys.readouterr().out
    assert "gmail.googleapis.com" in out and "google" in out
    assert "GenericFakeChatModel" in out or "Scripted" in out  # the model's row
