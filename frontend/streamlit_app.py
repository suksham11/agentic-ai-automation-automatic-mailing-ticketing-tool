import csv
import io
import os
import re
from typing import Any

import httpx
import streamlit as st

API_PATH = "/v1/process-message"
ANALYTICS_PATH = "/v1/ticket-analytics"
HISTORY_PATH = "/v1/tickets/history"
MAX_BATCH_ROWS = 50
MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_BATCH_ROWS = 200

TICKET_ID_ALIASES = ["ticket_id", "ticketid", "id", "record_id", "case_id", "order_id"]
CUSTOMER_EMAIL_ALIASES = ["customer_email", "email", "customeremail", "user_email"]
SUBJECT_ALIASES = ["subject", "title", "topic"]
MESSAGE_ALIASES = [
    "message",
    "description",
    "details",
    "issue",
    "query",
    "comment",
    "comments",
    "note",
    "item_type",
    "sales_channel",
]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def process_ticket(api_base_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{api_base_url.rstrip('/')}{API_PATH}"
    try:
        response = httpx.post(url, json=payload, timeout=60.0)
    except Exception as exc:
        return {
            "ok": False,
            "ticket_id": payload.get("ticket_id", ""),
            "status": "request_error",
            "warnings": [str(exc)],
        }

    if response.status_code >= 400:
        return {
            "ok": False,
            "ticket_id": payload.get("ticket_id", ""),
            "status": f"http_{response.status_code}",
            "warnings": [response.text[:400]],
        }

    data = response.json()
    return {
        "ok": True,
        "ticket_id": data.get("ticket_id", payload.get("ticket_id", "")),
        "status": data.get("status", "unknown"),
        "warnings": data.get("warnings", []),
        "intent": data.get("decision", {}).get("intent", ""),
        "confidence": data.get("decision", {}).get("confidence", 0),
        "subject": payload.get("subject", "Support update"),
        "full_response": data.get("decision", {}).get("drafted_response", ""),
        "response_preview": data.get("decision", {}).get("drafted_response", "")[:220],
    }


def fetch_analytics(api_base_url: str) -> dict[str, Any]:
    url = f"{api_base_url.rstrip('/')}{ANALYTICS_PATH}"
    try:
        response = httpx.get(url, timeout=30.0)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    if response.status_code >= 400:
        return {"ok": False, "error": response.text[:400]}

    data = response.json()
    data["ok"] = True
    return data


def fetch_history(api_base_url: str, limit: int = 100) -> dict[str, Any]:
    url = f"{api_base_url.rstrip('/')}{HISTORY_PATH}"
    try:
        response = httpx.get(url, params={"limit": limit}, timeout=30.0)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    if response.status_code >= 400:
        return {"ok": False, "error": response.text[:400]}

    data = response.json()
    return {"ok": True, "items": data.get("items", [])}


def check_api_health(api_base_url: str) -> tuple[bool, str]:
    try:
        response = httpx.get(f"{api_base_url.rstrip('/')}/v1/health", timeout=5.0)
    except Exception as exc:
        return False, str(exc)
    if response.status_code != 200:
        return False, f"HTTP {response.status_code}"
    return True, "ok"


def _pick_value(row: dict[str, str], aliases: list[str]) -> str:
    for key in aliases:
        value = (row.get(key) or "").strip()
        if value:
            return value
    return ""


def _normalize_header(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def _build_fallback_message(row: dict[str, str]) -> str:
    # If no dedicated message column exists, summarize key fields into one message.
    preferred_keys = [
        "region",
        "country",
        "item_type",
        "sales_channel",
        "order_priority",
        "units_sold",
        "total_revenue",
        "total_cost",
        "total_profit",
    ]
    parts: list[str] = []
    for key in preferred_keys:
        value = (row.get(key) or "").strip()
        if value:
            parts.append(f"{key.replace('_', ' ').title()}: {value}")
    return " | ".join(parts)


def parse_csv(file_bytes: bytes) -> tuple[list[dict[str, str]], list[str]]:
    text = file_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    raw_headers = reader.fieldnames or []
    headers = [_normalize_header(header) for header in raw_headers if header]

    rows = []
    for raw_row in reader:
        row = {_normalize_header(k or ""): (v or "") for k, v in raw_row.items()}
        message = _pick_value(row, MESSAGE_ALIASES)
        if not message:
            message = _build_fallback_message(row)

        rows.append(
            {
                "ticket_id": _pick_value(row, TICKET_ID_ALIASES),
                "customer_email": _pick_value(row, CUSTOMER_EMAIL_ALIASES),
                "subject": _pick_value(row, SUBJECT_ALIASES),
                "message": message,
            }
        )
    return rows, headers


def parse_csv_text(csv_text: str) -> tuple[list[dict[str, str]], list[str]]:
    return parse_csv(csv_text.encode("utf-8"))


def is_valid_row(row: dict[str, str]) -> bool:
    return bool(row.get("ticket_id") and row.get("message"))


def is_valid_email(email: str) -> bool:
    if not email:
        return True
    return bool(EMAIL_RE.match(email.strip()))


def main() -> None:
    st.set_page_config(page_title="Support Control Desk", page_icon="✦", layout="wide")

    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');

        html, body, [class*="css"] {
            font-family: 'Space Grotesk', sans-serif;
            color: #1a1a2e !important;
        }
        .stApp {
            background: radial-gradient(circle at 8% 5%, #fff4d6 0%, #f6f9ff 40%, #e8f3ff 100%);
        }
        h1, h2, h3 {
            letter-spacing: -0.02em;
            color: #1a1a2e !important;
        }
        code, .stCodeBlock {
            font-family: 'IBM Plex Mono', monospace;
        }
        .hero {
            background: linear-gradient(120deg, #11253f, #1b5d9b);
            color: #ffffff !important;
            padding: 1rem 1.2rem;
            border-radius: 14px;
            margin-bottom: 1rem;
        }
        .hero h2, .hero p {
            color: #ffffff !important;
        }
        /* Hide Streamlit chrome that can show account/token/fork controls. */
        #MainMenu,
        header[data-testid="stHeader"],
        div[data-testid="stToolbar"],
        div[data-testid="stDecoration"],
        div[data-testid="stStatusWidget"],
        div[data-testid="stHeaderActionElements"] {
            display: none !important;
            visibility: hidden !important;
            height: 0 !important;
        }
        /* Hide Streamlit footer branding. */
        footer {
            display: none !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="hero">
          <h2>Support Control Desk</h2>
          <p>Process customer tickets through AI, Zendesk, and Gmail in one place.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    secret_api_base_url = st.secrets.get("STREAMLIT_API_BASE_URL", "") if hasattr(st, "secrets") else ""
    default_api_base_url = secret_api_base_url or os.getenv("STREAMLIT_API_BASE_URL", "http://127.0.0.1:8000")
    api_base_url = st.text_input("FastAPI Base URL", value=default_api_base_url)
    healthy, health_message = check_api_health(api_base_url)
    if healthy:
        st.success(f"Connected to API: {api_base_url}")
    else:
        st.error(f"API not reachable at {api_base_url}: {health_message}")

    tab_single, tab_batch, tab_analytics, tab_history = st.tabs([
        "Single Ticket",
        "Batch Tickets (CSV)",
        "Ticket Analytics",
        "Ticket History",
    ])

    with tab_single:
        with st.form("single_ticket_form"):
            col1, col2 = st.columns(2)
            with col1:
                ticket_id = st.text_input("Ticket ID", value="TCK-1001")
                customer_email = st.text_input("Customer Email", value="user@example.com")
            with col2:
                subject = st.text_input("Subject", value="Support update")
                message = st.text_area("Message", value="I need help with my delayed shipment.", height=160)
                send_email_single = st.checkbox("Send customer email", value=True)
            submit_single = st.form_submit_button("Process Ticket")

        if submit_single:
            payload = {
                "ticket_id": ticket_id.strip(),
                "customer_email": customer_email.strip(),
                "subject": subject.strip(),
                "message": message.strip(),
                "send_email": send_email_single,
            }
            if not payload["ticket_id"] or not payload["message"]:
                st.error("`ticket_id` and `message` are required.")
            elif not is_valid_email(payload["customer_email"]):
                st.error("`customer_email` must be a valid email (example: name@example.com).")
            else:
                with st.spinner("Processing..."):
                    result = process_ticket(api_base_url, payload)
                if result["ok"]:
                    st.success("Processed successfully")
                else:
                    st.error("Processing failed")

                rcol1, rcol2 = st.columns([1, 1])
                with rcol1:
                    st.write("Intent:", result.get("intent", ""))
                    st.write("Confidence:", result.get("confidence", 0))
                    if result.get("warnings"):
                        st.warning(" | ".join(result["warnings"]))
                with rcol2:
                    st.subheader("Email Preview")
                    st.write("Subject:", result.get("subject", "Support update"))
                    st.text_area(
                        "Body",
                        value=result.get("full_response", ""),
                        height=260,
                        key="email_preview_body",
                    )
                with st.expander("Raw API output"):
                    st.json(result)

    with tab_batch:
        st.caption("CSV columns: `ticket_id,customer_email,subject,message`")
        st.info("If browser upload fails, paste CSV content below and process directly.")
        pasted_csv = st.text_area("Paste CSV content (fallback)", height=140)
        uploaded = st.file_uploader("Upload CSV", type=["csv"])

        rows: list[dict[str, str]] = []
        headers: list[str] = []

        if uploaded is not None:
            raw_bytes = uploaded.getvalue()
            if len(raw_bytes) > MAX_CSV_BYTES:
                st.error(
                    f"CSV too large ({len(raw_bytes)} bytes). Limit is {MAX_CSV_BYTES} bytes to prevent accidental bulk spam."
                )
                st.stop()

            rows, headers = parse_csv(raw_bytes)
        elif pasted_csv.strip():
            rows, headers = parse_csv_text(pasted_csv)

        if rows:
            valid_rows = [row for row in rows if is_valid_row(row)]
            if rows and not valid_rows:
                st.error(
                    "No valid rows found. Include columns for ticket ID and message. "
                    f"Detected columns: {', '.join(headers) if headers else 'none'}"
                )
            if len(valid_rows) > MAX_BATCH_ROWS:
                st.warning(
                    f"Limiting processing to first {MAX_BATCH_ROWS} valid rows (found {len(valid_rows)})."
                )
                valid_rows = valid_rows[:MAX_BATCH_ROWS]

            st.write(f"Loaded {len(rows)} rows, {len(valid_rows)} valid rows.")
            st.dataframe(valid_rows, use_container_width=True, hide_index=True)
            st.info("Batch mode safety: outbound email is disabled by default for CSV processing.")

            if st.button("Process All Valid Rows"):
                if not valid_rows:
                    st.warning("No valid rows found. Ensure `ticket_id` and `message` are populated.")
                else:
                    progress = st.progress(0)
                    results: list[dict[str, Any]] = []
                    for idx, row in enumerate(valid_rows, start=1):
                        row["send_email"] = False
                        results.append(process_ticket(api_base_url, row))
                        progress.progress(idx / len(valid_rows))

                    st.subheader("Batch Result")
                    st.dataframe(results, use_container_width=True, hide_index=True)
                    ok_count = sum(1 for item in results if item.get("ok"))
                    st.info(f"Success: {ok_count}/{len(results)}")

                    output = io.StringIO()
                    writer = csv.DictWriter(
                        output,
                        fieldnames=[
                            "ok",
                            "ticket_id",
                            "status",
                            "intent",
                            "confidence",
                            "warnings",
                            "response_preview",
                        ],
                    )
                    writer.writeheader()
                    for item in results:
                        writer.writerow(
                            {
                                "ok": item.get("ok"),
                                "ticket_id": item.get("ticket_id"),
                                "status": item.get("status"),
                                "intent": item.get("intent", ""),
                                "confidence": item.get("confidence", ""),
                                "warnings": " | ".join(item.get("warnings", [])),
                                "response_preview": item.get("response_preview", ""),
                            }
                        )

                    st.download_button(
                        "Download Batch Results",
                        data=output.getvalue().encode("utf-8"),
                        file_name="ticket_batch_results.csv",
                        mime="text/csv",
                    )

    with tab_analytics:
        st.caption("Live metrics from `/v1/ticket-analytics`")
        if st.button("Refresh Analytics"):
            st.rerun()

        analytics = fetch_analytics(api_base_url)
        if not analytics.get("ok"):
            st.error(f"Unable to fetch analytics: {analytics.get('error', 'unknown error')}")
        else:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Tickets", analytics.get("total_tickets", 0))
            c2.metric("Processed OK", analytics.get("processed_ok", 0))
            c3.metric("With Warnings", analytics.get("processed_with_warnings", 0))
            c4.metric("Handoff Required", analytics.get("handoff_required", 0))

            st.metric("Average Confidence", analytics.get("average_confidence", 0.0))

            st.subheader("Intent Breakdown")
            intents = analytics.get("intent_breakdown", [])
            if intents:
                st.dataframe(intents, use_container_width=True, hide_index=True)
            else:
                st.info("No intent data yet.")

            st.subheader("Top Warnings")
            warnings = analytics.get("top_warnings", [])
            if warnings:
                for warning in warnings:
                    st.write(f"- {warning}")
            else:
                st.success("No warnings recorded.")

    with tab_history:
        st.caption("Recent ticket processing events stored in PostgreSQL")
        history_limit = st.slider("Rows", min_value=10, max_value=200, value=50, step=10)
        if st.button("Refresh History"):
            st.rerun()

        history = fetch_history(api_base_url, limit=history_limit)
        if not history.get("ok"):
            st.error(f"Unable to fetch ticket history: {history.get('error', 'unknown error')}")
        else:
            items = history.get("items", [])
            if not items:
                st.info("No ticket history available yet.")
            else:
                st.dataframe(items, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
