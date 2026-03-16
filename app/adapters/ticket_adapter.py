import base64
import logging
import re

import httpx
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from app.core.config import Settings

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Retry policy: up to 3 attempts on transient network/timeout failures.
_RETRY_TRANSPORT = dict(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4.0),
    retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)


class TicketAdapter:
    """Zendesk ticket adapter.

    Returns status dictionaries instead of raising so API handlers can continue and
    surface integration warnings in responses.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _is_configured(self) -> bool:
        return bool(
            self.settings.zendesk_base_url
            and self.settings.zendesk_email
            and self.settings.zendesk_api_token
        )

    def _auth_header(self) -> str:
        raw = f"{self.settings.zendesk_email}/token:{self.settings.zendesk_api_token}"
        token = base64.b64encode(raw.encode("ascii")).decode("ascii")
        return f"Basic {token}"

    def _search_ticket_id(self, client: httpx.Client, raw_ticket_id: str) -> str | None:
        base_url = self.settings.zendesk_base_url.rstrip("/")
        headers = {"Authorization": self._auth_header()}

        queries = [
            f"type:ticket external_id:{raw_ticket_id}",
            f"type:ticket {raw_ticket_id}",
        ]

        for query in queries:
            try:
                response = client.get(
                    f"{base_url}/api/v2/search.json",
                    params={"query": query},
                    headers=headers,
                )
                if response.status_code >= 400:
                    continue

                payload = response.json()
                for result in payload.get("results", []):
                    ticket_id = result.get("id")
                    if ticket_id is not None:
                        return str(ticket_id)
            except (httpx.HTTPError, ValueError):
                continue

        return None

    def _create_ticket(
        self,
        client: httpx.Client,
        external_ticket_id: str,
        subject: str,
        body: str,
        requester_email: str | None,
    ) -> dict:
        base_url = self.settings.zendesk_base_url.rstrip("/")
        url = f"{base_url}/api/v2/tickets.json"
        headers = {
            "Authorization": self._auth_header(),
            "Content-Type": "application/json",
        }

        payload: dict = {
            "ticket": {
                "subject": subject,
                "comment": {
                    "body": body,
                    "public": True,
                },
                "external_id": external_ticket_id,
            }
        }
        has_requester = False
        if requester_email and _EMAIL_RE.match(requester_email.strip()):
            email = requester_email.strip()
            name = email.split("@")[0].replace(".", " ").replace("_", " ").title()
            payload["ticket"]["requester"] = {"email": email, "name": name}
            has_requester = True

        response = client.post(url, json=payload, headers=headers)

        # If Zendesk rejected the requester (422), retry without it so the
        # ticket is created under the authenticated agent instead.
        if response.status_code == 422 and has_requester:
            payload["ticket"].pop("requester", None)
            response = client.post(url, json=payload, headers=headers)

        if response.status_code >= 400:
            return {
                "updated": False,
                "ticket_id": external_ticket_id,
                "reason": "zendesk_create_http_error",
                "status_code": response.status_code,
                "details": response.text[:500],
            }

        ticket = response.json().get("ticket", {})
        return {
            "updated": True,
            "ticket_id": external_ticket_id,
            "created": True,
            "resolved_ticket_id": str(ticket.get("id")) if ticket.get("id") is not None else None,
            "status_code": response.status_code,
        }

    def update_ticket(
        self,
        ticket_id: str,
        body: str,
        private_note: bool = False,
        subject: str | None = None,
        requester_email: str | None = None,
    ) -> dict:
        if not self._is_configured():
            return {
                "updated": False,
                "ticket_id": ticket_id,
                "reason": "zendesk_not_configured",
            }

        payload = {
            "ticket": {
                "comment": {
                    "body": body,
                    "public": not private_note,
                }
            }
        }

        try:
            for attempt in Retrying(**_RETRY_TRANSPORT):
                with attempt:
                    with httpx.Client(timeout=20.0) as client:
                        resolved_ticket_id = ticket_id
                        if not resolved_ticket_id.isdigit():
                            resolved_ticket_id = self._search_ticket_id(client, ticket_id)
                            if not resolved_ticket_id:
                                fallback_subject = subject or f"Support request {ticket_id}"
                                return self._create_ticket(
                                    client=client,
                                    external_ticket_id=ticket_id,
                                    subject=fallback_subject,
                                    body=body,
                                    requester_email=requester_email,
                                )

                        base_url = self.settings.zendesk_base_url.rstrip("/")
                        url = f"{base_url}/api/v2/tickets/{resolved_ticket_id}.json"
                        headers = {
                            "Authorization": self._auth_header(),
                            "Content-Type": "application/json",
                        }
                        response = client.put(url, json=payload, headers=headers)

                        if response.status_code == 404:
                            fallback_subject = subject or f"Support request {ticket_id}"
                            return self._create_ticket(
                                client=client,
                                external_ticket_id=ticket_id,
                                subject=fallback_subject,
                                body=body,
                                requester_email=requester_email,
                            )
        except Exception as exc:
            return {
                "updated": False,
                "ticket_id": ticket_id,
                "reason": f"zendesk_request_error:{exc}",
            }

        if response.status_code >= 400:
            return {
                "updated": False,
                "ticket_id": ticket_id,
                "reason": "zendesk_http_error",
                "status_code": response.status_code,
                "details": response.text[:500],
            }

        return {
            "updated": True,
            "ticket_id": ticket_id,
            "resolved_ticket_id": resolved_ticket_id,
            "private_note": private_note,
            "status_code": response.status_code,
        }
