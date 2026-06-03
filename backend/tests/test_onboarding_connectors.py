import pytest

from app.routes.onboarding import _apply_message, _default_draft, _ensure_extracted_tasks, _extract_tasks


@pytest.mark.parametrize(
    ("prompt", "expected_name", "expected_generation_status"),
    [
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


@pytest.mark.parametrize(
    ("prompt", "expected_name", "expected_type"),
    [
        ("Empresa EdgeOps usa Cloudflare. Tenemos API token y docs de la API. Necesito revisar DNS records.", "Cloudflare", "cloudflare"),
        ("Usamos Linear para issues. Hay API docs publicas.", "Linear", "linear"),
        ("Usamos Slack para avisos internos. Tenemos bot token.", "Slack", "slack"),
        ("Usamos GitHub, Google Drive y Postgres para operaciones.", "GitHub", "github"),
    ],
)
def test_ported_connectors_are_official(prompt, expected_name, expected_type):
    draft = _default_draft()

    _apply_message(draft, prompt)

    by_name = {connector["name"]: connector for connector in draft["connectors"]}
    assert by_name[expected_name]["type"] == expected_type
    assert by_name[expected_name]["provider"] == "official"
    assert by_name[expected_name]["generationStatus"] == "autoppia_supported"


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


def test_internal_documents_do_not_become_custom_api_connector():
    draft = _default_draft()

    _apply_message(
        draft,
        "Celeris usa Gmail, SMTP, Holded, Telegram, BOPA web y documentos internos de conocimiento.",
    )

    connectors = {(connector["name"], connector["type"], connector["provider"]) for connector in draft["connectors"]}
    assert ("Documents", "knowledge", "official") in connectors
    assert not any(
        connector["type"] == "api" and "document" in connector["name"].lower()
        for connector in draft["connectors"]
    )


def test_extract_tasks_keeps_consultar_resumir_task():
    tasks = _extract_tasks(
        """Tasks:
        1. Leer un email de un cliente que pide su ultima factura, buscarla en Holded y preparar respuesta por email.
        2. Consultar el BOPA mas reciente, resumir novedades laborales y preparar email para un cliente.
        3. Buscar un cliente en Holded y recuperar su ultima factura.
        4. Enviar un aviso por Telegram al equipo cuando llegue una solicitud urgente.
        5. Responder una consulta laboral usando documentos internos y citando la fuente.
        """
    )

    assert len(tasks) == 5
    assert any("BOPA" in task for task in tasks)


def test_extracted_tasks_get_descriptive_names():
    draft = _default_draft()

    _ensure_extracted_tasks(
        draft,
        """Tasks:
        1. Leer el ultimo BOPA sobre temas laborales, resumirlo y preparar un email para un cliente.
        2. Encontrar la ultima factura de un cliente en Holded y preparar una respuesta por email.
        """,
    )

    names = [task["name"] for task in draft["tasks"]]
    assert names == [
        "Summarize BOPA update for client email",
        "Find Holded invoice and draft reply",
    ]
