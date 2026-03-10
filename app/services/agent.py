from app.core.config import Settings
from app.models.schemas import AgentDecision, InboundMessage
from app.services.retriever import KBRetriever


class SupportAgentService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.retriever = KBRetriever(settings.kb_dir)

    def _estimate_confidence(self, kb_hits: int, intent_match_strength: int) -> float:
        """Calculate confidence based on KB hits and intent keyword matches."""
        kb_score = 0.0
        if kb_hits >= 3:
            kb_score = 0.5
        elif kb_hits == 2:
            kb_score = 0.35
        elif kb_hits == 1:
            kb_score = 0.2

        intent_score = min(intent_match_strength * 0.15, 0.5)
        return min(kb_score + intent_score, 1.0)

    def _infer_intent(self, message_text: str) -> tuple[str, int]:
        """Return intent and match strength (number of matching keywords)."""
        text = message_text.lower()
        match_strength = 0

        # Billing patterns
        billing_keywords = ["charged", "charge", "double", "twice", "billing", "invoice", "bill", "payment"]
        if any(kw in text for kw in billing_keywords):
            match_strength = sum(1 for kw in billing_keywords if kw in text)
            return "billing_question", match_strength

        # Refund patterns
        refund_keywords = ["refund", "money back", "return"]
        if any(kw in text for kw in refund_keywords):
            match_strength = sum(1 for kw in refund_keywords if kw in text)
            return "refund_request", match_strength

        # Cancel patterns
        cancel_keywords = ["cancel", "stop", "remove"]
        if any(kw in text for kw in cancel_keywords):
            match_strength = sum(1 for kw in cancel_keywords if kw in text)
            return "cancel_order", match_strength

        # Tracking patterns
        tracking_keywords = ["track", "where", "delivery", "shipping", "ship", "status"]
        if any(kw in text for kw in tracking_keywords):
            match_strength = sum(1 for kw in tracking_keywords if kw in text)
            return "order_tracking", match_strength

        return "general_support", 0

    def _intent_steps(self, intent: str) -> list[str]:
        steps_by_intent = {
            "order_tracking": [
                "Please check your tracking link in the order confirmation email.",
                "If tracking has not updated in 48 hours, reply with your order number so we can investigate with the carrier.",
                "If the package is confirmed lost, we can help arrange a replacement or refund.",
            ],
            "refund_request": [
                "Reply with your order number so we can review eligibility and timeline.",
                "Share the reason for the refund request so we can process it correctly.",
                "Once approved, we will confirm the refund method and expected processing time.",
            ],
            "cancel_order": [
                "Reply with your order number so we can check cancellation eligibility.",
                "If the order has not shipped, we can cancel it immediately.",
                "If already shipped, we will guide you through return and refund steps.",
            ],
            "billing_question": [
                "Reply with your order number or invoice ID so we can locate the charge.",
                "Share the billed amount and date so we can verify what happened.",
                "If there is an error, we will correct it and confirm next steps right away.",
            ],
            "general_support": [
                "Reply with your order number and any relevant screenshots.",
                "Include key dates and details so we can investigate quickly.",
                "We will review and respond with a clear resolution plan.",
            ],
        }
        return steps_by_intent[intent]

    def _sanitize_customer_reply(self, text: str) -> str:
        """Defensive cleanup to ensure internal prompt text never reaches customers."""
        blocked_markers = (
            "human:",
            "system:",
            "knowledge context",
            "draft a concise",
            "user message:",
        )
        safe_lines = [
            line for line in text.splitlines() if not any(marker in line.lower() for marker in blocked_markers)
        ]
        return "\n".join(safe_lines).strip()

    def _build_customer_reply(self, user_message: str, intent: str) -> str:
        intent_openers = {
            "order_tracking": "I understand your shipment may be delayed.",
            "refund_request": "I understand you are requesting a refund.",
            "cancel_order": "I understand you would like to cancel your order.",
            "billing_question": "I understand you have a billing concern.",
            "general_support": "I understand you need help with your request.",
        }

        opener = intent_openers.get(intent, intent_openers["general_support"])
        steps = self._intent_steps(intent)
        steps_text = "\n".join([f"{idx}. {step}" for idx, step in enumerate(steps, start=1)])

        # Keep response concise and customer-facing only.
        reply = (
            "Hello,\n\n"
            "Thanks for contacting support.\n\n"
            f"{opener}\n"
            "Here are the next steps:\n\n"
            f"{steps_text}\n\n"
            "We are here to help and will resolve this as quickly as possible.\n\n"
            "Best regards,\n"
            "Support Team"
        )
        return self._sanitize_customer_reply(reply)

    def process_message(self, inbound: InboundMessage) -> AgentDecision:
        kb_docs = self.retriever.retrieve(inbound.message, top_k=3)

        intent, match_strength = self._infer_intent(inbound.message)
        confidence = self._estimate_confidence(len(kb_docs), match_strength)
        requires_handoff = confidence < 0.7
        drafted = self._build_customer_reply(inbound.message, intent)

        return AgentDecision(
            intent=intent,
            confidence=confidence,
            requires_human_handoff=requires_handoff,
            drafted_response=drafted,
            cited_kb_files=[name for name, _ in kb_docs],
        )
