import asyncio
import json
import os
from pathlib import Path
from time import monotonic

from firebase.client import get_async_db
from typing import Optional

COLLECTION = "clients"
USE_FIRESTORE = os.getenv("USE_FIRESTORE", "1").strip().lower() in {"1", "true", "yes", "on"}
_FIRESTORE_DISABLED_UNTIL = 0.0
FIRESTORE_BACKOFF_SECONDS = 60
FIRESTORE_RPC_TIMEOUT_SECONDS = 3


def _firestore_available() -> bool:
    return monotonic() >= _FIRESTORE_DISABLED_UNTIL


def _mark_firestore_unavailable() -> None:
    global _FIRESTORE_DISABLED_UNTIL
    _FIRESTORE_DISABLED_UNTIL = monotonic() + FIRESTORE_BACKOFF_SECONDS


def _load_local_clients() -> list[dict]:
    data_path = Path(__file__).resolve().parent.parent / "data" / "seed_clients.json"
    if not data_path.exists():
        return []

    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)

    clients = []
    for item in data:
        client = dict(item)
        client_id = client.get("client_id")
        if client_id:
            client["client_id"] = client_id
        clients.append(client)
    return clients


async def get_client(client_id: str) -> Optional[dict]:
    if (not USE_FIRESTORE) or (not _firestore_available()):
        for client in _load_local_clients():
            if client.get("client_id") == client_id:
                return client
        return None

    try:
        db = get_async_db()
        if db is None:
            for client in _load_local_clients():
                if client.get("client_id") == client_id:
                    return client
            return None
        async with asyncio.timeout(8):
            doc = await db.collection(COLLECTION).document(client_id).get(timeout=FIRESTORE_RPC_TIMEOUT_SECONDS)
        if not doc.exists:
            return None
        data = doc.to_dict()
        data["client_id"] = client_id
        return data
    except Exception:
        _mark_firestore_unavailable()
        for client in _load_local_clients():
            if client.get("client_id") == client_id:
                return client
        return None


async def list_clients() -> list[dict]:
    if (not USE_FIRESTORE) or (not _firestore_available()):
        return _load_local_clients()

    try:
        db = get_async_db()
        if db is None:
            return _load_local_clients()
        clients = []
        async with asyncio.timeout(8):
            async for doc in db.collection(COLLECTION).stream(timeout=FIRESTORE_RPC_TIMEOUT_SECONDS):
                data = doc.to_dict()
                data["client_id"] = doc.id
                clients.append(data)
        return clients
    except Exception:
        _mark_firestore_unavailable()
        return _load_local_clients()


async def upsert_client(client_id: str, data: dict) -> None:
    if not USE_FIRESTORE:
        return

    db = get_async_db()
    await db.collection(COLLECTION).document(client_id).set(data, merge=True)
