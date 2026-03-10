---
description: "Design and implement a customer support automation AI agent with FastAPI, LangChain, PostgreSQL, Redis, and Docker"
name: "Customer Support Automation Agent"
argument-hint: "Provide ticketing system, email API, KB source, SLA targets, and compliance constraints"
agent: "agent"
---

Build a production-ready customer support automation agent for the following workflow:

Customer message
-> AI agent analyzes message
-> Retrieve knowledge base context
-> Generate response
-> Send email or ticket update

Single default scenario to use:

- Ticket system: Zendesk
- Email API: Gmail API
- Knowledge base: documents indexed from a local `data/kb/` folder
- Compliance baseline: SOC2-style auditability

Default implementation stack (use unless user overrides):

- Backend: FastAPI + LangChain
- Model providers: OpenAI or Llama or Claude (design for provider abstraction)
- Data: PostgreSQL + Redis
- Integrations: Email API, ticket system API, document search
- Deployment: Docker and docker-compose

If no company data is available, bootstrap with public Hugging Face data:

- Primary dataset: `bitext/Bitext-customer-support-llm-chatbot-training-dataset`
- Use dataset columns (`instruction`, `intent`, `response`) to seed:
  - message intent classifier examples
  - response style templates
  - synthetic ticket threads for testing
- Create a small local KB by converting a subset into markdown docs in `data/kb/`.
- Clearly mark synthetic/public data versus real production data in outputs.

Required execution steps:

1. Clarify assumptions from missing details before solutioning.
2. Design the architecture for message intake, classification, retrieval, response generation, and outbound update.
3. Propose the MVP scope with exact in/out boundaries.
4. Produce implementation assets:

- Recommended folder structure
- Core Python modules/classes
- FastAPI endpoints and request/response schemas
- LangChain chain/agent wiring plan
- Adapter interfaces for email API, ticket API, and document search
- Database schema outline for tickets, conversations, messages, actions, and audit logs
- Redis usage plan (cache, rate limiting, queue/state)

5. Provide Docker deliverables:

- `Dockerfile` strategy
- `docker-compose.yml` services (api, postgres, redis, optional worker)
- Environment variable contract
- Local run and health-check commands

6. Define reliability and safety controls:

- Confidence threshold and fallback to human handoff
- PII redaction and audit logging
- Retry, idempotency, and dead-letter strategy for failed updates

7. Define testing and rollout:

- Unit, integration, and prompt regression tests
- KPI baseline and target metrics (first response time, resolution rate, deflection)
- Phased rollout (shadow mode -> pilot -> production)

8. Include a data bootstrapping section:

- How to ingest Hugging Face starter data
- How to transform it into KB chunks + evaluation set
- What minimum real company data to collect in week 1 to replace synthetic data

Output format:

- Section 1: "MVP Recommendation"
- Section 2: "System Architecture"
- Section 3: "API and Data Design"
- Section 4: "Docker Deployment Plan"
- Section 5: "Implementation Roadmap (30/60/90 days)"
- Section 6: "Risk Controls and Human Handoff"
- Section 7: "Testing and Success Metrics"
- Section 8: "Data Bootstrap Plan (Hugging Face -> Production Data)"

Constraints:

- Keep guidance practical for small to mid-sized teams.
- Prefer explicit tradeoffs over generic best practices.
- If details are uncertain, list assumptions first and proceed.
