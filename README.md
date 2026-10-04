# Course AI

Source and configuration templates for the 500-student course chatbot discussed in the reference conversation. The target architecture uses React + TypeScript + Vite, FastAPI, async SQLAlchemy with Psycopg, PostgreSQL/pgvector, Redis, and an OpenAI-compatible LLM API.

This folder contains source files only. No packages, environments, databases, Docker services, API credentials, or deployment have been configured, installed, or run. There are no real `.env` files. Runtime and capacity have not been tested.

## Project layout

```text
RA_Agent/
├── .gitignore
├── README.md
├── docker-compose.yml
├── infra/
│   ├── init.sql
│   └── nginx.conf.example
├── backend/
│   ├── .env.example
│   ├── requirements.txt
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py
│   │   │   └── redis.py
│   │   ├── db/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── session.py
│   │   │   └── models.py
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   └── chat.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── cache.py
│   │   │   ├── concurrency.py
│   │   │   ├── llm.py
│   │   │   ├── rag.py
│   │   │   └── rate_limit.py
│   │   └── api/
│   │       ├── __init__.py
│   │       ├── deps.py
│   │       └── routes/
│   │           ├── __init__.py
│   │           ├── chat.py
│   │           └── health.py
│   └── scripts/
│       ├── __init__.py
│       └── ingest_text.py
└── frontend/
    ├── .env.example
    ├── package.json
    ├── tsconfig.json
    ├── tsconfig.app.json
    ├── tsconfig.node.json
    ├── vite.config.ts
    ├── index.html
    └── src/
        ├── vite-env.d.ts
        ├── main.tsx
        ├── App.tsx
        ├── styles.css
        ├── types.ts
        └── api/
            └── chat.ts
```

## Request flow

```text
Student browser (React)
    -> Cloudflare / HTTPS / load balancer (user deployment)
    -> FastAPI instance 1 or 2, with 2 workers each (user deployment)
    -> Student identity header + Redis per-student rate limit
    -> PostgreSQL conversation history + optional pgvector retrieval
    -> Redis shared LLM slot (default maximum: 50 across all workers)
    -> LLM API
    -> SSE token stream to React
    -> Save completed assistant response to PostgreSQL
```

Redis also caches embeddings so repeated text can reuse a vector. Conversation answers themselves are not cached across students. PostgreSQL stores conversations, messages, and course chunks. The UI includes a student ID entry, new conversations, saved history, streamed answers, course source excerpts, errors, and a stop button.

The 500-student figure is an architecture target, not a measured capacity claim. `LLM_MAX_CONCURRENCY=50` controls simultaneous generations; it does not configure the provider's account quota.

## Environment templates

Fill your own local environment files when you are ready:

- `backend/.env.example`: app settings, PostgreSQL/Redis settings, chat provider, embedding provider, and concurrency/cache limits. All credentials and credential-bearing URLs are empty.
- `frontend/.env.example`: the public backend URL only. Provider keys belong exclusively in the backend environment.

Backend settings are read from `.env` relative to the backend working directory. Python source requires Python 3.11 or newer. Vite 7 requires a supported Node version (20.19+ or 22.12+).

The Compose file is a template for PostgreSQL/pgvector and Redis only. After filling your own backend environment, its variables are supplied with `docker compose --env-file backend/.env up -d`. The PostgreSQL initialization file creates the `vector` extension. The application creates its table definitions at startup. No services have been started by the file creation task.

The optional `infra/nginx.conf.example` shows two backend instances and disables buffering for SSE. Supply your own addresses and deployment configuration. It is not active or included in Compose.

## Backend API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Liveness |
| GET | `/health/ready` | PostgreSQL and Redis readiness |
| POST | `/api/chat` | Stream a chat response |
| GET | `/api/conversations` | List the current student's conversations |
| GET | `/api/conversations/{id}/messages` | Load the current student's conversation |

Chat and history routes use `X-Student-ID`. This is the local demo identity mechanism from the reference conversation. A production login system is not implemented. Replace the dependency with trusted authentication for a real deployment.

Example chat request body:

```json
{
  "message": "Explain recursion with a simple example",
  "conversation_id": null
}
```

SSE events are `meta` (conversation ID), `sources` (RAG excerpts), `token` (text), `done`, and `error`. The frontend uses a streaming `fetch` request to send the JSON body and student header. Aborted or failed responses are not saved as completed assistant messages.

## Course material ingestion

After your own setup, run the ingestion module from the backend working directory:

```sh
python -m scripts.ingest_text path/to/course.txt --source "Lecture 1"
```

Input is UTF-8 plain text. The script splits it into overlapping chunks, calls the embedding API, and saves vectors to `course_chunks`. It appends records on each run. `EMBEDDING_DIM` must match the embedding model output and the database vector column. After ingestion, set `RAG_ENABLED=true` in your own backend environment to retrieve context during chat.

## Reference implementation

Available backend code was copied from the reference conversation. The retrieved reference ends partway through the RAG service; the remaining RAG, routes, ingestion, and frontend templates were completed to follow its architecture and conventions. This scaffold includes the missing TypeScript project configuration and an embedding cache helper.

Only file existence, content completeness, and empty secret placeholders were checked. No installation, startup, build, runtime troubleshooting, load testing, or deployment was performed.
