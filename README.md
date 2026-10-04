# Course AI

Source and configuration templates for the 500-student course chatbot discussed in the reference conversation. The target architecture uses React + TypeScript + Vite, FastAPI, async SQLAlchemy with Psycopg, PostgreSQL/pgvector, Redis, and an OpenAI-compatible LLM API.

This repository contains the application source and a Compose stack for PostgreSQL, Redis, the backend, and the frontend. Local environment files and credentials are not tracked. A local burst-test result is recorded below; sustained capacity has not been measured.

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

After filling your own backend environment, start the Compose stack with `docker compose --env-file backend/.env up -d --build`. The PostgreSQL initialization file creates the `vector` extension. The application creates its table definitions at startup.

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

## Chat concurrency test

The project-root `test.py` sends concurrent requests to the running backend. It counts a request as successful only after the SSE `done` event, and reports HTTP errors, stream errors, completion latency, first-token latency, and request throughput. Each request uses a distinct student ID so the per-student rate limit does not affect this capacity measurement.

Start the Docker stack if it is stopped (from the project root):

```sh
docker compose --env-file backend/.env up -d --build
```

Then run a small check before increasing the load:

```sh
backend/.venv/bin/python test.py --requests 10 --concurrency 10
backend/.venv/bin/python test.py --requests 500 --concurrency 500 --max-failure-rate 0.05 --max-p95-ms 30000
```

Adjust the thresholds to your actual service targets. The test calls the configured LLM provider once per successful chat request, which may incur usage charges. Running containers do not need to be restarted between tests. Rebuild after backend image or dependency changes. The frontend is not used by this API-level test.

On October 4, 2026, a user-run local Docker test with `--requests 500 --concurrency 500` completed all 500 chats with no failures. It took 13.29 seconds, for 37.63 successful requests per second. Successful response latency was 6.90 seconds at P50 and 12.53 seconds at P95; first-token latency was 6.36 seconds at P50 and 12.00 seconds at P95. This was one burst using the script's short default prompt and a new student/conversation per request. It does not establish sustained throughput or the maximum supported number of active students.

## Course material ingestion

After your own setup, run the ingestion module from the backend working directory:

```sh
python -m scripts.ingest_text path/to/course.txt --source "Lecture 1"
```

Input is UTF-8 plain text. The script splits it into overlapping chunks, calls the embedding API, and saves vectors to `course_chunks`. It appends records on each run. `EMBEDDING_DIM` must match the embedding model output and the database vector column. After ingestion, set `RAG_ENABLED=true` in your own backend environment to retrieve context during chat.

## Reference implementation

Available backend code was copied from the reference conversation. The retrieved reference ends partway through the RAG service; the remaining RAG, routes, ingestion, and frontend templates were completed to follow its architecture and conventions. This scaffold includes the missing TypeScript project configuration and an embedding cache helper.

Use `test.py` against the deployment you intend to operate when measuring capacity for that environment.
