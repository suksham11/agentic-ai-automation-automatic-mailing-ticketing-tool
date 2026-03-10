from contextlib import contextmanager
from datetime import datetime

from app.services import history


class _FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def order_by(self, _):
        return self

    def limit(self, _):
        return self

    def all(self):
        return self.rows


class _FakeSession:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.added = []
        self.committed = False

    def add(self, row):
        self.added.append(row)

    def commit(self):
        self.committed = True

    def query(self, _model):
        return _FakeQuery(self.rows)


def test_save_ticket_event_success(monkeypatch) -> None:
    fake_session = _FakeSession()

    @contextmanager
    def _session_ctx():
        yield fake_session

    monkeypatch.setattr(history, "get_session", _session_ctx)

    ok = history.save_ticket_event(
        ticket_id="T1",
        customer_email="user@example.com",
        subject="Help",
        message="Need support",
        status="processed",
        intent="general_support",
        confidence=0.77,
        requires_handoff=False,
        warnings=["minor_warning"],
        drafted_response="Thanks",
        cited_kb_files=["cancel_order.md"],
    )

    assert ok is True
    assert fake_session.committed is True
    assert len(fake_session.added) == 1
    assert fake_session.added[0].ticket_id == "T1"


def test_save_ticket_event_failure_returns_false(monkeypatch) -> None:
    @contextmanager
    def _broken_session_ctx():
        raise RuntimeError("db down")
        yield

    monkeypatch.setattr(history, "get_session", _broken_session_ctx)

    ok = history.save_ticket_event(
        ticket_id="T1",
        customer_email="user@example.com",
        subject="Help",
        message="Need support",
        status="processed",
        intent="general_support",
        confidence=0.77,
        requires_handoff=False,
        warnings=[],
        drafted_response="Thanks",
        cited_kb_files=[],
    )

    assert ok is False


def test_list_ticket_history_returns_items(monkeypatch) -> None:
    row = type(
        "Row",
        (),
        {
            "created_at": datetime(2026, 3, 1, 12, 0, 0),
            "ticket_id": "T2",
            "customer_email": "user@example.com",
            "subject": "Status",
            "status": "processed",
            "intent": "order_tracking",
            "confidence": 0.88,
            "requires_handoff": False,
            "warnings": "[\"w1\"]",
            "drafted_response": "reply",
            "cited_kb_files": "[\"file.md\"]",
        },
    )()
    fake_session = _FakeSession(rows=[row])

    @contextmanager
    def _session_ctx():
        yield fake_session

    monkeypatch.setattr(history, "get_session", _session_ctx)

    response = history.list_ticket_history(limit=10)

    assert len(response.items) == 1
    assert response.items[0].ticket_id == "T2"
    assert response.items[0].warnings == ["w1"]


def test_load_ticket_analytics_from_db_computes_counts(monkeypatch) -> None:
    row1 = type("Row", (), {"status": "processed", "requires_handoff": False, "confidence": 0.9, "intent": "order_tracking", "warnings": "[]"})()
    row2 = type("Row", (), {"status": "processed_with_warnings", "requires_handoff": True, "confidence": 0.6, "intent": "refund_request", "warnings": "[\"ticket_failed\"]"})()
    row3 = type("Row", (), {"status": "processed", "requires_handoff": False, "confidence": 0.75, "intent": "order_tracking", "warnings": "[\"ticket_failed\"]"})()
    fake_session = _FakeSession(rows=[row1, row2, row3])

    @contextmanager
    def _session_ctx():
        yield fake_session

    monkeypatch.setattr(history, "get_session", _session_ctx)

    analytics = history.load_ticket_analytics_from_db()

    assert analytics.total_tickets == 3
    assert analytics.processed_ok == 2
    assert analytics.processed_with_warnings == 1
    assert analytics.handoff_required == 1
    assert analytics.intent_breakdown[0].intent == "order_tracking"
    assert analytics.top_warnings[0] == "ticket_failed"
