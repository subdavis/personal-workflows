# Paperless ingestion

Two DBOS workflows mirror the `personal-workflows` Paperless jobs:

| Workflow | Purpose |
|----------|---------|
| `process_document` | Classify a document, merge tags, stamp `paperless-ai-processed`, optionally enqueue receipt extraction |
| `process_receipt` | Extract `dollar-amount` and `purchase-category` custom fields from purchase receipts |

## What each automation does

### `process_document`

Runs when a new document arrives (webhook), is picked up by the scheduled sweep, or is enqueued manually. It:

1. Skips documents that already have the `paperless-ai-processed` date field set.
2. Loads the document OCR text and the archive's existing tags, correspondents, and document types.
3. Asks the classifier agent for a title, tags, correspondent, and document type — choosing only from existing tags and types, but allowing a new correspondent when the sender is clearly identified.
4. Writes the results back to Paperless: always updates the title and merges new tags; fills correspondent and document type only when the document lacks them; stamps today's date in `paperless-ai-processed`.
5. If the result is a purchase receipt (type **Purchase Receipts** or tag **Receipts**), enqueues `process_receipt` as a separate durable job.

### `process_receipt`

Runs after `process_document` hands off a receipt, or when triggered directly via the receipt webhook. It:

1. Skips documents where both `dollar-amount` and `purchase-category` are already populated.
2. Loads the receipt OCR text and the allowed values for `purchase-category`.
3. Asks the receipt agent for the grand total paid and the best-matching spending category.
4. Writes the total as a monetary custom field (e.g. `USD42.17`) and the category as the matching select-option id.

### `paperless-scan`

Runs on the configured cron schedule (and via `populate_jobs`). It finds the newest documents missing the `paperless-ai-processed` marker and enqueues `process_document` for each, up to `PAPERLESS_SCAN_LIMIT`.

## Prerequisites

- `PAPERLESS_URL` must point at the Paperless **/api** root (for example `http://localhost:8000/api`).
- `PAPERLESS_TOKEN` is sent as `Authorization: Token …`.
- Custom fields:
  - `paperless-ai-processed` (`date`) — auto-created if missing
  - `dollar-amount` (`monetary`) — must already exist
  - `purchase-category` (`select`) — must already exist, with user-defined options

## Configuration

Set these in `.env` (see the repo root `.env.example`):

| Variable | Description |
|----------|-------------|
| `PAPERLESS_URL` | Paperless `/api` root URL |
| `PAPERLESS_TOKEN` | Paperless API token |
| `PAPERLESS_SCAN_CRON` | Cron expression for the catch-up sweep (UTC) |
| `PAPERLESS_SCAN_LIMIT` | Max documents to enqueue per sweep/backfill run |

## Triggers

| Entrypoint | Auth | Action |
|------------|------|--------|
| `POST /webhooks/paperless` | Bearer | Enqueue `process_document` for `documentId` or a document URL |
| `POST /webhooks/paperless/receipt` | Bearer | Enqueue `process_receipt` for a document |
| DBOS schedule `paperless-scan` | n/a | Sweep unprocessed documents (`PAPERLESS_SCAN_CRON`, `PAPERLESS_SCAN_LIMIT`) |
| `uv run populate_jobs --limit N` | n/a | One-shot backfill sweep |

Webhook body accepts `{"documentId": 123}` or `{"url": "https://…/documents/123/"}` (or `?url=`).

Receipt extraction runs when a document is typed **Purchase Receipts** or tagged **Receipts**.

## Local testing

Uses a local SQLite file for DBOS state — no Postgres install required. DBOS creates
`./workflow-explorer.sqlite` on first launch (gitignored).

### 1. Configure

From the repo root:

```bash
uv sync
cp .env.example .env
```

Minimum for a live run:

| Variable | Example |
|----------|---------|
| `DBOS_SYSTEM_DATABASE_URL` | `sqlite:///./workflow-explorer.sqlite` |
| `PAPERLESS_URL` | `http://localhost:8000/api` |
| `PAPERLESS_TOKEN` | your Paperless API token |
| `LLM_MODEL` | Pydantic AI model id, format `provider:model` (e.g. `openrouter:openai/gpt-5.6-terra`) |
| `OPENROUTER_API_KEY` or `ANTHROPIC_API_KEY` | API key matching your `LLM_MODEL` provider |
| `WEBHOOK_BEARER_TOKEN` | any secret string (default `change-me`) |

### 2. Start the app

```bash
uv run serve
```

Listens on `http://localhost:8080` by default. DBOS creates the SQLite file and registers
the `paperless-scan` cron schedule automatically.

### 3. Trigger a specific document ID

Replace `123` with the numeric id from your Paperless UI (document detail URL:
`/documents/123/`). Use the same bearer token as `WEBHOOK_BEARER_TOKEN`.

**Classify + tag (main pipeline):**

```bash
curl -sS -X POST "http://localhost:8080/webhooks/paperless" \
  -H "Authorization: Bearer change-me" \
  -H "Content-Type: application/json" \
  -d '{"documentId": 123}'
```

**Receipt extraction only:**

```bash
curl -sS -X POST "http://localhost:8080/webhooks/paperless/receipt" \
  -H "Authorization: Bearer change-me" \
  -H "Content-Type: application/json" \
  -d '{"documentId": 123}'
```

**Trigger via Paperless document URL** (body or query string):

```bash
curl -sS -X POST "http://localhost:8080/webhooks/paperless?url=http://localhost:8000/documents/123/" \
  -H "Authorization: Bearer change-me"
```

A `202` response with `{"accepted":true,"document_id":123}` means the job was enqueued.
With `serve`, the queue worker runs in-process; watch the terminal for workflow logs.

### 4. Verify it worked

- **Paperless UI**: document should get an updated title/tags and the `paperless-ai-processed`
  custom field stamped with today's date.
- **DBOS admin** (while `serve` is running): `http://localhost:3001` lists workflow status.
- **Re-run safety**: documents already stamped `paperless-ai-processed` are skipped by
  `process_document`.

### 5. Alternative: sweep instead of webhook

Enqueue every unprocessed document (up to limit) without naming an id:

```bash
uv run populate_jobs --limit 1   # enqueue
uv run run_jobs --limit 1        # drain (separate terminal if not using serve)
```

## Package layout

| Module | Role |
|--------|------|
| `client.py` | Paperless REST client (`@DBOS.step()` boundaries) |
| `agents.py` | Classifier and receipt Pydantic AI agents |
| `workflows.py` | `process_document` and `process_receipt` workflows |
| `triggers.py` | Webhooks, cron sweep, CLI producer |
| `schemas.py` | Pydantic I/O models |
