"""Ask a question about one part.

Returns JSON by default, or Server-Sent Events when the client sends Accept: text/event-stream.

SSE events:
- ``stage``  {"stage": "asking_llm", "detail": "anthropic"}  progress while the pipeline runs
  (``reading_scan`` appears when the user has just agreed to read a scanned drawing)
- ``answer`` the full ``AskResult`` (verified evidence, computation, provider)
- ``error``  problem details if the pipeline itself crashed
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

from asgi_correlation_id.context import correlation_id
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.domain.answer import AskResult, StageEvent
from app.logging_setup import log
from app.services.ask_service import AskService

router = APIRouter(tags=["ask"])


class AskIn(BaseModel):
    question: str = Field(max_length=4000, examples=["What material is this part made of?"])
    conversation_id: uuid.UUID | None = None


def _service(request: Request) -> AskService:
    return AskService(
        request.app.state.session_factory,
        request.app.state.gateway,
        request.app.state.settings,
        request.app.state.vision,
    )


@router.post(
    "/parts/{part_number}/ask",
    response_model=AskResult,
    summary="Ask a question about a part (JSON, or SSE with Accept: text/event-stream)",
)
async def ask(part_number: str, body: AskIn, request: Request):
    service = _service(request)
    request_id = correlation_id.get()
    stream = service.run(part_number, body.question, body.conversation_id, request_id)

    if "text/event-stream" in request.headers.get("accept", ""):

        async def events() -> AsyncIterator[dict]:
            try:
                async for item in stream:
                    if await request.is_disconnected():
                        log.info("ask.client_disconnected", part=part_number)
                        return
                    if isinstance(item, StageEvent):
                        yield {"event": "stage", "data": item.model_dump_json()}
                    else:
                        yield {"event": "answer", "data": item.model_dump_json()}
            except Exception as exc:
                log.exception("ask.stream_failed", error=str(exc))
                yield {
                    "event": "error",
                    "data": json.dumps(
                        {
                            "title": "Internal error",
                            "detail": "The answer pipeline failed",
                            "request_id": request_id,
                        }
                    ),
                }

        return EventSourceResponse(
            events(),
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            ping=15,
        )

    result: AskResult | None = None
    async for item in stream:
        if isinstance(item, AskResult):
            result = item
    assert result is not None
    return result
