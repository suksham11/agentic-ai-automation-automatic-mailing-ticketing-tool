from collections import Counter

from app.models.schemas import TicketAnalyticsResponse, TicketHistoryItem, TicketHistoryResponse, IntentCount
from app.models.ticket_event import TicketEvent
from app.services.persistence import from_json_list, get_session, to_json_list


def save_ticket_event(
    *,
    ticket_id: str,
    customer_email: str,
    subject: str,
    message: str,
    status: str,
    intent: str,
    confidence: float,
    requires_handoff: bool,
    warnings: list[str],
    drafted_response: str,
    cited_kb_files: list[str],
) -> bool:
    try:
        with get_session() as session:
            row = TicketEvent(
                ticket_id=ticket_id,
                customer_email=customer_email or "",
                subject=subject or "",
                message=message or "",
                status=status,
                intent=intent,
                confidence=confidence,
                requires_handoff=requires_handoff,
                warnings=to_json_list(warnings),
                drafted_response=drafted_response,
                cited_kb_files=to_json_list(cited_kb_files),
            )
            session.add(row)
            session.commit()
        return True
    except Exception:
        return False


def list_ticket_history(limit: int = 50) -> TicketHistoryResponse:
    items: list[TicketHistoryItem] = []
    try:
        with get_session() as session:
            rows = (
                session.query(TicketEvent)
                .order_by(TicketEvent.created_at.desc())
                .limit(limit)
                .all()
            )
        for row in rows:
            items.append(
                TicketHistoryItem(
                    created_at=row.created_at.isoformat(),
                    ticket_id=row.ticket_id,
                    customer_email=row.customer_email,
                    subject=row.subject,
                    status=row.status,
                    intent=row.intent,
                    confidence=row.confidence,
                    requires_handoff=row.requires_handoff,
                    warnings=from_json_list(row.warnings),
                    drafted_response=row.drafted_response,
                    cited_kb_files=from_json_list(row.cited_kb_files),
                )
            )
    except Exception:
        return TicketHistoryResponse(items=[])

    return TicketHistoryResponse(items=items)


def load_ticket_analytics_from_db() -> TicketAnalyticsResponse:
    try:
        with get_session() as session:
            rows = session.query(TicketEvent).all()
    except Exception:
        return TicketAnalyticsResponse(
            total_tickets=0,
            processed_ok=0,
            processed_with_warnings=0,
            handoff_required=0,
            average_confidence=0.0,
            intent_breakdown=[],
            top_warnings=[],
        )

    if not rows:
        return TicketAnalyticsResponse(
            total_tickets=0,
            processed_ok=0,
            processed_with_warnings=0,
            handoff_required=0,
            average_confidence=0.0,
            intent_breakdown=[],
            top_warnings=[],
        )

    total = len(rows)
    processed_ok = sum(1 for row in rows if row.status == "processed")
    processed_warn = sum(1 for row in rows if row.status == "processed_with_warnings")
    handoff_required = sum(1 for row in rows if row.requires_handoff)
    avg_conf = round(sum(row.confidence for row in rows) / total, 3)

    intent_counts = Counter(row.intent for row in rows)
    warning_counts = Counter()
    for row in rows:
        for warning in from_json_list(row.warnings):
            warning_counts[warning] += 1

    return TicketAnalyticsResponse(
        total_tickets=total,
        processed_ok=processed_ok,
        processed_with_warnings=processed_warn,
        handoff_required=handoff_required,
        average_confidence=avg_conf,
        intent_breakdown=[IntentCount(intent=i, count=c) for i, c in intent_counts.most_common()],
        top_warnings=[k for k, _ in warning_counts.most_common(5)],
    )
