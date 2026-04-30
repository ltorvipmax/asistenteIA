from pydantic import BaseModel
from typing import Optional


class ChatRequest(BaseModel):
    client_id: str
    message: str
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    conversation_id: str


class MessageItem(BaseModel):
    role: str  # "human" | "ai"
    content: str
    timestamp: Optional[str] = None


class ConversationResponse(BaseModel):
    conversation_id: str
    client_id: str
    messages: list[MessageItem] = []
