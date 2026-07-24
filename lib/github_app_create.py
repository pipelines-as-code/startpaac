#!/usr/bin/env python3
# Copyright 2026 Chmouel Boudjnah <chmouel@chmouel.com>
"""Create a GitHub App for Pipelines-as-Code using the App Manifest flow.

Starts a loopback HTTP server, opens a browser page that submits the app
manifest to GitHub, receives the redirect with the temporary code and
exchanges it for the app credentials, which are written to --output-dir.

Standard library only. Progress goes to stderr, a JSON summary to stdout.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import secrets
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

DEFAULT_EVENTS = [
    "check_run",
    "check_suite",
    "commit_comment",
    "issue_comment",
    "pull_request",
    "push",
]

DEFAULT_PERMISSIONS = {
    "checks": "write",
    "contents": "write",
    "issues": "write",
    "members": "read",
    "metadata": "read",
    "organization_plan": "read",
    "pull_requests": "write",
}

SECRET_KEYS = {
    "github-application-id": "id",
    "github-private-key": "pem",
    "webhook.secret": "webhook_secret",
}


def build_manifest(app_name: str, webhook_url: str, redirect_url: str) -> dict:
    return {
        "name": app_name,
        "url": "https://pipelinesascode.com",
        "hook_attributes": {"url": webhook_url, "active": True},
        "redirect_url": redirect_url,
        "public": False,
        "default_permissions": DEFAULT_PERMISSIONS,
        "default_events": DEFAULT_EVENTS,
    }


def github_new_app_url(github_url: str, org: str, state: str) -> str:
    base = github_url.rstrip("/")
    if org:
        return (
            f"{base}/organizations/{urllib.parse.quote(org, safe='')}"
            f"/settings/apps/new?state={state}"
        )
    return f"{base}/settings/apps/new?state={state}"


def landing_page(post_url: str, manifest: dict) -> bytes:
    manifest_value = html.escape(json.dumps(manifest), quote=True)
    page = f"""<!DOCTYPE html>
<html>
<head><title>startpaac - create GitHub App</title></head>
<body onload="document.forms[0].submit()">
<form action="{html.escape(post_url, quote=True)}" method="post">
<input type="hidden" name="manifest" value="{manifest_value}">
<noscript><button type="submit">Create GitHub App</button></noscript>
</form>
<p>Redirecting you to GitHub to create the app&hellip;</p>
</body>
</html>"""
    return page.encode()


SUCCESS_PAGE = b"""<!DOCTYPE html>
<html>
<head><title>startpaac - GitHub App created</title></head>
<body>
<h1>&#127881; GitHub App created</h1>
<p>Credentials were saved. You can close this tab and go back to your
terminal.</p>
</body>
</html>"""


def parse_conversion(data: dict) -> dict:
    required = ("id", "pem", "webhook_secret", "html_url", "slug")
    missing = [key for key in required if not data.get(key)]
    if missing:
        raise ValueError(
            f"GitHub conversion response is missing fields: {', '.join(missing)}"
        )
    return {key: data[key] for key in required}


def convert_code(api_url: str, code: str, timeout: int = 30) -> dict:
    url = f"{api_url.rstrip('/')}/app-manifests/{urllib.parse.quote(code, safe='')}/conversions"
    req = urllib.request.Request(
        url,
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "startpaac-github-app-setup",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
        data = json.loads(resp.read().decode())
    return parse_conversion(data)


def write_secret_file(path: str, content: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fp:
        fp.write(content)


def write_secrets(output_dir: str, result: dict) -> None:
    os.makedirs(output_dir, mode=0o700, exist_ok=True)
    for filename, key in SECRET_KEYS.items():
        content = str(result[key])
        if key != "pem" and not content.endswith("\n"):
            content += "\n"
        write_secret_file(os.path.join(output_dir, filename), content)


class ManifestHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args) -> None:  # silence request logging
        pass

    def _respond(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        parsed = urllib.parse.urlparse(self.path)
        server = self.server
        if parsed.path == "/":
            self._respond(200, server.landing_page)
            return
        if parsed.path != "/callback":
            self._respond(404, b"not found")
            return
        query = urllib.parse.parse_qs(parsed.query)
        state = query.get("state", [""])[0]
        code = query.get("code", [""])[0]
        if not code or not secrets.compare_digest(state, server.expected_state):
            server.failure = "callback with an invalid state or missing code"
            self._respond(400, b"invalid state or missing code")
            server.done.set()
            return
        try:
            server.result = convert_code(server.api_url, code)
        except Exception as exc:  # pylint: disable=broad-except
            server.failure = f"failed to exchange the manifest code: {exc}"
            self._respond(502, b"failed to exchange the manifest code")
            server.done.set()
            return
        self._respond(200, SUCCESS_PAGE)
        server.done.set()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-name", required=True, help="GitHub App name")
    parser.add_argument(
        "--webhook-url", required=True, help="Webhook URL set on the app"
    )
    parser.add_argument(
        "--output-dir", required=True, help="Directory where credentials are written"
    )
    parser.add_argument("--org", default="", help="Create the app in this organization")
    parser.add_argument(
        "--github-url", default="https://github.com", help="GitHub web base URL"
    )
    parser.add_argument(
        "--github-api-url",
        default="https://api.github.com",
        help="GitHub API base URL",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Seconds to wait for the browser flow to complete",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open a browser, only print the URL to visit",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    state = secrets.token_urlsafe(32)

    server = HTTPServer(("127.0.0.1", 0), ManifestHandler)
    port = server.server_address[1]
    redirect_url = f"http://127.0.0.1:{port}/callback"
    manifest = build_manifest(args.app_name, args.webhook_url, redirect_url)
    server.landing_page = landing_page(
        github_new_app_url(args.github_url, args.org, state), manifest
    )
    server.expected_state = state
    server.api_url = args.github_api_url
    server.result = None
    server.failure = ""
    server.done = threading.Event()

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    local_url = f"http://127.0.0.1:{port}/"
    print(f"Waiting for GitHub App creation at: {local_url}", file=sys.stderr, flush=True)
    if not args.no_browser:
        webbrowser.open(local_url)

    try:
        completed = server.done.wait(args.timeout)
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130
    finally:
        server.shutdown()

    if not completed:
        print(f"Timed out after {args.timeout}s waiting for GitHub", file=sys.stderr, flush=True)
        return 2
    if server.failure or not server.result:
        print(f"Error: {server.failure or 'no result received'}", file=sys.stderr, flush=True)
        return 1

    write_secrets(args.output_dir, server.result)
    summary = {
        "id": server.result["id"],
        "slug": server.result["slug"],
        "html_url": server.result["html_url"],
        "install_url": f"{server.result['html_url']}/installations/new",
    }
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
