# Flowdesk — AI-assisted business workflows

Two local portfolio demos share one frontend: lead qualification and appointment booking. This is an AI-assisted personal project, not a client deployment. Use synthetic inquiries and contact details.

## Development approach

This is a learning project built with substantial AI assistance. Codex generated most of the application code and tests and ran the automated and live-service verification. My contribution so far includes setting up the external service accounts, credentials and integration configuration. The next learning steps are guided code walkthroughs and independent changes to the application. This repository demonstrates a working integration; it is not a claim of independently authored implementation or a production client deployment.

## Open locally

Double-click `Start.cmd`, then open http://127.0.0.1:18766. Docker Desktop and the existing `portfolio-n8n` container must be running. The n8n editor is http://localhost:5679. Both services are local-only; the app is not deployed.

Alternatively, in this folder:

    uv sync
    uv run uvicorn main:app --host 127.0.0.1 --port 18766

## What each layer does

| Layer | Responsibility |
| --- | --- |
| Frontend | Inquiry consent, booking forms, results, verification and cancellation |
| FastAPI + Pydantic | Validate input and structured model output; decide whether an action can proceed |
| SQLite | Persist leads, cached analysis, CRM references and pending/confirmed booking reservations |
| n8n | Use its stored credentials to call Gemini, SeaTable and Google Calendar |
| Gemini | Classify an inquiry, summarize it and list missing information; it cannot confirm appointments or prices |
| SeaTable | Store qualified inquiries under a stable Lead ID |
| Google Calendar | Provide live availability and authoritative event creation, readback and cancellation |

## Lead flow

`POST /api/leads` requires explicit consent and a valid contact. The lead is saved before calling external services. Gemini's response must validate against the category/summary/missing-information schema. The analysis is cached locally for retries. A protected n8n workflow checks the CRM schema, searches the exact Lead ID, then reuses an existing row or creates one. The app reports CRM completion only after receiving a row reference. Identical contact plus inquiry reuses the lead. Retrying the same inquiry retries incomplete delivery.

SeaTable base: the account selected in n8n. Table: `Table1`. Required columns, all **Text**: `Name`, `Lead ID`, `Contact`, `Inquiry`, `Category`, `Summary`, `Status`.

## Booking flow

`GET /api/availability` checks a future Dubai slot. `POST /api/bookings` first reserves it locally, checks Calendar free/busy, creates an event with a deterministic ID, and reads it back before returning confirmation. A lost creation response is resolved by readback. An uncertain outcome retains a pending reservation and a reference. Reposting the same request can recover it without creating a second event. `POST /api/bookings/{id}/verify` checks it explicitly. `DELETE /api/bookings/{id}` cancels the event and then releases the local reservation.

Appointments are one hour, 10:00–15:00, Asia/Dubai UTC+4. This demo uses the separate **Portfolio Demo** Google calendar. Event descriptions contain a synthetic reference; no invitations or customer messages are sent.

## Local configuration and portability

The six active service workflows are exported in `live-workflows.json`; individual exports are `portfolio-ai.json`, `portfolio-crm.json`, and `portfolio-calendar-*.json`. These contain credential **references**, not credential secrets. For another n8n instance, import inactive workflows and select your own credentials before activation. Update the calendar ID in `integrations.py` and `build_integrations.py`, then regenerate exports. The Gemini model is configured in `build_integrations.py`; provider availability and free-tier quotas can change.

The webhook triggers require the `Portfolio backend access` Header Auth credential with header name `X-Portfolio-Key`. Its value must match `N8N_CONNECTOR_SECRET` in local `.env`. Never put that value in the frontend or share `.env`. Provider tokens remain in n8n's credential store. The supplied ZIP excludes credentials, `.env`, databases, caches and the virtual environment. You can alternatively supply `N8N_CONNECTOR_SECRET` as an environment variable and override `N8N_WEBHOOK_BASE_URL`. The backend Dockerfile is supplied as an unverified starting point; only the local Python backend and n8n Docker runtime are tested.

A fresh machine needs its own `.env`, credentials, Docker/n8n setup and SeaTable columns. Existing old n8n containers and volumes were left intact. The new instance uses `portfolio_n8n_data`. The earlier mock lead/booking workflows are inactive. Legacy mock HTTP endpoints remain for isolated regression tests; they are not used by the frontend.

## Validation

    uv run pytest -q test_workflows.py test_integrations.py

Tests isolate SQLite and mock external services: consent, duplicate handling, contact/time validation, concurrent local requests, structured-output rejection, busy slots, verification and uncertain-outcome recovery.

To deliberately call the real services:

    uv run python verify_live.py

This creates one clearly synthetic CRM lead, checks retry behavior, creates and verifies an appointment eight days ahead, and cancels that appointment. It leaves the synthetic CRM lead for demonstration. A successful run writes `verification.json` with actual checks and timestamp. Do not present mocked tests as proof of a live service connection.

## Practical limits

This is a local single-process demo, not production infrastructure. No app login, multi-tenant permissions, distributed locking, cross-channel messaging, queue worker, scheduled follow-up, automatic human assignment, RAG, LangChain or LangGraph is implemented. Local slot uniqueness plus Calendar checks reduce conflicts; Calendar free/busy and event creation are separate operations, so another calendar writer can race them. Pending outcomes require retry/review. AI classification is fallible and does not authorize external actions. No measured business impact is claimed.

## Portfolio wording after reviewing and understanding the implementation

- Developed an AI-assisted lead qualification demo using FastAPI, Gemini and n8n, with schema-validated extraction, explicit consent and retryable SeaTable delivery using stable lead references.
- Developed a Google Calendar appointment demo with live availability checks, persistent slot reservations, deterministic event IDs, confirmation readback and cancellation.

Describe these as two workflows in one application. Add RAG or agent frameworks only after implementing and verifying a feature that needs them.
