"""Get a new YOUTUBE_REFRESH_TOKEN on your own computer.

    python scripts/youtube_refresh_token.py

It asks for the OAuth client id and secret (or reads YOUTUBE_CLIENT_ID /
YOUTUBE_CLIENT_SECRET), opens Google's consent page in your browser, catches
the answer on a local port and prints the refresh token. Nothing is sent
anywhere else. Put the printed token into the GitHub Actions secret
YOUTUBE_REFRESH_TOKEN (and on Render, if set there).

The OAuth client must be of type "Desktop app" (Google only allows the local
127.0.0.1 redirect for that type). If the consent screen is in "Testing" mode,
Google revokes refresh tokens after 7 days: publish the app to avoid that.
"""

from __future__ import annotations

import base64
import getpass
import hashlib
import http.server
import os
import secrets
import sys
import threading
import urllib.parse
import webbrowser

import httpx

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
# upload + thumbnails, and videos.update/delete + comments for "Yayınla" / "İptal"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def build_auth_url(client_id: str, redirect_uri: str, state: str, challenge: str) -> str:
    query = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",  # ask for a refresh token
        "prompt": "consent",  # always return one, even if consent was given before
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(query)}"


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    return verifier, challenge.decode()


def start_callback_server(state: str) -> tuple[http.server.HTTPServer, dict[str, str]]:
    """Local server for Google's redirect. ``result`` gets redirect_uri, then code or error."""
    result: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - http.server API
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            ok = params.get("state", [""])[0] == state and "code" in params
            if ok:
                result["code"] = params["code"][0]
            else:
                result["error"] = params.get("error", ["state uyuşmadı"])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = "Tamam, bu sekmeyi kapatabilirsin." if ok else "Hata: " + result["error"]
            self.wfile.write(f"<h2>{msg}</h2>".encode())
            threading.Thread(target=self.server.shutdown, daemon=True).start()

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    redirect_uri = f"http://127.0.0.1:{server.server_address[1]}/"
    result["redirect_uri"] = redirect_uri
    return server, result


def main() -> int:
    client_id = os.environ.get("YOUTUBE_CLIENT_ID") or input("YOUTUBE_CLIENT_ID: ").strip()
    client_secret = (
        os.environ.get("YOUTUBE_CLIENT_SECRET")
        or getpass.getpass("YOUTUBE_CLIENT_SECRET (yazarken görünmez): ").strip()
    )
    if not client_id or not client_secret:
        print("Client id ve secret gerekli.", file=sys.stderr)
        return 1

    state = secrets.token_urlsafe(16)
    verifier, challenge = pkce_pair()
    server, result = start_callback_server(state)
    url = build_auth_url(client_id, result["redirect_uri"], state, challenge)
    print("\nTarayıcıda Google izin sayfası açılıyor. Açılmazsa bu adresi kopyala:\n")
    print(url, "\n")
    webbrowser.open(url)
    server.serve_forever()  # returns after the single redirect
    if "code" not in result:
        print(f"İzin alınamadı: {result.get('error')}", file=sys.stderr)
        return 1

    r = httpx.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": result["code"],
            "code_verifier": verifier,
            "grant_type": "authorization_code",
            "redirect_uri": result["redirect_uri"],
        },
        timeout=30,
    )
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    token = body.get("refresh_token")
    if r.status_code >= 400 or not token:
        print(
            f"Token alınamadı: {body.get('error', r.status_code)} {body.get('error_description', '')}",
            file=sys.stderr,
        )
        return 1
    print("YENİ YOUTUBE_REFRESH_TOKEN (kimseyle paylaşma):\n")
    print(token)
    print("\nBunu GitHub → Settings → Secrets → Actions → YOUTUBE_REFRESH_TOKEN olarak kaydet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
