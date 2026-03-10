import json
from collections import Counter
from pathlib import Path

from app.models.schemas import IntentCount, TicketAnalyticsResponse


def record_ticket_event(
    log_path: str,
    *,
    status: str,
    ticket_id: str,
    intent: str,
    confidence: float,
    requires_handoff: bool,
    warnings: list[str],
) -> None:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "status": status,
        "ticket_id": ticket_id,
        "intent": intent,
        "confidence": confidence,
        "requires_handoff": requires_handoff,
        "warnings": warnings,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def load_ticket_analytics(log_path: str) -> TicketAnalyticsResponse:
    path = Path(log_path)
    if not path.exists():
        return TicketAnalyticsResponse(
            total_tickets=0,
            processed_ok=0,
            processed_with_warnings=0,
            handoff_required=0,
            average_confidence=0.0,
            intent_breakdown=[],
            top_warnings=[],
        )

    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue

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
    processed_ok = sum(1 for row in rows if row.get("status") == "processed")
    processed_warn = sum(1 for row in rows if row.get("status") == "processed_with_warnings")
    handoff_required = sum(1 for row in rows if bool(row.get("requires_handoff")))

    conf_values = [float(row.get("confidence", 0.0)) for row in rows]
    avg_conf = round(sum(conf_values) / len(conf_values), 3) if conf_values else 0.0

    intent_counts = Counter(str(row.get("intent", "unknown")) for row in rows)
    warning_counts = Counter()
    for row in rows:
        for warning in row.get("warnings", []) or []:
            warning_counts[str(warning)] += 1

    return TicketAnalyticsResponse(
        total_tickets=total,
        processed_ok=processed_ok,
        processed_with_warnings=processed_warn,
        handoff_required=handoff_required,
        average_confidence=avg_conf,
        intent_breakdown=[
            IntentCount(intent=intent, count=count)
            for intent, count in intent_counts.most_common()
        ],
        top_warnings=[key for key, _ in warning_counts.most_common(5)],
    )
