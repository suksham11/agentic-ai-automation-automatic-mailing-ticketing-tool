from fastapi.testclient import TestClient

from app.api import routes
from app.main import app
from app.models.schemas import AgentDecision


client = TestClient(app)


def _payload(send_email: bool = True) -> dict:
    return {
        "ticket_id": "TCK-9001",
        "customer_email": "user@example.com",
        "subject": "Need support",
        "message": "Please help with my order",
        "send_email": send_email,
    }


def _decision() -> AgentDecision:
    return AgentDecision(
        intent="order_tracking",
        confidence=0.82,
        requires_human_handoff=False,
        drafted_response="Resolved response",
        cited_kb_files=["cancel_order.md"],
    )


def test_process_message_success_without_warnings(monkeypatch) -> None:
    monkeypatch.setattr(routes.SupportAgentService, "process_message", lambda self, inbound: _decision())
    monkeypatch.setattr(routes.TicketAdapter, "update_ticket", lambda self, **kwargs: {"updated": True, "status_code": 200})
    monkeypatch.setattr(routes.EmailAdapter, "send_email", lambda self, **kwargs: {"sent": True})
    monkeypatch.setattr(routes, "save_ticket_event", lambda **kwargs: True)

    response = client.post("/v1/process-message", json=_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "processed"
    assert body["warnings"] == []
    assert body["decision"]["intent"] == "order_tracking"


def test_process_message_collects_ticket_and_email_warnings(monkeypatch) -> None:
    monkeypatch.setattr(routes.SupportAgentService, "process_message", lambda self, inbound: _decision())
    monkeypatch.setattr(
        routes.TicketAdapter,
        "update_ticket",
        lambda self, **kwargs: {
            "updated": False,
            "reason": "zendesk_http_error",
            "status_code": 500,
            "details": "server failed",
        },
    )
    monkeypatch.setattr(routes.EmailAdapter, "send_email", lambda self, **kwargs: {"sent": False, "reason": "gmail_http_error"})
    monkeypatch.setattr(routes, "save_ticket_event", lambda **kwargs: True)

    response = client.post("/v1/process-message", json=_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "processed_with_warnings"
    assert any(item.startswith("ticket_update_failed:zendesk_http_error:http_500") for item in body["warnings"])
    assert "email_send_failed:gmail_http_error" in body["warnings"]


def test_process_message_skips_email_when_send_email_false(monkeypatch) -> None:
    monkeypatch.setattr(routes.SupportAgentService, "process_message", lambda self, inbound: _decision())
    monkeypatch.setattr(routes.TicketAdapter, "update_ticket", lambda self, **kwargs: {"updated": True})

    called = {"email": 0}

    def _email_stub(self, **kwargs):
        called["email"] += 1
        return {"sent": True}

    monkeypatch.setattr(routes.EmailAdapter, "send_email", _email_stub)
    monkeypatch.setattr(routes, "save_ticket_event", lambda **kwargs: True)

    response = client.post("/v1/process-message", json=_payload(send_email=False))

    assert response.status_code == 200
    assert called["email"] == 0
    assert response.json()["status"] == "processed"


def test_process_message_db_write_is_background_task(monkeypatch) -> None:
    """DB persistence is a background task; its outcome no longer affects the
    synchronous response status – failures are handled asynchronously."""
    monkeypatch.setattr(routes.SupportAgentService, "process_message", lambda self, inbound: _decision())
    monkeypatch.setattr(routes.TicketAdapter, "update_ticket", lambda self, **kwargs: {"updated": True})
    monkeypatch.setattr(routes.EmailAdapter, "send_email", lambda self, **kwargs: {"sent": True})
    # Stub save_ticket_event to raise so we can verify it doesn't break the response.
    monkeypatch.setattr(routes, "save_ticket_event", lambda **kwargs: False)

    response = client.post("/v1/process-message", json=_payload())

    assert response.status_code == 200
    body = response.json()
    # The response is "processed" regardless of the background DB write result.
    assert body["status"] == "processed"
    assert "database_write_failed" not in body["warnings"]


def test_ticket_history_limit_is_clamped(monkeypatch) -> None:
    seen = {"limit": None}

    def _history_stub(limit: int):
        seen["limit"] = limit
        return {"items": []}

    monkeypatch.setattr(routes, "list_ticket_history", _history_stub)

    low = client.get("/v1/tickets/history?limit=0")
    high = client.get("/v1/tickets/history?limit=9999")

    assert low.status_code == 200
    assert high.status_code == 200
    assert seen["limit"] == 500


def test_ticket_analytics_route_uses_history_service(monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "load_ticket_analytics_from_db",
        lambda: {
            "total_tickets": 2,
            "processed_ok": 2,
            "processed_with_warnings": 0,
            "handoff_required": 0,
            "handoff_rate": 0.0,
            "average_confidence": 0.9,
            "intent_breakdown": [{"intent": "order_tracking", "count": 2}],
            "top_warnings": [],
        },
    )

    response = client.get("/v1/ticket-analytics")

    assert response.status_code == 200
    body = response.json()
    assert body["total_tickets"] == 2
    assert body["intent_breakdown"][0]["intent"] == "order_tracking"
    assert "handoff_rate" in body
