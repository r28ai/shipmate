"""Every provider's own LangChain client, through Shipmate's agent, against a local fake server.

The fake answers the first request with a call to Shipmate's `list_routines` tool and
the second with text, so each client's tool-call round trip is exercised, not just a
reply. Nothing leaves this machine.
"""

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import respx
from langchain_core.messages import HumanMessage

from shipmate import models
from shipmate.agent import build_agent
from shipmate.models import PROVIDERS, load_model, model_host, model_name

ANSWER = "No routines yet."


class FakeModelServer(BaseHTTPRequestHandler):
    seen: list[tuple[str, dict, dict]] = []

    def do_POST(self) -> None:  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        type(self).seen.append((self.path, {k.lower(): v for k, v in self.headers.items()}, body))
        answered = any(m.get("role") == "tool" for m in body.get("messages", []))
        if self.path.endswith("/api/chat"):
            self.ollama(body, answered)
        else:
            self.openai(body, answered)

    def ollama(self, body: dict, answered: bool) -> None:
        call = {"function": {"name": "list_routines", "arguments": {}}}
        message = {"role": "assistant", "content": ANSWER if answered else ""}
        if not answered:
            message["tool_calls"] = [call]
        done = {
            "model": body["model"],
            "created_at": "2026-10-03T00:00:00Z",
            "message": message,
            "done": True,
            "done_reason": "stop",
        }
        self.reply("application/x-ndjson", json.dumps(done) + "\n")

    def openai(self, body: dict, answered: bool) -> None:
        call = {
            "index": 0,
            "id": "call_1",
            "type": "function",
            "function": {"name": "list_routines", "arguments": "{}"},
        }
        finish = "stop" if answered else "tool_calls"
        base = {"id": "c1", "created": 0, "model": body["model"], "system_fingerprint": "fp"}
        usage = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
        if body.get("stream"):
            delta = (
                {"role": "assistant", "content": ANSWER}
                if answered
                else {"role": "assistant", "content": None, "tool_calls": [call]}
            )
            chunk = {
                **base,
                "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
                "usage": usage,
            }
            self.reply("text/event-stream", f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n")
            return
        message = (
            {"role": "assistant", "content": ANSWER}
            if answered
            else {
                "role": "assistant",
                "content": None,
                "tool_calls": [{k: v for k, v in call.items() if k != "index"}],
            }
        )
        full = {
            **base,
            "object": "chat.completion",
            "choices": [{"index": 0, "message": message, "finish_reason": finish}],
            "usage": usage,
        }
        self.reply("application/json", json.dumps(full))

    def reply(self, content_type: str, text: str) -> None:
        data = text.encode()
        self.send_response(200)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def server():
    FakeModelServer.seen = []
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeModelServer)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SHIPMATE_HOME", str(tmp_path))
    monkeypatch.delenv("SHIPMATE_MODEL", raising=False)
    for p in PROVIDERS:
        if p.env:
            monkeypatch.delenv(p.env, raising=False)


# provider, the model, where its client posts (relative to the fake), the path it uses
CASES = [
    ("fireworks", None, "/inference", "/inference/v1/chat/completions"),
    ("openrouter", None, "/api/v1", "/api/v1/chat/completions"),
    ("together", None, "/v1", "/v1/chat/completions"),
    ("ollama", "ollama:qwen3", "", "/api/chat"),
]


@pytest.mark.parametrize("key, name, prefix, path", CASES, ids=[c[0] for c in CASES])
def test_each_provider_runs_a_tool_call_round_trip(server, monkeypatch, key, name, prefix, path):
    provider = models.find(key)
    if provider.env:
        monkeypatch.setenv(provider.env, f"test-{key}-key")
    name = name or provider.default
    model = load_model(name, base_url=server + prefix)
    agent = build_agent(model, [], [], ask=None)

    state = asyncio.run(agent.ainvoke({"messages": [HumanMessage("what's scheduled?")]}))

    assert state["messages"][-1].text == ANSWER
    assert [m.name for m in state["messages"] if m.type == "tool"] == ["list_routines"]
    assert [p for p, _, _ in FakeModelServer.seen] == [path, path]
    _, headers, body = FakeModelServer.seen[0]
    assert body["model"] == name.split(":", 1)[1]
    if provider.env:
        assert f"test-{key}-key" in headers.get("authorization", "")


@pytest.mark.parametrize(
    "key, host",
    [
        ("fireworks", "api.fireworks.ai"),
        ("openrouter", "openrouter.ai"),
        ("together", "api.together.xyz"),
        ("ollama", "localhost:11434"),
    ],
)
def test_hosts_names_each_providers_server(monkeypatch, key, host):
    provider = models.find(key)
    if provider.env:
        monkeypatch.setenv(provider.env, "x")
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    assert model_host(load_model(provider.default or "ollama:qwen3")) == host


def test_the_first_provider_with_a_key_picks_the_model(monkeypatch):
    assert model_name() is None
    monkeypatch.setenv("TOGETHER_API_KEY", "x")
    assert model_name() == "together:zai-org/GLM-5.3-Flash"
    monkeypatch.setenv("FIREWORKS_API_KEY", "x")
    assert model_name() == "fireworks:accounts/fireworks/models/glm-5p3-flash"
    monkeypatch.setenv("SHIPMATE_MODEL", "openrouter:z-ai/glm-5.3-flash")
    assert model_name() == "openrouter:z-ai/glm-5.3-flash"
    assert model_name("ollama:qwen3") == "ollama:qwen3"


def test_connecting_a_provider_saves_its_key_and_makes_it_the_model(tmp_path, monkeypatch):
    from shipmate import cli

    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": "or-test-key")
    cli.connect("openrouter")
    secrets = (tmp_path / "secrets.env").read_text()
    assert "OPENROUTER_API_KEY=or-test-key" in secrets
    assert "SHIPMATE_MODEL=openrouter:z-ai/glm-5.3-flash" in secrets
    assert model_name() == "openrouter:z-ai/glm-5.3-flash"


@respx.mock
def test_connecting_ollama_picks_from_the_models_it_has(tmp_path, monkeypatch):
    from shipmate import cli

    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    tags = {"models": [{"name": "qwen3:8b"}, {"name": "llama3.3:70b"}]}
    respx.get("http://localhost:11434/api/tags").respond(json=tags)
    monkeypatch.setattr(cli.console, "input", lambda prompt="": "2")
    cli.connect("ollama")
    assert "SHIPMATE_MODEL=ollama:llama3.3:70b" in (tmp_path / "secrets.env").read_text()


@respx.mock
def test_connecting_ollama_when_it_is_not_running_says_so(monkeypatch):
    import httpx

    from shipmate import cli

    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    respx.get("http://localhost:11434/api/tags").mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(SystemExit, match="isn't running"):
        cli.connect("ollama")
