import base64
from email.message import EmailMessage

import httpx

from app.core.config import Settings


class EmailAdapter:
    """Gmail adapter.

    Returns status dictionaries instead of raising so API handlers can continue and
    surface integration warnings in responses.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _delivery_mode(self) -> str:
        return self.settings.email_delivery_mode.strip().lower() or "safe"

    def _is_live_mode(self) -> bool:
        return self._delivery_mode() == "live"

    def _allowed_recipients(self) -> set[str]:
        raw = self.settings.email_allowed_recipients
        if not raw:
            return set()
        return {item.strip().lower() for item in raw.split(",") if item.strip()}

    def _is_recipient_allowed(self, to_email: str) -> bool:
        allowed = self._allowed_recipients()
        if not allowed:
            return True
        return to_email.strip().lower() in allowed

    def _is_configured(self) -> bool:
        has_sender = bool(self.settings.gmail_sender_email)
        has_direct_token = bool(self.settings.gmail_access_token)
        has_refresh_flow = bool(
            self.settings.gmail_refresh_token
            and self.settings.gmail_client_id
            and self.settings.gmail_client_secret
        )
        return has_sender and (has_direct_token or has_refresh_flow)

    def _build_raw_message(self, to_email: str, subject: str, body: str) -> str:
        message = EmailMessage()
        message["To"] = to_email
        message["From"] = self.settings.gmail_sender_email
        message["Subject"] = subject
        message.set_content(body)
        return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")

    def _get_access_token(self, client: httpx.Client) -> tuple[str | None, str | None]:
        if self.settings.gmail_access_token:
            return self.settings.gmail_access_token, None

        refresh_token = self.settings.gmail_refresh_token
        client_id = self.settings.gmail_client_id
        client_secret = self.settings.gmail_client_secret
        if not (refresh_token and client_id and client_secret):
            return None, "gmail_oauth_config_missing"

        try:
            response = client.post(
                self.settings.gmail_token_url,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
        except Exception as exc:
            return None, f"gmail_token_request_error:{exc}"

        if response.status_code >= 400:
            return None, "gmail_token_http_error"

        access_token = response.json().get("access_token")
        if not access_token:
            return None, "gmail_token_missing_in_response"

        return str(access_token), None

    def send_email(self, to_email: str, subject: str, body: str) -> dict:
        if not self._is_live_mode():
            return {
                "sent": True,
                "to": to_email,
                "subject": subject,
                "reason": "email_safe_mode",
                "simulated": True,
            }

        if not self._is_recipient_allowed(to_email):
            return {
                "sent": False,
                "to": to_email,
                "subject": subject,
                "reason": "email_recipient_not_allowed",
            }

        if not self._is_configured():
            return {
                "sent": False,
                "to": to_email,
                "subject": subject,
                "reason": "gmail_not_configured",
            }

        raw_message = self._build_raw_message(to_email=to_email, subject=subject, body=body)

        try:
            with httpx.Client(timeout=20.0) as client:
                access_token, token_error = self._get_access_token(client)
                if not access_token:
                    return {
                        "sent": False,
                        "to": to_email,
                        "subject": subject,
                        "reason": token_error or "gmail_access_token_unavailable",
                    }

                response = client.post(
                    "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                    json={"raw": raw_message},
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                )
        except Exception as exc:
            return {
                "sent": False,
                "to": to_email,
                "subject": subject,
                "reason": f"gmail_request_error:{exc}",
            }

        if response.status_code >= 400:
            return {
                "sent": False,
                "to": to_email,
                "subject": subject,
                "reason": "gmail_http_error",
                "status_code": response.status_code,
            }

        payload = response.json()
        return {
            "sent": True,
            "to": to_email,
            "subject": subject,
            "message_id": payload.get("id"),
            "thread_id": payload.get("threadId"),
            "status_code": response.status_code,
        }
