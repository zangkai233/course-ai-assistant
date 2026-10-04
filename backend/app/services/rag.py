import hashlib
import json

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import CourseChunk
from app.services.cache import get_cached_json, set_cached_json


async def embed_text(
    client: httpx.AsyncClient,
    text: str,
) -> list[float]:
    if not settings.embedding_api_key:
        raise ValueError("EMBEDDING_API_KEY is required for RAG and ingestion.")

    cache_identity = json.dumps(
        [settings.embedding_base_url, settings.embedding_model,
         settings.embedding_dim, text],
        ensure_ascii=False,
    )
    key = "embedding:" + hashlib.sha256(cache_identity.encode()).hexdigest()
    cached = await get_cached_json(key)
    if isinstance(cached, list) and len(cached) == settings.embedding_dim:
        return cached

    url = (
        settings.embedding_base_url.rstrip("/")
        + "/" + settings.embedding_path.lstrip("/")
    )
    response = await client.post(
        url,
        headers={"Authorization": f"Bearer {settings.embedding_api_key}"},
        json={"model": settings.embedding_model, "input": text},
    )
    response.raise_for_status()
    embedding = response.json()["data"][0]["embedding"]
    if len(embedding) != settings.embedding_dim:
        raise ValueError("Embedding length does not match EMBEDDING_DIM.")
    await set_cached_json(key, embedding)
    return embedding


async def retrieve_context(
    session: AsyncSession,
    client: httpx.AsyncClient,
    query: str,
) -> tuple[str, list[dict[str, str]]]:
    if not settings.rag_enabled:
        return "", []

    embedding = await embed_text(client, query)
    result = await session.execute(
        select(CourseChunk)
        .where(CourseChunk.embedding.is_not(None))
        .order_by(CourseChunk.embedding.cosine_distance(embedding))
        .limit(settings.rag_top_k)
    )
    chunks = result.scalars().all()
    context = "\n\n".join(
        f"[{index}] Source: {chunk.source}\n{chunk.content}"
        for index, chunk in enumerate(chunks, start=1)
    )
    sources = [
        {"id": str(chunk.id), "source": chunk.source, "content": chunk.content}
        for chunk in chunks
    ]
    return context, sources
