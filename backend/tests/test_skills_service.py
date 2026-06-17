from app.services.skills import skill_slug


def test_skill_slug_normalizes_accents_to_ascii():
    assert skill_slug("Descargar PDF último boletín") == "descargar_pdf_ultimo_boletin"
