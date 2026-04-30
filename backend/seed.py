"""Script para cargar los perfiles de prueba en Firebase Firestore.

Uso:
    python seed.py           # Carga datos
    python seed.py --clean   # Limpia y recarga
"""
import json
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from firebase.client import get_sync_db


def seed(clean: bool = False):
    db = get_sync_db()
    data_path = Path("data/seed_clients.json")

    with open(data_path, encoding="utf-8") as f:
        clients = json.load(f)

    collection = db.collection("clients")

    if clean:
        print("Limpiando colección clients...")
        for doc in collection.stream():
            doc.reference.delete()

    for client in clients:
        client_id = client.pop("client_id", None)
        if client_id:
            collection.document(client_id).set(client)
            print(f"✓ Cargado: {client_id} - {client.get('name', 'Sin nombre')}")

    print(f"\n✅ {len(clients)} perfiles cargados en Firestore.")


if __name__ == "__main__":
    clean = "--clean" in sys.argv
    seed(clean=clean)
