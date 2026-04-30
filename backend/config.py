import json
import tempfile
from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Se vuelven opcionales para que endpoints como /clients no caigan si faltan.
    openai_api_key: str = ""
    tavily_api_key: str = ""
    google_application_credentials: str = "./firebase-service-account.json"
    firebase_service_account_json: str = ""
    firebase_project_id: str = ""
    use_firestore: bool = True
    cors_origins: str = ""

    model_config = {
        "env_file": (".env", "../.env", "../../.env"),
        "env_file_encoding": "utf-8",
    }

    def model_post_init(self, __context):
        base_dir = Path(__file__).resolve().parent

        if self.firebase_service_account_json:
            try:
                payload = json.loads(self.firebase_service_account_json)
                temp_path = Path(tempfile.gettempdir()) / "firebase-service-account.json"
                temp_path.write_text(json.dumps(payload), encoding="utf-8")
                self.google_application_credentials = str(temp_path)
                if not self.firebase_project_id:
                    self.firebase_project_id = payload.get("project_id", "")
            except Exception:
                pass

        # Resuelve la ruta de credenciales incluso si el archivo esta fuera de backend.
        cred_path = Path(self.google_application_credentials)
        if not cred_path.is_absolute():
            candidate_paths = [
                (base_dir / cred_path),
                (base_dir / "../firebase-service-account.json"),
                (base_dir / "../../firebase-service-account.json"),
            ]
            for candidate in candidate_paths:
                if candidate.exists():
                    cred_path = candidate.resolve()
                    break

        if cred_path.exists():
            self.google_application_credentials = str(cred_path)

            # Si no vino FIREBASE_PROJECT_ID, se infiere del JSON de service account.
            if not self.firebase_project_id:
                try:
                    payload = json.loads(cred_path.read_text(encoding="utf-8"))
                    self.firebase_project_id = payload.get("project_id", "")
                except Exception:
                    pass


@lru_cache
def get_settings() -> Settings:
    return Settings()
