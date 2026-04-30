from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers.clients_router import router as clients_router
from routers.agent_router import router as agent_router
from config import get_settings

settings = get_settings()

allow_origins = [
    "http://localhost:5173",
    "http://localhost:3000",
]
if settings.cors_origins:
    allow_origins.extend(
        origin.strip()
        for origin in settings.cors_origins.split(",")
        if origin.strip()
    )

allow_origins = list(dict.fromkeys(allow_origins))

app = FastAPI(
    title="Asistente IA",
    description="Asistente conversacional con Firebase y LangChain",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(clients_router)
app.include_router(agent_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


# uvicorn main:app --reload --port 8000
