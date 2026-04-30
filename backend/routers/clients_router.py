from fastapi import APIRouter, HTTPException
from firebase.clients import get_client, list_clients
from firebase.chat_history import get_conversations_for_client

router = APIRouter(prefix="/clients", tags=["clients"])


@router.get("")
async def get_clients():
    return await list_clients()


@router.get("/{client_id}")
async def get_client_by_id(client_id: str):
    client = await get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return client


@router.get("/{client_id}/conversations")
async def get_client_conversations(client_id: str):
    return await get_conversations_for_client(client_id)
