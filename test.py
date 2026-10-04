"""Measure end-to-end concurrency of the Course AI chat endpoint.

Run only against a service and LLM provider you are authorized to load test.
Each request starts a new conversation and uses a distinct student ID.
"""

import argparse
import asyncio
import json
import math
import time
import uuid
from collections import Counter
from dataclasses import dataclass

import httpx


@dataclass
class Result:
    outcome: str
    elapsed_ms: float
    first_token_ms: float | None = None


def percentile(values: list[float], percent: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * percent / 100
    lower = math.floor(rank)
    upper = math.ceil(rank)
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower), 1)


async def send_chat(
    client: httpx.AsyncClient,
    base_url: str,
    student_id: str,
    message: str,
) -> Result:
    started = time.perf_counter()
    first_token_ms = None
    event_name = None
    saw_done = False
    saw_error = False

    try:
        async with client.stream(
            "POST",
            f"{base_url}/api/chat",
            headers={"X-Student-ID": student_id, "Accept": "text/event-stream"},
            json={"message": message, "conversation_id": None},
        ) as response:
            if response.status_code != 200:
                return Result(f"http_{response.status_code}", (time.perf_counter() - started) * 1000)

            async for line in response.aiter_lines():
                if line.startswith("event:"):
                    event_name = line[6:].strip()
                elif line.startswith("data:"):
                    if event_name == "token" and first_token_ms is None:
                        first_token_ms = (time.perf_counter() - started) * 1000
                    elif event_name == "done":
                        saw_done = True
                    elif event_name == "error":
                        saw_error = True
                elif not line:
                    event_name = None

        outcome = "sse_error" if saw_error else "success" if saw_done else "incomplete_stream"
        return Result(outcome, (time.perf_counter() - started) * 1000, first_token_ms)
    except httpx.TimeoutException:
        outcome = "client_timeout"
    except httpx.RequestError:
        outcome = "connection_error"

    return Result(outcome, (time.perf_counter() - started) * 1000, first_token_ms)


async def run(args: argparse.Namespace) -> dict:
    base_url = args.base_url.rstrip("/")
    timeout = httpx.Timeout(args.timeout, connect=min(args.timeout, 10))
    limits = httpx.Limits(max_connections=args.concurrency, max_keepalive_connections=args.concurrency)

    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        ready = await client.get(f"{base_url}/health/ready")
        if ready.status_code != 200:
            raise RuntimeError(f"Readiness check failed: HTTP {ready.status_code}")

        gate = asyncio.Semaphore(args.concurrency)
        prefix = f"loadtest-{uuid.uuid4().hex[:8]}"

        async def one(index: int) -> Result:
            async with gate:
                return await send_chat(client, base_url, f"{prefix}-{index}", args.message)

        started = time.perf_counter()
        results = await asyncio.gather(*(one(index) for index in range(args.requests)))
        duration = time.perf_counter() - started

    counts = Counter(item.outcome for item in results)
    successful = [item for item in results if item.outcome == "success"]
    total_ms = [item.elapsed_ms for item in successful]
    first_token_ms = [item.first_token_ms for item in successful if item.first_token_ms is not None]
    return {
        "requests": args.requests,
        "concurrency": args.concurrency,
        "duration_seconds": round(duration, 2),
        "completed_requests_per_second": round(args.requests / duration, 2),
        "successful_requests_per_second": round(len(successful) / duration, 2),
        "outcomes": dict(sorted(counts.items())),
        "failure_rate": round(1 - len(successful) / args.requests, 4),
        "success_latency_ms": {
            "p50": percentile(total_ms, 50),
            "p95": percentile(total_ms, 95),
            "p99": percentile(total_ms, 99),
        },
        "first_token_ms": {
            "p50": percentile(first_token_ms, 50),
            "p95": percentile(first_token_ms, 95),
            "p99": percentile(first_token_ms, 99),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, required=True)
    parser.add_argument("--concurrency", type=int, required=True)
    parser.add_argument("--timeout", type=float, default=120, help="Per-request timeout in seconds")
    parser.add_argument("--message", default="Explain recursion in one short paragraph.")
    parser.add_argument("--max-failure-rate", type=float, help="Fail if this fraction is exceeded, e.g. 0.05")
    parser.add_argument("--max-p95-ms", type=float, help="Fail if successful responses exceed this p95")
    args = parser.parse_args()

    if args.requests < 1 or args.concurrency < 1 or args.timeout <= 0:
        parser.error("requests, concurrency, and timeout must be positive")
    if args.max_failure_rate is not None and not 0 <= args.max_failure_rate <= 1:
        parser.error("max-failure-rate must be between 0 and 1")
    if args.max_p95_ms is not None and args.max_p95_ms <= 0:
        parser.error("max-p95-ms must be positive")

    try:
        report = asyncio.run(run(args))
    except (httpx.RequestError, RuntimeError) as exc:
        parser.exit(2, f"Load test could not start: {exc}\n")

    print(json.dumps(report, indent=2))
    if args.max_failure_rate is not None and report["failure_rate"] > args.max_failure_rate:
        parser.exit(1, "Failure-rate threshold exceeded.\n")
    p95 = report["success_latency_ms"]["p95"]
    if args.max_p95_ms is not None and (p95 is None or p95 > args.max_p95_ms):
        parser.exit(1, "P95 latency threshold exceeded.\n")


if __name__ == "__main__":
    main()
