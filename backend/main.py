import sys
import os
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# Load .env before agent imports that read OPENAI_API_KEY / Browserbase env vars.
_backend_dir_path = Path(__file__).resolve().parent
load_dotenv(_backend_dir_path / ".env")
load_dotenv()

# Pin backend dir first so local package `agent` resolves reliably.
_backend_dir = str(_backend_dir_path)
sys.path.insert(0, _backend_dir)
import agent.browser_executor  # noqa: F401 — warm import; keeps `agent` from sys.path races

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

import socketio

from app.middleware import verify_api_key
from app.api_errors import error_payload
from app.database import ensure_indexes
from app.sio_app import sio
from app.routes.api import agents, legacy_tasks
from app.routes import auth as auth_routes
from app.routes import user as user_routes
from app.routes import session as session_routes
from app.routes import profile as profile_routes
from app.routes import api_keys as api_keys_routes
from app.routes import companies as companies_routes
from app.routes import connectors as connectors_routes
from app.routes import entities as entities_routes
from app.routes import approvals as approvals_routes
from app.routes import artifacts as artifacts_routes
from app.routes import credentials as credentials_routes
from app.routes import capabilities as capabilities_routes
from app.routes import knowledge as knowledge_routes
from app.routes import onboarding as onboarding_routes
from app.routes import skills as skills_routes
from app.routes import agent_configs as agent_configs_routes
from app.routes import agent_assets as agent_assets_routes
from app.routes import toolkits as toolkits_routes
from app.routes import evals as evals_routes
from app.routes import analytics as analytics_routes
from app.routes import agent_creation as agent_creation_routes
from app.routes import runtime as runtime_routes
from app.routes import validator_rounds as validator_rounds_routes
from app.routes import work_items as work_items_routes
from app.routes import notifications as notifications_routes
from app.routes import assistant as assistant_routes
from app.routes import embed as embed_routes

def _production_mode() -> bool:
    return os.getenv("AUTOMATA_ENV", os.getenv("ENVIRONMENT", os.getenv("APP_ENV", ""))).strip().lower() in {
        "prod",
        "production",
    }


_hide_internal_openapi = _production_mode() or os.getenv("AUTOMATA_HIDE_INTERNAL_OPENAPI", "").strip().lower() in {
    "1",
    "true",
    "yes",
}


fastapi_app = FastAPI(
    title="Automata API",
    description="This is API for Automata Agents",
    version="1.0.0",
    openapi_url=None if _hide_internal_openapi else "/openapi.json",
    docs_url=None if _hide_internal_openapi else "/docs",
    redoc_url=None if _hide_internal_openapi else "/redoc",
)

fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

fastapi_app.include_router(
    legacy_tasks.router,
    prefix="/api/v1",
    dependencies=[Depends(verify_api_key)],
    include_in_schema=False,
    deprecated=True,
)
fastapi_app.include_router(agents.router, prefix="/api/v1")

# Web routes (no API key required — used by the frontend)
fastapi_app.include_router(auth_routes.router)
fastapi_app.include_router(user_routes.router)
fastapi_app.include_router(session_routes.router)
fastapi_app.include_router(profile_routes.router)
fastapi_app.include_router(api_keys_routes.router)
fastapi_app.include_router(companies_routes.router)
fastapi_app.include_router(connectors_routes.router)
fastapi_app.include_router(entities_routes.router)
fastapi_app.include_router(approvals_routes.router)
fastapi_app.include_router(artifacts_routes.router)
fastapi_app.include_router(credentials_routes.router)
fastapi_app.include_router(capabilities_routes.router)
fastapi_app.include_router(knowledge_routes.router)
fastapi_app.include_router(onboarding_routes.router)
fastapi_app.include_router(skills_routes.router)
fastapi_app.include_router(agent_configs_routes.router)
fastapi_app.include_router(agent_assets_routes.router)
fastapi_app.include_router(toolkits_routes.router)
fastapi_app.include_router(evals_routes.router)
fastapi_app.include_router(analytics_routes.router)
fastapi_app.include_router(agent_creation_routes.router)
fastapi_app.include_router(runtime_routes.router)
fastapi_app.include_router(validator_rounds_routes.router)
fastapi_app.include_router(work_items_routes.router)
fastapi_app.include_router(notifications_routes.router)
fastapi_app.include_router(assistant_routes.router)
fastapi_app.include_router(embed_routes.router)


@fastapi_app.get("/health")
async def health_check():
    return {"status": "ok"}


@fastapi_app.get("/openapi-public.json", include_in_schema=False)
async def public_openapi():
    schema = get_openapi(
        title="Automata Public Agent API",
        version="1.0.0",
        description="Public API for listing owned agents, inspecting runtime contracts, and executing /step.",
        routes=fastapi_app.routes,
    )
    public_paths = {
        path: methods
        for path, methods in schema.get("paths", {}).items()
        if path.startswith("/api/v1/agents")
    }
    schema["paths"] = public_paths
    schema["components"] = schema.get("components") or {}
    schema["components"]["securitySchemes"] = {
        "ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "x-api-key"}
    }
    for methods in schema["paths"].values():
        for operation in methods.values():
            if isinstance(operation, dict):
                operation["security"] = [{"ApiKeyAuth": []}]
    return schema


@fastapi_app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, dict) and "error" in detail:
        payload = detail
    elif request.url.path.startswith("/api/v1"):
        payload = error_payload(
            code=str(exc.status_code),
            message=str(detail or exc.status_code),
        )
    else:
        payload = {"detail": detail}
    return JSONResponse(status_code=exc.status_code, content=payload, headers=getattr(exc, "headers", None))


@fastapi_app.on_event("startup")
async def startup_event():
    await ensure_indexes()
    # Migrate existing users: add is_verified and auth_provider fields
    from app.database import users_collection

    await users_collection.update_many(
        {"is_verified": {"$exists": False}},
        {"$set": {"is_verified": True, "auth_provider": "email"}},
    )
    from app.services.workers import job_worker_loop, notification_cleanup_worker_loop, scheduled_work_worker_loop

    asyncio.create_task(scheduled_work_worker_loop())
    asyncio.create_task(notification_cleanup_worker_loop())
    asyncio.create_task(job_worker_loop())


# Wrap FastAPI inside Socket.IO ASGI app so both share the same origin
app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app)
