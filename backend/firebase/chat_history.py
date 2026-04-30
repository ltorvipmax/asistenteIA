import asyncio
import os
import uuid
from datetime import datetime, timezone
from firebase.client import get_sync_db
from firebase.rest_firestore import (
    append_history_item,
    get_decoded_document,
    list_collection_documents,
    upsert_conversation,
)
from typing import Optional
from google.cloud.firestore import ArrayUnion

COLLECTION = "conversations"
_LOCAL_CONVERSATIONS: dict[str, dict] = {}
USE_FIRESTORE = os.getenv("USE_FIRESTORE", "1").strip().lower() in {"1", "true", "yes", "on"}
_FIRESTORE_DISABLED_UNTIL = 0.0
FIRESTORE_BACKOFF_SECONDS = 60
FIRESTORE_RPC_TIMEOUT_SECONDS = 3
FIRESTORE_ASYNC_TIMEOUT_SECONDS = 4


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _firestore_available() -> bool:
    return asyncio.get_running_loop().time() >= _FIRESTORE_DISABLED_UNTIL


def _mark_firestore_unavailable() -> None:
    global _FIRESTORE_DISABLED_UNTIL
    _FIRESTORE_DISABLED_UNTIL = asyncio.get_running_loop().time() + FIRESTORE_BACKOFF_SECONDS


async def _persist_via_rest(conversation_id: str, client_id: str, history_item: dict) -> None:
    conversation = _LOCAL_CONVERSATIONS.get(conversation_id)
    if conversation is None:
        return

    await asyncio.gather(
        asyncio.to_thread(upsert_conversation, conversation_id, conversation),
        asyncio.to_thread(append_history_item, client_id, history_item),
    )


def _local_create_conversation(client_id: str) -> str:
    conv_id = str(uuid.uuid4())
    _LOCAL_CONVERSATIONS[conv_id] = {
        "client_id": client_id,
        "messages": [],
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    return conv_id


async def create_conversation(client_id: str) -> str:
    # Keep conversation creation off the critical path. The first add_message(...)
    # uses set(..., merge=True), so Firestore can create the document lazily.
    return _local_create_conversation(client_id)


async def get_conversation(conversation_id: str) -> Optional[dict]:
    local_conv = _LOCAL_CONVERSATIONS.get(conversation_id)
    if local_conv is not None:
        return local_conv

    if (not USE_FIRESTORE) or (not _firestore_available()):
        if USE_FIRESTORE:
            try:
                conversation = await asyncio.to_thread(
                    get_decoded_document, f"conversations/{conversation_id}"
                )
                conversation.pop("_document_id", None)
                return conversation
            except Exception:
                pass
        return _LOCAL_CONVERSATIONS.get(conversation_id)

    try:
        db = get_sync_db()
        if db is None:
            return _LOCAL_CONVERSATIONS.get(conversation_id)

        async with asyncio.timeout(FIRESTORE_ASYNC_TIMEOUT_SECONDS):
            doc = await asyncio.to_thread(
                db.collection(COLLECTION).document(conversation_id).get,
                timeout=FIRESTORE_RPC_TIMEOUT_SECONDS,
                retry=None,
            )
        if not doc.exists:
            return None
        return doc.to_dict()
    except Exception as exc:
        _mark_firestore_unavailable()
        print(f"[chat_history.get_conversation] Firestore error: {exc!r}")
        try:
            conversation = await asyncio.to_thread(
                get_decoded_document, f"conversations/{conversation_id}"
            )
            conversation.pop("_document_id", None)
            return conversation
        except Exception:
            pass
        return _LOCAL_CONVERSATIONS.get(conversation_id)


async def add_message(conversation_id: str, client_id: str, role: str, content: str) -> None:
    message = {
        "role": role,
        "content": content,
        "timestamp": _now_iso()
    }

    # Keep a per-client audit trail in clients/{client_id}.history.
    history_item = {
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
        "timestamp": message["timestamp"],
    }

    conv = _LOCAL_CONVERSATIONS.get(conversation_id)
    if conv is None:
        conv = {
            "client_id": client_id,
            "messages": [],
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        _LOCAL_CONVERSATIONS[conversation_id] = conv
    conv["messages"].append(message)
    conv["updated_at"] = _now_iso()

    if (not USE_FIRESTORE) or (not _firestore_available()):
        if USE_FIRESTORE:
            try:
                await _persist_via_rest(conversation_id, client_id, history_item)
            except Exception as exc:
                print(f"[chat_history.add_message.rest] Firestore REST error: {exc!r}")
        return

    try:
        db = get_sync_db()
        if db is None:
            raise RuntimeError("Firestore sync client is not available")

        conv_payload = {
                "client_id": client_id,
                "messages": ArrayUnion([message]),
                "updated_at": datetime.now(timezone.utc),
            }
        client_payload = {
                "history": ArrayUnion([history_item]),
                "updated_at": datetime.now(timezone.utc),
            }

        async with asyncio.timeout(FIRESTORE_ASYNC_TIMEOUT_SECONDS):
            # Use set(..., merge=True) so writes do not fail when the doc does not exist yet.
            await asyncio.gather(
                asyncio.to_thread(
                    db.collection(COLLECTION).document(conversation_id).set,
                    conv_payload,
                    merge=True,
                    timeout=FIRESTORE_RPC_TIMEOUT_SECONDS,
                    retry=None,
                ),
                asyncio.to_thread(
                    db.collection("clients").document(client_id).set,
                    client_payload,
                    merge=True,
                    timeout=FIRESTORE_RPC_TIMEOUT_SECONDS,
                    retry=None,
                ),
            )
        return
    except Exception as exc:
        _mark_firestore_unavailable()
        print(f"[chat_history.add_message] Firestore error: {exc!r}")
        try:
            await _persist_via_rest(conversation_id, client_id, history_item)
        except Exception as rest_exc:
            print(f"[chat_history.add_message.rest] Firestore REST error: {rest_exc!r}")


async def get_conversations_for_client(client_id: str) -> list[dict]:
    if (not USE_FIRESTORE) or (not _firestore_available()):
        if USE_FIRESTORE:
            try:
                documents = await asyncio.to_thread(list_collection_documents, COLLECTION)
                conversations = []
                for item in documents:
                    if item.get("client_id") != client_id:
                        continue
                    conversation_id = item.pop("_document_id", "")
                    item["conversation_id"] = conversation_id
                    conversations.append(item)
                conversations.sort(key=lambda c: c.get("updated_at", ""), reverse=True)
                if conversations:
                    return conversations[:20]
            except Exception:
                pass
        conversations = []
        for conv_id, conv in _LOCAL_CONVERSATIONS.items():
            if conv.get("client_id") == client_id:
                item = dict(conv)
                item["conversation_id"] = conv_id
                conversations.append(item)
        conversations.sort(key=lambda c: c.get("updated_at", ""), reverse=True)
        return conversations[:20]

    try:
        db = get_sync_db()
        if db is None:
            raise RuntimeError("Firestore sync client is not available")

        def _fetch_conversations() -> list[dict]:
            # Requiere índice compuesto: client_id (ASC) + updated_at (DESC)
            query = (
                db.collection(COLLECTION)
                .where("client_id", "==", client_id)
                .order_by("updated_at", direction="DESCENDING")
                .limit(20)
            )
            items: list[dict] = []
            for doc in query.stream(timeout=FIRESTORE_RPC_TIMEOUT_SECONDS, retry=None):
                data = doc.to_dict()
                data["conversation_id"] = doc.id
                items.append(data)
            return items

        async with asyncio.timeout(FIRESTORE_ASYNC_TIMEOUT_SECONDS):
            return await asyncio.to_thread(_fetch_conversations)
    except Exception as exc:
        _mark_firestore_unavailable()
        print(f"[chat_history.get_conversations_for_client] Firestore error: {exc!r}")
        try:
            documents = await asyncio.to_thread(list_collection_documents, COLLECTION)
            conversations = []
            for item in documents:
                if item.get("client_id") != client_id:
                    continue
                conversation_id = item.pop("_document_id", "")
                item["conversation_id"] = conversation_id
                conversations.append(item)
            conversations.sort(key=lambda c: c.get("updated_at", ""), reverse=True)
            if conversations:
                return conversations[:20]
        except Exception:
            pass
        conversations = []
        for conv_id, conv in _LOCAL_CONVERSATIONS.items():
            if conv.get("client_id") == client_id:
                item = dict(conv)
                item["conversation_id"] = conv_id
                conversations.append(item)
        conversations.sort(key=lambda c: c.get("updated_at", ""), reverse=True)
        return conversations[:20]


async def delete_conversation(conversation_id: str) -> None:
    if (not USE_FIRESTORE) or (not _firestore_available()):
        _LOCAL_CONVERSATIONS.pop(conversation_id, None)
        return

    try:
        db = get_sync_db()
        if db is None:
            raise RuntimeError("Firestore sync client is not available")

        async with asyncio.timeout(FIRESTORE_ASYNC_TIMEOUT_SECONDS):
            await asyncio.to_thread(
                db.collection(COLLECTION).document(conversation_id).delete,
                timeout=FIRESTORE_RPC_TIMEOUT_SECONDS,
                retry=None,
            )
    except Exception as exc:
        _mark_firestore_unavailable()
        print(f"[chat_history.delete_conversation] Firestore error: {exc!r}")
        _LOCAL_CONVERSATIONS.pop(conversation_id, None)
