import pytest

from app.routes.onboarding import _apply_message, _default_draft, _ensure_extracted_tasks, _extract_tasks, _normalize_custom_connectors, _normalize_connector_duplicates


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


def test_bopa_pdf_prompt_keeps_hints_as_task_metadata_not_extra_tasks():
    draft = _default_draft()
    prompt = """Quiero crear un agent para BOPA, el sitio oficial del Govern d'Andorra.

    Company: BOPA
    Website: https://www.bopa.ad/
    Connector: web publico, sin login.

    Crea una sola task:
    "Descargarse el pdf del ultimo boletin oficial."

    Pistas para hacer la tarea:
    1. Entrar en https://www.bopa.ad/
    2. Ir a https://www.bopa.ad/Butlletins
    3. Encontrar el boletin mas reciente, normalmente el primero o el de fecha mas nueva.
    4. Abrir ese boletin.
    5. Descargar el PDF del boletin oficial.
    6. La tarea se considera correcta si el PDF del ultimo boletin queda descargado o si el agent devuelve el enlace directo al PDF descargable.
    """

    _apply_message(draft, prompt)
    _ensure_extracted_tasks(draft, prompt)

    assert draft["company"]["name"] == "BOPA"
    assert draft["agent"]["websiteUrl"] == "https://www.bopa.ad/"
    assert [connector["name"] for connector in draft["connectors"]] == ["BOPA"]
    assert draft["connectors"][0]["type"] == "bopa"
    bopa_plan = next(item for item in draft["automationPlan"] if item.get("toolName") == "bopa.latest_bulletin_pdf")
    assert bopa_plan["strategy"] == "structured_api_tool"
    assert len(draft["tasks"]) == 1
    task = draft["tasks"][0]
    assert task["name"] == "Download latest BOPA bulletin PDF"
    assert "Descargarse el pdf" in task["prompt"]
    assert task["metadata"]["startUrl"] == "https://www.bopa.ad/"
    assert task["metadata"]["expectedArtifacts"] == ["pdf_download"]
    assert "https://www.bopa.ad/Butlletins" in task["metadata"]["hints"][1]


def test_onboarding_discovery_scope_can_be_broad_without_adding_tasks():
    draft = _default_draft()
    prompt = """
    Company: BOPA
    Website: https://www.bopa.ad/
    Task: descargarse el pdf del ultimo boletin oficial.
    Quiero que auto discover mas tools y skills utiles de BOPA, no solo esta task.
    """

    _apply_message(draft, prompt)
    _ensure_extracted_tasks(draft, prompt)

    assert draft["capabilityDiscovery"]["mode"] == "broad_autodiscovery"
    assert any(item.get("strategy") == "broad_autodiscovery" for item in draft["automationPlan"])
    assert len(draft["tasks"]) == 1


def test_bopa_public_api_hint_does_not_create_custom_api_connector():
    draft = _default_draft()

    _apply_message(
        draft,
        """
        Company: BOPA
        Website: https://www.bopa.ad/
        Task: descargarse el pdf del ultimo boletin oficial.
        Si descubres una API publica o URLs directas de PDFs, usa HTTP deterministico.
        """,
    )
    _ensure_extracted_tasks(draft, draft["company"]["description"])

    assert [(connector["name"], connector["type"]) for connector in draft["connectors"]] == [("BOPA", "bopa")]


def test_new_public_web_url_creates_custom_web_connector():
    draft = _default_draft()

    prompt = """
    Company: ExampleCo
    Website: https://example.com/reports
    Task: descargar el ultimo PDF de reportes publicos.
    """
    _apply_message(draft, prompt)
    _ensure_extracted_tasks(draft, prompt)

    connector = draft["connectors"][0]
    assert connector["type"] == "web"
    assert connector["provider"] == "custom"
    assert connector["status"] == "connected"
    assert connector["surface"] == "webapp"
    assert connector["discoveryStatus"] == "pending"
    assert connector["runtimeRequirements"] == ["browser", "network"]
    assert connector["config"]["baseUrl"] == "https://example.com/reports"
    assert connector["config"]["startUrl"] == "https://example.com/reports"
    assert draft["agent"]["websiteUrl"] == "https://example.com/reports"


def test_public_api_hint_for_new_web_does_not_invent_api_or_documents_connector():
    draft = _default_draft()

    prompt = """
    Company: ReportsCo
    Website: https://example.com/reports
    Task: descargar el ultimo PDF publico de reportes.
    Si hay API publica, usa HTTP deterministico.
    """
    _apply_message(draft, prompt)
    _ensure_extracted_tasks(draft, prompt)

    assert [(connector["name"], connector["type"], connector["provider"]) for connector in draft["connectors"]] == [
        ("Example", "web", "custom")
    ]


def test_speculative_same_host_api_connector_is_removed_without_user_docs_url():
    draft = _default_draft()
    prompt = """
    Company: ReportsCo
    Website: https://example.com/reports
    Task: descargar el ultimo PDF publico de reportes.
    Si hay API publica, usa HTTP deterministico.
    """
    _apply_message(draft, prompt)
    draft["connectors"].append(
        {
            "name": "ReportsCo Public API",
            "type": "api",
            "provider": "custom",
            "status": "not_connected",
            "config": {"baseUrl": "https://example.com", "docsUrl": "https://example.com/docs"},
        }
    )

    _normalize_custom_connectors(draft, prompt)
    _normalize_connector_duplicates(draft)

    assert [(connector["name"], connector["type"]) for connector in draft["connectors"]] == [("Example", "web")]


def test_new_private_web_connector_asks_for_auth_context():
    draft = _default_draft()

    prompt = """
    Company: PortalCo
    Website: https://portal.example.com
    Task: entrar al portal privado y descargar la ultima factura.
    Necesita login con usuario y password.
    """
    _apply_message(draft, prompt)
    _ensure_extracted_tasks(draft, prompt)

    connector = draft["connectors"][0]
    assert connector["type"] == "web"
    assert connector["provider"] == "custom"
    assert connector["status"] == "needs_auth"
    assert connector["authRequired"] is True
    assert len(draft["connectors"]) == 1
    assert any("Example" in question for question in draft["questions"])
