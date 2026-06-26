from app.services.onboarding_tasks import extract_task_metadata
from app.services.onboarding_tasks import extract_tasks
from app.services.onboarding_tasks import hint_key
from app.services.onboarding_tasks import merge_task_metadata
from app.services.onboarding_tasks import same_task_intent
from app.services.onboarding_tasks import task_name_from_prompt
from app.services.onboarding_tasks import task_text_without_hints


def test_extract_tasks_keeps_labelled_tasks_before_hints():
    text = """
    Tarea: Descargar el último boletín BOPA en PDF y guardarlo como artefacto.
    Tarea: Preparar un resumen para enviar al cliente sin enviar el email.
    Pistas:
    - abrir https://www.bopa.ad/
    """

    assert extract_tasks(task_text_without_hints(text)) == [
        "Descargar el último boletín BOPA en PDF y guardarlo como artefacto",
        "Preparar un resumen para enviar al cliente sin enviar el email",
    ]


def test_task_metadata_extracts_hints_start_url_site_and_expected_artifacts():
    metadata = extract_task_metadata(
        """
        Tarea: Descargar el boletín.
        Pistas:
        - Entrar en https://www.bopa.ad/bopa/consulta
        - Descargar PDF del boletín más reciente
        """
    )

    assert metadata["site"] == "BOPA"
    assert metadata["startUrl"] == "https://www.bopa.ad/bopa/consulta"
    assert metadata["expectedArtifacts"] == ["pdf_download"]
    assert metadata["hints"] == [
        "Entrar en https://www.bopa.ad/bopa/consulta",
        "Descargar PDF del boletín más reciente",
    ]


def test_task_name_from_prompt_uses_business_specific_names():
    assert task_name_from_prompt("Descargar el último boletín BOPA en PDF") == "Download latest BOPA bulletin PDF"
    assert task_name_from_prompt("Buscar factura en Holded y preparar respuesta por email") == "Find Holded invoice and draft reply"
    assert task_name_from_prompt("", 4) == "Workflow 4"


def test_merge_task_metadata_dedupes_hints_and_preserves_existing_metadata():
    task = {"metadata": {"hints": ["Abrir página inicial"], "site": "BOPA"}}
    merge_task_metadata(
        task,
        {
            "hints": ["1. Abrir pagina inicial", "Descargar PDF"],
            "expectedArtifacts": ["pdf_download"],
        },
    )

    assert task["metadata"]["hints"] == ["Abrir página inicial", "Descargar PDF"]
    assert task["metadata"]["site"] == "BOPA"
    assert task["metadata"]["expectedArtifacts"] == ["pdf_download"]
    assert hint_key("1. Abrir página inicial") == "abrir pagina inicial"


def test_same_task_intent_matches_bopa_pdf_latest_bulletin():
    existing = {
        "prompt": "Descargar el último boletín BOPA en PDF",
        "metadata": {"site": "BOPA", "expectedArtifacts": ["pdf_download"]},
    }

    assert same_task_intent(existing, "Baixar el butlletí BOPA PDF més recent", {"site": "BOPA", "expectedArtifacts": ["pdf_download"]}) is True
    assert same_task_intent(existing, "Responder un correo de cliente", {}) is False
