from __future__ import annotations

from datetime import datetime, timezone
from time import monotonic

import httpx
from google.oauth2 import service_account

from config import get_settings

TOKEN_SCOPE = "https://www.googleapis.com/auth/datastore"
TOKEN_TTL_SKEW_SECONDS = 60
REQUEST_TIMEOUT_SECONDS = 20

_TOKEN_CACHE = {
    "access_token": "",
    "expires_at": 0.0,
}


def _get_settings():
    return get_settings()


def _firestore_base_url() -> str:
    settings = _get_settings()
    return (
        f"https://firestore.googleapis.com/v1/projects/"
        f"{settings.firebase_project_id}/databases/(default)/documents"
    )


def _get_access_token() -> str:
    now = monotonic()
    cached_token = _TOKEN_CACHE.get("access_token", "")
    expires_at = float(_TOKEN_CACHE.get("expires_at", 0.0))
    if cached_token and now < expires_at:
        return cached_token

    settings = _get_settings()
    creds = service_account.Credentials.from_service_account_file(
        settings.google_application_credentials,
        scopes=[TOKEN_SCOPE],
    )
    assertion = creds._make_authorization_grant_assertion()
    if isinstance(assertion, bytes):
        assertion = assertion.decode("utf-8")

    response = httpx.post(
        "https://oauth2.googleapis.com/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    access_token = payload["access_token"]
    expires_in = int(payload.get("expires_in", 3600))

    _TOKEN_CACHE["access_token"] = access_token
    _TOKEN_CACHE["expires_at"] = now + max(0, expires_in - TOKEN_TTL_SKEW_SECONDS)
    return access_token


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_get_access_token()}"}


def _document_url(path: str) -> str:
    return f"{_firestore_base_url()}/{path}"


def _to_firestore_value(value):
    if value is None:
        return {"nullValue": None}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"integerValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return {"timestampValue": value.astimezone(timezone.utc).isoformat()}
    if isinstance(value, list):
        return {"arrayValue": {"values": [_to_firestore_value(item) for item in value]}}
    if isinstance(value, dict):
        return {
            "mapValue": {
                "fields": {key: _to_firestore_value(item) for key, item in value.items()}
            }
        }
    return {"stringValue": str(value)}


def _from_firestore_value(value: dict):
    if "nullValue" in value:
        return None
    if "booleanValue" in value:
        return value["booleanValue"]
    if "integerValue" in value:
        return int(value["integerValue"])
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "timestampValue" in value:
        return value["timestampValue"]
    if "stringValue" in value:
        return value["stringValue"]
    if "arrayValue" in value:
        return [_from_firestore_value(item) for item in value.get("arrayValue", {}).get("values", [])]
    if "mapValue" in value:
        fields = value.get("mapValue", {}).get("fields", {})
        return {key: _from_firestore_value(item) for key, item in fields.items()}
    return value


def _decode_document(document: dict) -> dict:
    name = document.get("name", "")
    doc_id = name.split("/")[-1] if name else ""
    fields = document.get("fields", {})
    decoded = {key: _from_firestore_value(value) for key, value in fields.items()}
    if doc_id:
        decoded["_document_id"] = doc_id
    return decoded


def get_document(path: str) -> dict:
    response = httpx.get(_document_url(path), headers=_headers(), timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def get_decoded_document(path: str) -> dict:
    return _decode_document(get_document(path))


def list_collection_documents(collection: str, page_size: int = 100) -> list[dict]:
    response = httpx.get(
        _document_url(collection),
        headers=_headers(),
        params={"pageSize": str(page_size)},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    return [_decode_document(document) for document in payload.get("documents", [])]


def append_history_item(client_id: str, history_item: dict) -> None:
    try:
        current = get_document(f"clients/{client_id}")
        history_values = current.get("fields", {}).get("history", {}).get("arrayValue", {}).get("values", [])
    except httpx.HTTPStatusError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            history_values = []
        else:
            raise

    history_values.append(_to_firestore_value(history_item))
    patch_document(
        f"clients/{client_id}",
        {
            "history": {"__raw_firestore_value__": {"arrayValue": {"values": history_values}}},
            "updated_at": datetime.now(timezone.utc),
        },
        ["history", "updated_at"],
    )


def upsert_conversation(conversation_id: str, conversation: dict) -> None:
    patch_document(
        f"conversations/{conversation_id}",
        {
            "client_id": conversation.get("client_id", ""),
            "messages": conversation.get("messages", []),
            "created_at": conversation.get("created_at", ""),
            "updated_at": datetime.now(timezone.utc),
        },
        ["client_id", "messages", "created_at", "updated_at"],
    )


def _normalize_field_map(field_map: dict) -> dict:
    normalized = {}
    for key, value in field_map.items():
        if isinstance(value, dict) and "__raw_firestore_value__" in value:
            normalized[key] = value["__raw_firestore_value__"]
        else:
            normalized[key] = _to_firestore_value(value)
    return normalized


def patch_document(path: str, field_map: dict, update_mask_fields: list[str]) -> dict:
    params = [("updateMask.fieldPaths", field) for field in update_mask_fields]
    response = httpx.patch(
        _document_url(path),
        params=params,
        headers={**_headers(), "Content-Type": "application/json"},
        json={"fields": _normalize_field_map(field_map)},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()