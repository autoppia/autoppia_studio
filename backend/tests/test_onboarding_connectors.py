import pytest

from app.routes.onboarding import _apply_message, _default_draft


@pytest.mark.parametrize(
    ("prompt", "expected_name", "expected_generation_status"),
    [
        (
            "Empresa EdgeOps usa Cloudflare. Tenemos API token y docs de la API. Necesito revisar DNS records.",
            "Cloudflare",
            "needs_docs",
        ),
        (
            "La empresa CallDesk utiliza Twilio para SMS. Tenemos API key y docs https://www.twilio.com/docs.",
            "Twilio",
            "docs_provided",
        ),
        (
            "Mi soporte usa Zendesk. Tenemos token API pero no tengo OpenAPI URL.",
            "Zendesk",
            "needs_docs",
        ),
        (
            "Usamos Linear para issues. Hay API docs publicas.",
            "Linear",
            "needs_docs",
        ),
        (
            "Usamos Slack para avisos internos. Tenemos bot token.",
            "Slack",
            "needs_docs",
        ),
    ],
)
def test_unknown_systems_become_custom_api_connectors(prompt, expected_name, expected_generation_status):
    draft = _default_draft()

    _apply_message(draft, prompt)

    assert len(draft["connectors"]) == 1
    connector = draft["connectors"][0]
    assert connector["name"] == expected_name
    assert connector["type"] == "api"
    assert connector["provider"] == "custom"
    assert connector["generationStatus"] == expected_generation_status
    assert connector["status"] == "needs_auth"


def test_api_docs_text_does_not_create_knowledge_connector_for_custom_api():
    draft = _default_draft()

    _apply_message(draft, "Usamos Cloudflare. Tenemos docs de la API y API token.")

    connector_names = [connector["name"] for connector in draft["connectors"]]
    assert connector_names == ["Cloudflare"]


def test_known_connectors_are_marked_official():
    draft = _default_draft()

    _apply_message(draft, "Celeris usa SMTP, Telegram, Holded, documentos internos y https://www.bopa.ad/.")

    by_name = {connector["name"]: connector for connector in draft["connectors"]}
    assert by_name["SMTP"]["provider"] == "official"
    assert by_name["Telegram"]["provider"] == "official"
    assert by_name["Holded"]["provider"] == "official"
    assert by_name["Documents"]["provider"] == "official"
    assert by_name["BOPA"]["provider"] == "official"
