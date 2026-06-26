from __future__ import annotations

import re
from typing import Any

from app.services.onboarding_tasks import extract_urls


AUTH_WEB_HINTS = (
    "login",
    "sign in",
    "signin",
    "log in",
    "private",
    "privado",
    "privada",
    "portal",
    "usuario",
    "password",
    "contraseña",
    "credenciales",
    "auth",
)


def connector_key(connector: dict[str, Any]) -> str:
    return f"{connector.get('type')}:{str(connector.get('name') or '').lower()}"


def normalized_connector_name(value: str) -> str:
    return re.sub(r"\b(api|connector|integration|toolkit)\b", "", value.lower()).strip(" -_:")


def url_host(url: str) -> str:
    return re.sub(r"^https?://", "", str(url or "").strip(), flags=re.IGNORECASE).split("/", 1)[0].strip().lower()


def display_name_from_url(url: str) -> str:
    host = url_host(url)
    if not host:
        return "Custom Web"
    parts = [part for part in host.split(".") if part and part not in {"www", "app", "portal"}]
    base = parts[0] if parts else host
    return re.sub(r"[^a-zA-Z0-9]+", " ", base).strip().title() or host


def web_auth_required(text: str, url: str = "") -> bool:
    lower = f"{text}\n{url}".lower()
    return any(hint in lower for hint in AUTH_WEB_HINTS)


def custom_web_connector(url: str, user_message: str = "") -> dict[str, Any]:
    auth_required = web_auth_required(user_message, url)
    host = url_host(url)
    return {
        "name": display_name_from_url(url),
        "type": "web",
        "category": "web",
        "description": f"Custom web connector for {host or url}. Automata will discover whether this is best automated through HTTP/API tools or browser trajectories.",
        "config": {"baseUrl": url, "startUrl": url},
        "status": "needs_auth" if auth_required else "connected",
        "provider": "custom",
        "generationStatus": "start_url_provided",
        "surface": "webapp",
        "authRequired": auth_required,
        "discoveryStatus": "pending",
        "discoveryMode": "task_scoped",
        "runtimeRequirements": ["browser", "network"],
    }


def looks_like_docs_url(url: str) -> bool:
    lower = str(url or "").lower()
    return any(token in lower for token in ("docs", "api-docs", "openapi", "swagger", "developer", "developers"))


def looks_like_api_docs(text: str) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in ("api docs", "docs de la api", "documentacion de la api", "documentación de la api", "swagger", "openapi"))


def extract_docs_url(text: str, system_name: str = "") -> str:
    urls = extract_urls(text)
    if not urls:
        return ""
    if system_name:
        lowered = system_name.lower()
        for url in urls:
            if lowered in url.lower():
                return url
    for url in urls:
        if any(token in url.lower() for token in ("docs", "api", "openapi", "swagger", "developer")):
            return url
    return urls[0]


def has_auth_hint(text: str) -> bool:
    return any(term in text.lower() for term in ("api token", "token", "api key", "auth", "oauth", "credential", "credencial", "bot token"))
