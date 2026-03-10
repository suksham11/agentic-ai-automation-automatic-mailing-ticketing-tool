from fastapi import APIRouter, Depends

from app.adapters.email_adapter import EmailAdapter
from app.adapters.ticket_adapter import TicketAdapter
from app.core.config import Settings, get_settings
from app.models.schemas import (
    InboundMessage,
    ProcessMessageResponse,
    TicketAnalyticsResponse,
    TicketHistoryResponse,
)
from app.services.history import load_ticket_analytics_from_db, list_ticket_history, save_ticket_event
from app.services.agent import SupportAgentService

router = APIRouter(prefix="/v1", tags=["support-agent"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/process-message", response_model=ProcessMessageResponse)
def process_message(
    payload: InboundMessage,
    settings: Settings = Depends(get_settings),
) -> ProcessMessageResponse:
    service = SupportAgentService(settings)
    ticket_client = TicketAdapter(settings)
    email_client = EmailAdapter(settings)
    warnings: list[str] = []

    decision = service.process_message(payload)

    ticket_result = ticket_client.update_ticket(
        ticket_id=payload.ticket_id,
        body=decision.drafted_response,
        private_note=decision.requires_human_handoff,
        subject=payload.subject,
        requester_email=payload.customer_email,
    )
    if not ticket_result.get("updated", False):
        reason = ticket_result.get("reason", "unknown")
        status_code = ticket_result.get("status_code")
        details = str(ticket_result.get("details", "")).replace("\n", " ").strip()
        details = details[:120] if details else ""
        if status_code is not None:
            message = f"ticket_update_failed:{reason}:http_{status_code}"
            if details:
                message = f"{message}:{details}"
            warnings.append(message)
        else:
            message = f"ticket_update_failed:{reason}"
            if details:
                message = f"{message}:{details}"
            warnings.append(message)

    if payload.send_email and payload.customer_email:
        email_result = email_client.send_email(
            to_email=payload.customer_email,
            subject=payload.subject or "Support update",
            body=decision.drafted_response,
        )
        if not email_result.get("sent", False):
            warnings.append(f"email_send_failed:{email_result.get('reason', 'unknown')}")

    final_status = "processed_with_warnings" if warnings else "processed"

    persisted = save_ticket_event(
        ticket_id=payload.ticket_id,
        customer_email=payload.customer_email or "",
        subject=payload.subject or "",
        message=payload.message,
        status=final_status,
        intent=decision.intent,
        confidence=decision.confidence,
        requires_handoff=decision.requires_human_handoff,
        warnings=warnings,
        drafted_response=decision.drafted_response,
        cited_kb_files=decision.cited_kb_files,
    )
    if not persisted:
        warnings.append("database_write_failed")
        final_status = "processed_with_warnings"

    return ProcessMessageResponse(
        status=final_status,
        ticket_id=payload.ticket_id,
        decision=decision,
        warnings=warnings,
    )


@router.get("/ticket-analytics", response_model=TicketAnalyticsResponse)
def ticket_analytics() -> TicketAnalyticsResponse:
    return load_ticket_analytics_from_db()


@router.get("/tickets/history", response_model=TicketHistoryResponse)
def tickets_history(limit: int = 50) -> TicketHistoryResponse:
    safe_limit = max(1, min(limit, 500))
    return list_ticket_history(limit=safe_limit)
