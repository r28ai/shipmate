"""Everything Shipmate keeps lives in one folder: ~/.shipmate.

secrets.env   your keys, KEY=value, readable by you alone
policy.json   tools you said may run without asking
routines.json what runs on a schedule
memory.md     what it has been asked to remember
log.jsonl     every API call it made
inbox/        what each routine run reported
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def home() -> Path:
    root = Path(os.environ.get("SHIPMATE_HOME", "~/.shipmate")).expanduser()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return root


def write_private(path: Path, text: str) -> None:
    """Write a file only its owner can read, whether or not it existed."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.chmod(path, 0o600)


def read_secrets() -> dict[str, str]:
    path = home() / "secrets.env"
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
    return out


def load_secrets() -> None:
    """Put saved keys in the environment, where Charter's packs look for them.

    The shell wins: a variable you exported is never replaced by a saved one.
    Must run before any pack is imported, since API-key packs read the
    environment at import.
    """
    for key, value in read_secrets().items():
        os.environ.setdefault(key, value)


def save_secret(key: str, value: str) -> None:
    secrets = read_secrets()
    secrets[key] = value
    body = "".join(f"{k}={v}\n" for k, v in secrets.items())
    write_private(home() / "secrets.env", "# written by `shipmate connect`\n" + body)
    os.environ[key] = value


def read_json(name: str, default: Any) -> Any:
    path = home() / name
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except ValueError:
        return default


def write_json(name: str, data: Any) -> None:
    path = home() / name
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)
