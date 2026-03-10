from pathlib import Path

from app.core.config import Settings
from app.models.schemas import InboundMessage
from app.services.agent import SupportAgentService


def test_process_message_response_is_customer_facing(tmp_path: Path) -> None:
    kb_file = tmp_path / "cancel_order.md"
    kb_file.write_text(
        "# Intent: cancel_order\nExample response content for internal retrieval.",
        encoding="utf-8",
    )

    settings = Settings(kb_dir=str(tmp_path))
    service = SupportAgentService(settings)

    inbound = InboundMessage(
        ticket_id="TCK-5001",
        customer_email="user@example.com",
        subject="Delayed shipment",
        message="I need help with my delayed shipment.",
    )
    decision = service.process_message(inbound)

    assert "Thanks for contacting support." in decision.drafted_response
    assert "Here are the next steps:" in decision.drafted_response

    # Ensure internal prompt plumbing text never leaks to user-facing output.
    assert "Human:" not in decision.drafted_response
    assert "System:" not in decision.drafted_response
    assert "Knowledge context" not in decision.drafted_response
    assert "User message:" not in decision.drafted_response
    assert "Draft a concise" not in decision.drafted_response
