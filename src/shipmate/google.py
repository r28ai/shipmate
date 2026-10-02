"""Connect a Google account with your own OAuth client. No broker in the middle.

Google only hands Gmail access to an app it knows, so you register one, once:
a "Desktop app" OAuth client in your own Google Cloud project. The consent
screen then says *your* app is asking, and the refresh token comes straight
back to this machine.
"""

from __future__ import annotations

import asyncio
import json
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from charter.auth import OAuth2Flow, OAuth2Server, scopes_for, states_match
from rich.console import Console

from shipmate.apps import GOOGLE_PACKS, pack_tools
from shipmate.home import home, save_secret, write_private

GOOGLE = OAuth2Server(
    issuer="https://accounts.google.com",
    authorization_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
    token_endpoint="https://oauth2.googleapis.com/token",
    token_endpoint_auth_method="client_secret_post",
    authorization_params={"access_type": "offline", "prompt": "consent"},
)

APIS = ",".join(
    [
        "gmail.googleapis.com",
        "calendar-json.googleapis.com",
        "drive.googleapis.com",
        "sheets.googleapis.com",
        "docs.googleapis.com",
        "forms.googleapis.com",
    ]
)

SETUP = f"""\
[bold]One-time setup in Google Cloud (about five minutes):[/]

 1. Turn on the APIs:
    https://console.cloud.google.com/flows/enableapi?apiid={APIS}
 2. Consent screen: https://console.cloud.google.com/auth/branding
    User type [bold]External[/]. Under Audience, add yourself as a test user, or
    press [bold]Publish app[/]: in Testing mode Google expires the sign-in after 7 days.
 3. Create the client: https://console.cloud.google.com/auth/clients
    Application type [bold]Desktop app[/] → Create → [bold]Download JSON[/].
"""


def read_client(path: Path) -> tuple[str, str]:
    data = json.loads(path.expanduser().read_text())
    client = data.get("installed") or data.get("web") or data
    return client["client_id"], client["client_secret"]


def wait_for_redirect(server: HTTPServer) -> dict[str, str]:
    """Serve the browser's one redirect back to us, and nothing else."""
    captured: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            query = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
            if "code" in query or "error" in query:
                captured.update(query)
            self.send_response(200)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.end_headers()
            done = "Connected. You can close this tab." if "code" in query else "Not connected."
            self.wfile.write(f"<h2 style='font-family:system-ui'>{done}</h2>".encode())

        def log_message(self, *args: object) -> None:
            pass

    server.RequestHandlerClass = Handler
    server.timeout = 5
    deadline = time.monotonic() + 300
    while not captured:
        if time.monotonic() > deadline:
            raise SystemExit("No answer from the browser in five minutes. Start again.")
        server.handle_request()
    return captured


async def connect(console: Console) -> Path:
    console.print(SETUP)
    raw = console.input("Path to the downloaded client JSON: ").strip().strip("'\"")
    client_id, client_secret = read_client(Path(raw))

    server = HTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    port = server.server_address[1]
    flow = OAuth2Flow(
        GOOGLE,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=f"http://127.0.0.1:{port}/",
    )
    scopes = scopes_for(t for pack in GOOGLE_PACKS for t in pack_tools(pack))
    request = flow.authorize(scopes)
    console.print("\nOpening Google in your browser. If it doesn't open, use this link:")
    console.print(request.url, style="dim", soft_wrap=True)
    webbrowser.open(request.url)

    try:
        params = await asyncio.to_thread(wait_for_redirect, server)
    finally:
        server.server_close()
    if "error" in params:
        raise SystemExit(f"Google said: {params['error']}")
    if not states_match(request.state, params.get("state", "")):
        raise SystemExit("The sign-in came back with the wrong state. Start again.")
    grant = await flow.exchange(params["code"], code_verifier=request.code_verifier)

    token_file = home() / "google.json"
    token = {
        "type": "authorized_user",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": grant.refresh_token,
    }
    write_private(token_file, json.dumps(token, indent=2))
    save_secret("GOOGLE_TOKEN_FILE", str(token_file))
    return token_file
