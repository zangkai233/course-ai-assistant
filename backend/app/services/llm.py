import asyncio
import json

import httpx

from app.core.config import settings


SYSTEM_PROMPT = """
You are a university course AI assistant.

Your job is to help students understand course concepts clearly,
accurately, and concisely.

When approved course context is provided, prioritize that context.

If the provided material does not contain enough information,
say that clearly instead of inventing course-specific facts.
""".strip()


def build_messages(
    history: list[dict[str, str]],
    rag_context: str,
) -> list[dict[str, str]]:

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        }
    ]

    if rag_context:

        messages.append(
            {
                "role": "system",
                "content": (
                    "Approved course material:\n\n"
                    + rag_context
                ),
            }
        )

    # Prevent conversation context from growing forever
    messages.extend(history[-20:])

    return messages


async def stream_llm(
    client: httpx.AsyncClient,
    messages: list[dict[str, str]],
):

    url = (
        settings.llm_base_url.rstrip("/")
        + "/"
        + settings.llm_chat_path.lstrip("/")
    )

    headers = {
        "Authorization": (
            f"Bearer {settings.llm_api_key}"
        ),
        "Content-Type": "application/json",
    }

    payload = {
        "model": settings.llm_model,
        "messages": messages,
        "stream": True,
        "temperature": 0.2,
    }

    max_attempts = settings.llm_max_retries + 1

    for attempt in range(max_attempts):

        emitted_token = False

        try:

            async with client.stream(
                "POST",
                url,
                headers=headers,
                json=payload,
            ) as response:

                response.raise_for_status()

                async for line in response.aiter_lines():

                    if not line:
                        continue

                    if not line.startswith("data:"):
                        continue

                    raw = line[5:].strip()

                    if raw == "[DONE]":
                        return

                    try:
                        event = json.loads(raw)

                    except json.JSONDecodeError:
                        continue

                    choices = event.get("choices", [])

                    if not choices:
                        continue

                    delta = (
                        choices[0]
                        .get("delta", {})
                        .get("content")
                    )

                    if delta:

                        emitted_token = True

                        yield delta

            return

        except httpx.HTTPError:

            # Never restart generation after tokens
            # were already sent to the student,
            # otherwise text could be duplicated.
            if emitted_token:
                raise

            if attempt >= max_attempts - 1:
                raise

            await asyncio.sleep(
                0.5 * (2 ** attempt)
            )
