from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config
from .db import init_db
from .routers import conversations, documents, questions

app = FastAPI(title="DocPilot API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(questions.router)
app.include_router(conversations.router)


@app.on_event("startup")
def startup() -> None:
    init_db()
    config.ensure_dirs()
    from .services.ingestion import recover_interrupted_documents

    recover_interrupted_documents()


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "chat_model": config.MISTRAL_CHAT_MODEL,
        "embed_model": config.MISTRAL_EMBED_MODEL,
        "api_key_configured": bool(config.MISTRAL_API_KEY),
    }


# Serve the built frontend (frontend/dist) when present so one process can
# host the whole app: `npm run build` then start uvicorn.
_FRONTEND_DIST = config.BACKEND_DIR.parent / "frontend" / "dist"
if _FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")
