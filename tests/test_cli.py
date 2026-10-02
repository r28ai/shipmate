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
