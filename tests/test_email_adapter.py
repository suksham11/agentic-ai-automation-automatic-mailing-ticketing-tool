from app.adapters.email_adapter import EmailAdapter
from app.core.config import Settings


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, responses_by_url: dict[str, _FakeResponse]) -> None:
        self.responses_by_url = responses_by_url
        self.calls: list[dict] = []

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def post(self, url: str, data: dict | None = None, json: dict | None = None, headers: dict | None = None):
        self.calls.append({"url": url, "data": data, "json": json, "headers": headers})
        return self.responses_by_url[url]


def test_send_email_not_configured() -> None:
    adapter = EmailAdapter(Settings(gmail_sender_email="", email_delivery_mode="live"))

    result = adapter.send_email("user@example.com", "Subject", "Body")

    assert result["sent"] is False
    assert result["reason"] == "gmail_not_configured"


def test_send_email_with_direct_access_token(monkeypatch) -> None:
    settings = Settings(
        gmail_sender_email="support@example.com",
        gmail_access_token="access-token",
        email_delivery_mode="live",
    )
    adapter = EmailAdapter(settings)

    send_url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
    fake_client = _FakeClient(
        responses_by_url={
            send_url: _FakeResponse(200, {"id": "msg-1", "threadId": "thr-1"}),
        }
    )
    monkeypatch.setattr("app.adapters.email_adapter.httpx.Client", lambda timeout: fake_client)

    result = adapter.send_email("user@example.com", "Support", "Hello from support")

    assert result["sent"] is True
    assert result["message_id"] == "msg-1"
    assert len(fake_client.calls) == 1
    assert fake_client.calls[0]["url"] == send_url
    assert fake_client.calls[0]["headers"]["Authorization"] == "Bearer access-token"


def test_send_email_with_refresh_token(monkeypatch) -> None:
    settings = Settings(
        gmail_sender_email="support@example.com",
        gmail_refresh_token="refresh-token",
        gmail_client_id="client-id",
        gmail_client_secret="client-secret",
        email_delivery_mode="live",
    )
    adapter = EmailAdapter(settings)

    token_url = "https://oauth2.googleapis.com/token"
    send_url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
    fake_client = _FakeClient(
        responses_by_url={
            token_url: _FakeResponse(200, {"access_token": "new-access-token"}),
            send_url: _FakeResponse(200, {"id": "msg-2", "threadId": "thr-2"}),
        }
    )
    monkeypatch.setattr("app.adapters.email_adapter.httpx.Client", lambda timeout: fake_client)

    result = adapter.send_email("user@example.com", "Support", "Refresh flow")

    assert result["sent"] is True
    assert result["thread_id"] == "thr-2"
    assert len(fake_client.calls) == 2
    assert fake_client.calls[0]["url"] == token_url
    assert fake_client.calls[1]["headers"]["Authorization"] == "Bearer new-access-token"


def test_send_email_safe_mode_simulates_send() -> None:
    adapter = EmailAdapter(Settings(email_delivery_mode="safe"))

    result = adapter.send_email("user@example.com", "Subject", "Body")

    assert result["sent"] is True
    assert result["simulated"] is True
    assert result["reason"] == "email_safe_mode"


def test_send_email_live_mode_enforces_allow_list() -> None:
    settings = Settings(
        gmail_sender_email="support@example.com",
        gmail_access_token="access-token",
        email_delivery_mode="live",
        email_allowed_recipients="qa@example.com",
    )
    adapter = EmailAdapter(settings)

    result = adapter.send_email("user@example.com", "Subject", "Body")

    assert result["sent"] is False
    assert result["reason"] == "email_recipient_not_allowed"
