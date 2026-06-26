from app.services.onboarding_connectors import (
    connector_key,
    custom_web_connector,
    display_name_from_url,
    extract_docs_url,
    has_auth_hint,
    looks_like_api_docs,
    looks_like_docs_url,
    normalized_connector_name,
    url_host,
    web_auth_required,
)


def test_custom_web_connector_describes_browser_discovery_contract():
    connector = custom_web_connector("https://example.com/reports", "Public reports site.")

    assert connector["name"] == "Example"
    assert connector["type"] == "web"
    assert connector["provider"] == "custom"
    assert connector["status"] == "connected"
    assert connector["generationStatus"] == "start_url_provided"
    assert connector["surface"] == "webapp"
    assert connector["authRequired"] is False
    assert connector["discoveryStatus"] == "pending"
    assert connector["discoveryMode"] == "task_scoped"
    assert connector["runtimeRequirements"] == ["browser", "network"]
    assert connector["config"] == {
        "baseUrl": "https://example.com/reports",
        "startUrl": "https://example.com/reports",
    }


def test_custom_web_connector_marks_auth_bound_portals():
    connector = custom_web_connector("https://portal.example.com/login", "Portal privado con usuario y password.")

    assert connector["name"] == "Example"
    assert connector["status"] == "needs_auth"
    assert connector["authRequired"] is True
    assert web_auth_required("tenemos credenciales", "https://example.com") is True


def test_extract_docs_url_prefers_matching_system_then_docs_like_url():
    text = "Base https://example.com y Twilio docs https://www.twilio.com/docs/api."

    assert extract_docs_url(text, "Twilio") == "https://www.twilio.com/docs/api"
    assert extract_docs_url("Portal https://example.com y OpenAPI https://docs.example.com/openapi.json") == "https://docs.example.com/openapi.json"


def test_connector_string_helpers_normalize_names_hosts_and_hints():
    assert connector_key({"type": "api", "name": "Twilio"}) == "api:twilio"
    assert normalized_connector_name("Twilio API Connector") == "twilio"
    assert url_host("https://portal.example.com/reports") == "portal.example.com"
    assert display_name_from_url("https://app.my-erp.example.com") == "My Erp"
    assert looks_like_docs_url("https://developer.example.com/openapi.json") is True
    assert looks_like_api_docs("Tenemos documentación de la API y swagger.") is True
    assert has_auth_hint("Tenemos bot token y API key.") is True
