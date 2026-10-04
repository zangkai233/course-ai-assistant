import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_student_id
from app.core.config import settings
from app.db.models import Conversation, Message
from app.db.session import SessionLocal, get_session
from app.schemas.chat import ChatRequest
from app.services.concurrency import acquire_llm_slot, release_llm_slot
from app.services.llm import build_messages, stream_llm
from app.services.rag import retrieve_context
from app.services.rate_limit import enforce_rate_limit


router = APIRouter(tags=["chat"])
StudentID = Annotated[str, Depends(get_student_id)]
DatabaseSession = Annotated[AsyncSession, Depends(get_session)]


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def owned_conversation(
    session: AsyncSession,
    conversation_id: UUID,
    student_id: str,
) -> Conversation:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None or conversation.student_id != student_id:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conversation


@router.get("/conversations")
async def list_conversations(student_id: StudentID, session: DatabaseSession):
    result = await session.execute(
        select(Conversation)
        .where(Conversation.student_id == student_id)
        .order_by(Conversation.created_at.desc())
        .limit(100)
    )
    return [
        {"id": str(item.id), "title": item.title, "created_at": item.created_at}
        for item in result.scalars().all()
    ]


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(
    conversation_id: UUID,
    student_id: StudentID,
    session: DatabaseSession,
):
    await owned_conversation(session, conversation_id, student_id)
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    return [
        {"id": str(item.id), "role": item.role, "content": item.content}
        for item in result.scalars().all()
    ]


@router.post("/chat")
async def chat(payload: ChatRequest, request: Request, student_id: StudentID):
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Message cannot be blank.")
    await enforce_rate_limit(student_id)

    # Close the database session before holding a streaming connection.
    async with SessionLocal() as session:
        if payload.conversation_id:
            conversation = await owned_conversation(
                session, payload.conversation_id, student_id,
            )
        else:
            conversation = Conversation(student_id=student_id, title=message[:100])
            session.add(conversation)
            await session.flush()

        conversation_id = conversation.id
        result = await session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(19)
        )
        previous = list(reversed(result.scalars().all()))
        history = [{"role": item.role, "content": item.content} for item in previous]
        history.append({"role": "user", "content": message})
        rag_context, sources = await retrieve_context(
            session, request.app.state.http_client, message,
        )
        session.add(Message(
            conversation_id=conversation_id,
            role="user",
            content=message,
        ))
        await session.commit()

    slot = await acquire_llm_slot()
    if slot is None:
        raise HTTPException(
            status_code=503,
            detail="The AI is busy. Please try again shortly.",
            headers={"Retry-After": "5"},
        )

    async def generate() -> AsyncGenerator[str, None]:
        answer: list[str] = []
        try:
            yield sse_event("meta", {"conversation_id": str(conversation_id)})
            yield sse_event("sources", {"sources": sources})
            async with asyncio.timeout(settings.llm_timeout_seconds):
                async for token in stream_llm(
                    request.app.state.http_client,
                    build_messages(history, rag_context),
                ):
                    if await request.is_disconnected():
                        return
                    answer.append(token)
                    yield sse_event("token", {"text": token})

            async with SessionLocal() as save_session:
                save_session.add(Message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content="".join(answer),
                ))
                await save_session.commit()
            yield sse_event("done", {"conversation_id": str(conversation_id)})
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            yield sse_event("error", {"message": "The AI request timed out. Please try again."})
        except Exception:
            yield sse_event("error", {"message": "The AI service is temporarily unavailable."})
        finally:
            await asyncio.shield(release_llm_slot(slot))

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
