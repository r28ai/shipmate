"""The Google sign-in, end to end, with the browser and Google's token endpoint faked."""

import asyncio
import json
import os
import stat
import threading
import urllib.request
from urllib.parse import parse_qs, quote, urlparse

import respx

from shipmate import google


def test_connect_writes_a_private_grant_and_points_charter_at_it(tmp_path, monkeypatch):
    monkeypatch.setenv("SHIPMATE_HOME", str(tmp_path))
    monkeypatch.delenv("GOOGLE_TOKEN_FILE", raising=False)
    client = tmp_path / "client_secret.json"
    client.write_text(json.dumps({"installed": {"client_id": "cid", "client_secret": "csecret"}}))
    seen: dict = {}

    def browser(url: str) -> bool:
        """What the user's browser does after they press Allow: follow the redirect."""
        query = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        seen.update(query)
        back = f"{query['redirect_uri']}?code=the-code&state={query['state']}"
        threading.Thread(target=lambda: urllib.request.urlopen(back).read()).start()
        return True

    monkeypatch.setattr(google.webbrowser, "open", browser)

    class Console:
        def print(self, *args, **kwargs):
            pass

        def input(self, prompt=""):
            return f"'{client}'"  # dragged into the terminal, quotes and all

    with respx.mock:
        token = respx.post("https://oauth2.googleapis.com/token").respond(
            json={"access_token": "at", "refresh_token": "rt", "expires_in": 3600}
        )
        path = asyncio.run(google.connect(Console()))

    assert seen["redirect_uri"].startswith("http://127.0.0.1:")
    assert "https://www.googleapis.com/auth/gmail.modify" in seen["scope"].split()
    assert seen["code_challenge_method"] == "S256"
    assert b"code=the-code" in token.calls.last.request.content
    assert json.loads(path.read_text()) == {
        "type": "authorized_user",
        "client_id": "cid",
        "client_secret": "csecret",
        "refresh_token": "rt",
    }
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert os.environ["GOOGLE_TOKEN_FILE"] == str(path)
    assert f"GOOGLE_TOKEN_FILE={path}" in (tmp_path / "secrets.env").read_text()


def free_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_a_web_client_signs_in_at_its_registered_address(tmp_path, monkeypatch):
    monkeypatch.setenv("SHIPMATE_HOME", str(tmp_path))
    monkeypatch.delenv("GOOGLE_TOKEN_FILE", raising=False)
    registered = f"http://localhost:{free_port()}/auth/provider/callback"
    client = tmp_path / "web_client.json"
    client.write_text(
        json.dumps(
            {
                "web": {
                    "client_id": "cid",
                    "client_secret": "csecret",
                    "redirect_uris": ["https://example.com/callback", registered],
                }
            }
        )
    )
    seen: dict = {}

    def browser(url: str) -> bool:
        query = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        seen.update(query)
        back = f"{query['redirect_uri']}?code=the-code&state={query['state']}"
        threading.Thread(target=lambda: urllib.request.urlopen(back).read()).start()
        return True

    monkeypatch.setattr(google.webbrowser, "open", browser)

    class Console:
        def print(self, *args, **kwargs):
            pass

        def input(self, prompt=""):
            return str(client)

    with respx.mock:
        token = respx.post("https://oauth2.googleapis.com/token").respond(
            json={"access_token": "at", "refresh_token": "rt", "expires_in": 3600}
        )
        asyncio.run(google.connect(Console()))

    assert seen["redirect_uri"] == registered
    assert f"redirect_uri={quote(registered, safe='')}".encode() in token.calls.last.request.content


def test_a_web_client_without_a_localhost_address_says_what_to_add(tmp_path):
    import pytest

    client = tmp_path / "web_client.json"
    client.write_text(
        json.dumps(
            {"web": {"client_id": "c", "client_secret": "s", "redirect_uris": ["https://x.dev/cb"]}}
        )
    )
    with pytest.raises(SystemExit, match="Authorized redirect URIs"):
        google.read_client(client)
