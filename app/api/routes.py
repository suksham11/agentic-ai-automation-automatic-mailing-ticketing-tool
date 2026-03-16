import logging
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import text

from app.adapters.email_adapter import EmailAdapter
from app.adapters.ticket_adapter import TicketAdapter
from app.core.config import Settings, get_settings
from app.models.schemas import (
    HealthResponse,
    InboundMessage,
    ProcessMessageResponse,
    TicketAnalyticsResponse,
    TicketHistoryResponse,
)
from app.services.history import load_ticket_analytics_from_db, list_ticket_history, save_ticket_event
from app.services.agent import SupportAgentService
from app.services.persistence import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["support-agent"])


@router.get("/health", response_model=HealthResponse)
async def health(request: Request, settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Liveness + readiness probe.

    Checks database connectivity and AI provider configuration, then returns
    the aggregate health status and application uptime.
    """
    # --- Database check ---
    db_ok = False
    try:
        with get_session() as session:
            session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        logger.warning("health_check_db_failed")

    # --- AI service check (configuration presence, not a live probe) ---
    ai_ok = bool(settings.openai_api_key) if settings.model_provider == "openai" else True

    # --- Uptime ---
    startup_time: float = getattr(request.app.state, "startup_time", time.time())
    uptime_seconds = round(time.time() - startup_time, 1)

    status = "ok" if db_ok else "degraded"
    return HealthResponse(
        status=status,
        uptime_seconds=uptime_seconds,
        database=db_ok,
        ai_service=ai_ok,
        version="1.0.0",
    )


@router.post("/process-message", response_model=ProcessMessageResponse)
def process_message(
    payload: InboundMessage,
    background_tasks: BackgroundTasks,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> ProcessMessageResponse:
    req_id: str | None = getattr(request.state, "request_id", None)
    service = SupportAgentService(settings)
    ticket_client = TicketAdapter(settings)
    email_client = EmailAdapter(settings)
    warnings: list[str] = []

    logger.info(
        "processing_message",
        extra={"ticket_id": payload.ticket_id, "intent_hint": None},
    )

    try:
        decision = service.process_message(payload)
    except Exception as exc:
        logger.exception("agent_service_failed", extra={"ticket_id": payload.ticket_id})
        raise HTTPException(status_code=500, detail="Internal processing error") from exc

    logger.info(
        "agent_decision",
        extra={
            "ticket_id": payload.ticket_id,
            "intent": decision.intent,
            "confidence": decision.confidence,
            "requires_handoff": decision.requires_human_handoff,
        },
    )

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

    # Persist the ticket event asynchronously so it does not block the response.
    background_tasks.add_task(
        save_ticket_event,
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

    return ProcessMessageResponse(
        status=final_status,
        ticket_id=payload.ticket_id,
        decision=decision,
        warnings=warnings,
        request_id=req_id,
    )


@router.get("/ticket-analytics", response_model=TicketAnalyticsResponse)
def ticket_analytics() -> TicketAnalyticsResponse:
    try:
        return load_ticket_analytics_from_db()
    except Exception as exc:
        logger.exception("analytics_load_failed")
        raise HTTPException(status_code=500, detail="Failed to load analytics") from exc


@router.get("/tickets/history", response_model=TicketHistoryResponse)
def tickets_history(limit: int = 50) -> TicketHistoryResponse:
    safe_limit = max(1, min(limit, 500))
    try:
        return list_ticket_history(limit=safe_limit)
    except Exception as exc:
        logger.exception("history_load_failed")
        raise HTTPException(status_code=500, detail="Failed to load history") from exc
