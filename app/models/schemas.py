from pydantic import BaseModel, Field


class InboundMessage(BaseModel):
    ticket_id: str = Field(..., description="Ticket identifier from Zendesk or another system")
    customer_email: str | None = Field(default=None)
    subject: str | None = Field(default=None)
    message: str = Field(..., min_length=1)
    send_email: bool = Field(default=True, description="Whether to send outbound email for this request")


class AgentDecision(BaseModel):
    intent: str
    confidence: float
    requires_human_handoff: bool
    drafted_response: str
    cited_kb_files: list[str] = Field(default_factory=list)


class ProcessMessageResponse(BaseModel):
    status: str
    ticket_id: str
    decision: AgentDecision
    warnings: list[str] = Field(default_factory=list)


class IntentCount(BaseModel):
    intent: str
    count: int


class TicketAnalyticsResponse(BaseModel):
    total_tickets: int
    processed_ok: int
    processed_with_warnings: int
    handoff_required: int
    average_confidence: float
    intent_breakdown: list[IntentCount] = Field(default_factory=list)
    top_warnings: list[str] = Field(default_factory=list)


class TicketHistoryItem(BaseModel):
    created_at: str
    ticket_id: str
    customer_email: str
    subject: str
    status: str
    intent: str
    confidence: float
    requires_handoff: bool
    warnings: list[str] = Field(default_factory=list)
    drafted_response: str
    cited_kb_files: list[str] = Field(default_factory=list)


class TicketHistoryResponse(BaseModel):
    items: list[TicketHistoryItem] = Field(default_factory=list)
