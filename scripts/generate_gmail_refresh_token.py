import argparse
import json
import secrets
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

AUTH_BASE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
DEFAULT_SCOPE = "https://www.googleapis.com/auth/gmail.send"


def _load_client_config(client_json_path: Path) -> dict:
    payload = json.loads(client_json_path.read_text(encoding="utf-8"))
    config = payload.get("installed") or payload.get("web")
    if not config:
        raise ValueError("OAuth client JSON must contain an 'installed' or 'web' section.")

    required = ["client_id", "client_secret", "token_uri", "redirect_uris"]
    missing = [key for key in required if key not in config]
    if missing:
        raise ValueError(f"OAuth client JSON missing required keys: {', '.join(missing)}")

    return config


def _extract_code(user_input: str) -> str:
    text = user_input.strip()
    if text.startswith("http://") or text.startswith("https://"):
        parsed = urlparse(text)
        query = parse_qs(parsed.query)
        code = query.get("code", [""])[0]
        if not code:
            raise ValueError("No 'code' parameter found in pasted URL.")
        return code
    return text


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Gmail OAuth refresh token from client JSON.")
    parser.add_argument(
        "--client-json",
        default="client_secret_283523013155-s13fi6dnl8ffo04bi8l715seh2no8393.apps.googleusercontent.com.json",
        help="Path to OAuth client JSON downloaded from Google Cloud.",
    )
    parser.add_argument(
        "--scope",
        default=DEFAULT_SCOPE,
        help="OAuth scope to request (default: gmail.send).",
    )
    args = parser.parse_args()

    client_json_path = Path(args.client_json)
    if not client_json_path.exists():
        raise FileNotFoundError(f"Client JSON not found: {client_json_path}")

    config = _load_client_config(client_json_path)
    redirect_uri = str(config["redirect_uris"][0])
    state = secrets.token_urlsafe(24)

    auth_params = {
        "client_id": config["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": args.scope,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    auth_url = f"{AUTH_BASE_URL}?{urlencode(auth_params)}"

    print("1) Open this URL in your browser and approve access:\n")
    print(auth_url)
    print("\n2) After consent, browser redirects to localhost and may show an error page.")
    print("   Copy either the full redirected URL or only the 'code' value and paste below.\n")

    pasted = input("Paste redirect URL or code: ")
    auth_code = _extract_code(pasted)

    token_payload = {
        "client_id": config["client_id"],
        "client_secret": config["client_secret"],
        "code": auth_code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }

    with httpx.Client(timeout=30.0) as client:
        token_response = client.post(str(config["token_uri"]), data=token_payload)

    if token_response.status_code >= 400:
        print("\nToken exchange failed.")
        print(f"HTTP {token_response.status_code}: {token_response.text}")
        raise SystemExit(1)

    token_json = token_response.json()
    refresh_token = token_json.get("refresh_token")
    if not refresh_token:
        print("\nNo refresh_token returned.")
        print("Try again and ensure prompt=consent is used and this is the first consent for this client/scope combination.")
        print(f"Response: {token_json}")
        raise SystemExit(1)

    print("\nRefresh token generated successfully. Add these values to .env:\n")
    print(f"GMAIL_CLIENT_ID={config['client_id']}")
    print(f"GMAIL_CLIENT_SECRET={config['client_secret']}")
    print(f"GMAIL_REFRESH_TOKEN={refresh_token}")


if __name__ == "__main__":
    main()
