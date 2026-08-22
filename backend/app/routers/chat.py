from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.agent.orchestrator import LLMNotConfiguredError, ToolLoopExceededError, run_chat
from app.auth import get_current_user

router = APIRouter()


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


@router.post("/chat")
def chat(body: ChatRequest, user_id: str = Depends(get_current_user)) -> dict:
    try:
        return run_chat(user_id, [m.model_dump() for m in body.messages])
    except LLMNotConfiguredError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ToolLoopExceededError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
