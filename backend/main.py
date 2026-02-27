import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load .env before any imports that depend on env vars (e.g. autoppia_iwa needs OPENAI_API_KEY)
load_dotenv()

# autoppia_iwa pollutes sys.path with its internal 'src/' directory on import,
# which shadows our local 'execution' package. Pin our backend dir at the front.
_backend_dir = str(Path(__file__).resolve().parent)
sys.path.insert(0, _backend_dir)
import execution.browser_executor  # noqa: F401 — cache before autoppia_iwa can interfere

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

import socketio

from app.middleware import verify_api_key
from app.database import ensure_indexes
from app.sio_app import sio
from app.routes import operator, cua
from app.routes import user as user_routes
from app.routes import session as session_routes

fastapi_app = FastAPI(
    title="Automata API",
    description="This is API for Automata Web Operator",
    version="1.0.0",
)

fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

fastapi_app.include_router(operator.router, prefix="/api/v1", dependencies=[Depends(verify_api_key)])
fastapi_app.include_router(cua.router, prefix="/api/v1", dependencies=[Depends(verify_api_key)])

# Web routes (no API key required — used by the frontend)
fastapi_app.include_router(user_routes.router)
fastapi_app.include_router(session_routes.router)


@fastapi_app.get("/health")
async def health_check():
    return {"status": "ok"}


@fastapi_app.on_event("startup")
async def startup_event():
    await ensure_indexes()


# Wrap FastAPI inside Socket.IO ASGI app so both share the same origin
app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app)
