import asyncio

import pytest
import respx

from shipmate.cli import status_table, verify


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SHIPMATE_HOME", str(tmp_path))
    for name in ("GOOGLE_TOKEN_FILE", "GOOGLE_REFRESH_TOKEN", "SHIPMATE_MODEL", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_ACCESS_TOKEN", "test-token")


@respx.mock
def test_a_google_grant_missing_calendar_is_not_called_connected(capsys):
    respx.get(url__regex=r".*/gmail/v1/users/me/labels").respond(json={"labels": []})
    denied = {"error": {"code": 403, "message": "Request had insufficient authentication scopes."}}
    respx.get(url__regex=r".*/calendar/v3/users/me/calendarList").respond(403, json=denied)
    respx.get(url__regex=r".*/drive/v3/files").respond(json={"files": []})

    with pytest.raises(SystemExit):
        asyncio.run(verify("google"))
    out = capsys.readouterr().out
    assert "connected" not in out
    assert "✓ gmail, gdrive" in out and "✗ gcalendar" in out


def test_the_status_names_the_model_in_use(monkeypatch, capsys):
    monkeypatch.setenv("SHIPMATE_MODEL", "fireworks:accounts/fireworks/models/glm-5p3-flash")
    status_table()
    assert "glm-5p3-flash" in capsys.readouterr().out


@respx.mock
def test_a_fine_grained_github_token_is_told_why_notifications_fail(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "github_pat_test")
    respx.get("https://api.github.com/user").respond(json={"login": "someone"})
    respx.get(url__regex=r"https://api.github.com/notifications.*").respond(
        403, json={"message": "Resource not accessible by personal access token"}
    )
    with pytest.raises(SystemExit):
        asyncio.run(verify("github"))
    out = capsys.readouterr().out
    assert "✓ users_get_authenticated as @someone" in out
    assert "✗ notifications_list: HTTP 403" in out and "classic token" in out


def test_the_gh_login_prompt_names_the_account_before_using_it(monkeypatch, tmp_path):
    from shipmate import cli

    monkeypatch.setattr(cli, "github_cli_token", lambda: "gho_main_account_token")
    monkeypatch.setattr(cli, "github_cli_login", lambda: "mainaccount")
    prompts = []

    def paste_sandbox_token(prompt=""):
        prompts.append(prompt)
        return "github_pat_sandbox"

    monkeypatch.setattr(cli.getpass, "getpass", paste_sandbox_token)
    monkeypatch.setattr(cli, "verify", lambda key: asyncio.sleep(0))
    cli.connect("github")
    assert "@mainaccount" in prompts[0]
    secrets = (tmp_path / "secrets.env").read_text()
    assert "GITHUB_TOKEN=github_pat_sandbox" in secrets and "gho_" not in secrets
