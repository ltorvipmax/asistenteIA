import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore import AsyncClient
from config import get_settings

_app = None
_async_db = None


def get_firebase_app():
    global _app
    if _app is None:
        try:
            settings = get_settings()
            if not settings.firebase_project_id or not settings.google_application_credentials:
                return None
            cred = credentials.Certificate(settings.google_application_credentials)
            _app = firebase_admin.initialize_app(
                cred, {"projectId": settings.firebase_project_id}
            )
        except Exception as exc:
            print(f"[firebase.client.get_firebase_app] Initialization error: {exc}")
            return None
    return _app


def get_sync_db():
    """Solo para seed.py. No usar en endpoints async."""
    app = get_firebase_app()
    if app is None:
        return None
    return firestore.client(app=app)


def get_async_db() -> AsyncClient:
    """Cliente async para endpoints FastAPI."""
    global _async_db
    if _async_db is None:
        try:
            settings = get_settings()
            if not settings.firebase_project_id or not settings.google_application_credentials:
                return None
            cred = credentials.Certificate(settings.google_application_credentials)
            _async_db = AsyncClient(
                project=settings.firebase_project_id,
                credentials=cred.get_credential()
            )
        except Exception as exc:
            print(f"[firebase.client.get_async_db] Initialization error: {exc}")
            return None
    return _async_db
