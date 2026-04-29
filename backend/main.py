import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env before any imports that depend on env vars (e.g. autoppia_iwa needs OPENAI_API_KEY)
load_dotenv()

# autoppia_iwa pollutes sys.path with its internal 'src/' directory on import,
# which shadows our local packages. Pin our backend dir at the front.
_backend_dir = str(Path(__file__).resolve().parent)
sys.path.insert(0, _backend_dir)
import agent.browser_executor  # noqa: F401 — cache before autoppia_iwa can interfere

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

import socketio

from app.middleware import verify_api_key
from app.database import ensure_indexes
from app.sio_app import sio
from app.routes.api import operator
from app.routes import auth as auth_routes
from app.routes import user as user_routes
from app.routes import session as session_routes
from app.routes import profile as profile_routes
from app.routes import api_keys as api_keys_routes
from app.routes import skills as skills_routes
from app.routes import evals as evals_routes
from app.routes import wallet as wallet_routes
from app.routes import payments as payments_routes

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

# Web routes (no API key required — used by the frontend)
fastapi_app.include_router(auth_routes.router)
fastapi_app.include_router(user_routes.router)
fastapi_app.include_router(session_routes.router)
fastapi_app.include_router(profile_routes.router)
fastapi_app.include_router(api_keys_routes.router)
fastapi_app.include_router(skills_routes.router)
fastapi_app.include_router(evals_routes.router)
fastapi_app.include_router(wallet_routes.router)
fastapi_app.include_router(payments_routes.router)


@fastapi_app.get("/health")
async def health_check():
    return {"status": "ok"}


@fastapi_app.on_event("startup")
async def startup_event():
    await ensure_indexes()
    # Migrate existing users: add is_verified and auth_provider fields
    from app.database import users_collection
    await users_collection.update_many(
        {"is_verified": {"$exists": False}},
        {"$set": {"is_verified": True, "auth_provider": "email"}},
    )


# Wrap FastAPI inside Socket.IO ASGI app so both share the same origin
app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app)
