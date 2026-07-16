# workflow-explorer

An agent-harness framework built on **DBOS** (durable orchestration), **Pydantic AI**
(agent harness), **Pydantic Logfire** (observability), and **FastAPI** (webhooks).
Webhook and cron triggers create typed *jobs*; a producer/consumer model enqueues and runs
them; each job type is handled by one consumer that may drive a Pydantic AI agent.

## Quickstart (local)

```bash
uv sync
cp .env.example .env
uv run serve
```

Job-specific setup and testing (including Paperless document triggers) live in each job's
README — start with [Paperless](harness/jobs_impl/paperless/README.md).

For Postgres in production or Docker Compose, see `docker-compose.yml` and uncomment the
Postgres URL in `.env.example`.

## Layout

- `harness/` — the framework (queue dispatch, agent factory, API, CLI)
- `harness/jobs_impl/paperless/` — Paperless document classification + receipt extraction ([docs](harness/jobs_impl/paperless/README.md))

## Tooling

Ruff handles formatting, linting, and import sorting. VS Code/Cursor picks this up from
[`.vscode/settings.json`](.vscode/settings.json) (format + fix + organize imports on save).

[Poe the Poet](https://poethepoet.natn.io/) task runner:

```bash
uv run poe validate   # check only (ruff + ty)
uv run poe format     # apply fixes and formatting
uv run python -m unittest discover -s tests -v
```
