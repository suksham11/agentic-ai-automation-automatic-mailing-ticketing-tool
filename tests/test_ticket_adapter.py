from app.adapters.ticket_adapter import TicketAdapter
from app.core.config import Settings


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self) -> dict:
        return self._payload


class _FakeHttpClient:
    def __init__(self, *, get_responses: list[_FakeResponse] | None = None, put_response: _FakeResponse | None = None, post_response: _FakeResponse | None = None) -> None:
        self.get_responses = get_responses or []
        self.put_response = put_response or _FakeResponse(200, {})
        self.post_response = post_response or _FakeResponse(201, {"ticket": {"id": 999}})
        self.get_calls: list[dict] = []
        self.put_calls: list[dict] = []
        self.post_calls: list[dict] = []

    def __enter__(self) -> "_FakeHttpClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def get(self, url: str, params: dict | None = None, headers: dict | None = None):
        self.get_calls.append({"url": url, "params": params, "headers": headers})
        if self.get_responses:
            return self.get_responses.pop(0)
        return _FakeResponse(200, {"results": []})

    def put(self, url: str, json: dict | None = None, headers: dict | None = None):
        self.put_calls.append({"url": url, "json": json, "headers": headers})
        return self.put_response

    def post(self, url: str, json: dict | None = None, headers: dict | None = None):
        self.post_calls.append({"url": url, "json": json, "headers": headers})
        return self.post_response


def _settings() -> Settings:
    return Settings(
        zendesk_base_url="https://example.zendesk.com",
        zendesk_email="agent@example.com",
        zendesk_api_token="secret",
    )


def test_update_ticket_returns_not_configured_when_credentials_missing() -> None:
    adapter = TicketAdapter(
        Settings(
            zendesk_base_url="",
            zendesk_email="",
            zendesk_api_token="",
        )
    )

    result = adapter.update_ticket(ticket_id="TCK-1", body="reply")

    assert result["updated"] is False
    assert result["reason"] == "zendesk_not_configured"


def test_update_ticket_uses_numeric_ticket_id_without_search(monkeypatch) -> None:
    fake_client = _FakeHttpClient(put_response=_FakeResponse(200, {}))
    monkeypatch.setattr("app.adapters.ticket_adapter.httpx.Client", lambda timeout: fake_client)
    adapter = TicketAdapter(_settings())

    result = adapter.update_ticket(ticket_id="123", body="public reply", private_note=True)

    assert result["updated"] is True
    assert result["resolved_ticket_id"] == "123"
    assert result["private_note"] is True
    assert len(fake_client.get_calls) == 0
    assert len(fake_client.put_calls) == 1
    assert fake_client.put_calls[0]["json"]["ticket"]["comment"]["public"] is False


def test_update_ticket_searches_and_updates_when_external_id_matches(monkeypatch) -> None:
    search_hit = _FakeResponse(200, {"results": [{"id": 456}]})
    fake_client = _FakeHttpClient(get_responses=[search_hit], put_response=_FakeResponse(200, {}))
    monkeypatch.setattr("app.adapters.ticket_adapter.httpx.Client", lambda timeout: fake_client)
    adapter = TicketAdapter(_settings())

    result = adapter.update_ticket(ticket_id="TCK-456", body="reply")

    assert result["updated"] is True
    assert result["resolved_ticket_id"] == "456"
    assert len(fake_client.get_calls) == 1
    assert len(fake_client.put_calls) == 1


def test_update_ticket_creates_ticket_when_search_misses(monkeypatch) -> None:
    search_miss_1 = _FakeResponse(200, {"results": []})
    search_miss_2 = _FakeResponse(200, {"results": []})
    create_ok = _FakeResponse(201, {"ticket": {"id": 789}})
    fake_client = _FakeHttpClient(get_responses=[search_miss_1, search_miss_2], post_response=create_ok)
    monkeypatch.setattr("app.adapters.ticket_adapter.httpx.Client", lambda timeout: fake_client)
    adapter = TicketAdapter(_settings())

    result = adapter.update_ticket(
        ticket_id="TCK-789",
        body="reply",
        subject="Need help",
        requester_email="user@example.com",
    )

    assert result["updated"] is True
    assert result["created"] is True
    assert result["resolved_ticket_id"] == "789"
    assert len(fake_client.get_calls) == 2
    assert len(fake_client.post_calls) == 1
    payload = fake_client.post_calls[0]["json"]
    assert payload["ticket"]["external_id"] == "TCK-789"
    assert payload["ticket"]["requester"]["email"] == "user@example.com"


def test_update_ticket_does_not_send_invalid_requester_email(monkeypatch) -> None:
    search_miss_1 = _FakeResponse(200, {"results": []})
    search_miss_2 = _FakeResponse(200, {"results": []})
    create_ok = _FakeResponse(201, {"ticket": {"id": 790}})
    fake_client = _FakeHttpClient(get_responses=[search_miss_1, search_miss_2], post_response=create_ok)
    monkeypatch.setattr("app.adapters.ticket_adapter.httpx.Client", lambda timeout: fake_client)
    adapter = TicketAdapter(_settings())

    result = adapter.update_ticket(
        ticket_id="TCK-790",
        body="reply",
        subject="Need help",
        requester_email="Nam",
    )

    assert result["updated"] is True
    payload = fake_client.post_calls[0]["json"]
    assert "requester" not in payload["ticket"]


def test_update_ticket_returns_http_error_details_on_put_failure(monkeypatch) -> None:
    fake_client = _FakeHttpClient(put_response=_FakeResponse(500, {}, text="boom"))
    monkeypatch.setattr("app.adapters.ticket_adapter.httpx.Client", lambda timeout: fake_client)
    adapter = TicketAdapter(_settings())

    result = adapter.update_ticket(ticket_id="321", body="reply")

    assert result["updated"] is False
    assert result["reason"] == "zendesk_http_error"
    assert result["status_code"] == 500
    assert result["details"] == "boom"


def test_update_ticket_returns_create_http_error_details(monkeypatch) -> None:
    search_miss_1 = _FakeResponse(200, {"results": []})
    search_miss_2 = _FakeResponse(200, {"results": []})
    create_fail = _FakeResponse(422, {}, text="invalid requester")
    fake_client = _FakeHttpClient(get_responses=[search_miss_1, search_miss_2], post_response=create_fail)
    monkeypatch.setattr("app.adapters.ticket_adapter.httpx.Client", lambda timeout: fake_client)
    adapter = TicketAdapter(_settings())

    result = adapter.update_ticket(ticket_id="TCK-err", body="reply")

    assert result["updated"] is False
    assert result["reason"] == "zendesk_create_http_error"
    assert result["status_code"] == 422


def test_update_ticket_returns_request_error(monkeypatch) -> None:
    def _boom(timeout: float):
        raise RuntimeError("network down")

    monkeypatch.setattr("app.adapters.ticket_adapter.httpx.Client", _boom)
    adapter = TicketAdapter(_settings())

    result = adapter.update_ticket(ticket_id="123", body="reply")

    assert result["updated"] is False
    assert "zendesk_request_error" in result["reason"]
