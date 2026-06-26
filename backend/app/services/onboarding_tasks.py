from __future__ import annotations

import json
import re
import unicodedata
from typing import Any


def extract_urls(text: str) -> list[str]:
    return [url.rstrip(".,;)") for url in re.findall(r"https?://[^\s,)]+", text)]


def extract_tasks(text: str) -> list[str]:
    labelled_tasks: list[str] = []
    for match in re.finditer(
        r"\b(?:task|tarea)\s*:\s*[\"'“”]?(.*?)(?=(?:\n\s*(?:task|tarea)\s*:)|\b(?:pistas?|ayuda|hints?|pasos sugeridos|ruta sugerida)\s*:|$)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        task = match.group(1).strip().strip("\"'“” .")
        if len(task) >= 12:
            labelled_tasks.append(task)
    if labelled_tasks:
        return labelled_tasks[:10]

    normalized = re.sub(r"\s+(\d+[\).:-]\s*)", r"\n\1", text)
    lines = [line.strip(" -\t") for line in normalized.splitlines()]
    numbered_lines = [line for line in lines if re.match(r"^\d+[\).:-]\s*", line)]
    if numbered_lines:
        lines = numbered_lines
    tasks: list[str] = []
    for line in lines:
        cleaned = re.sub(r"^\d+[\).:-]\s*", "", line).strip().strip("\"'“”")
        lower_cleaned = cleaned.lower()
        if len(cleaned) < 18:
            continue
        if any(phrase in lower_cleaned for phrase in ("crear un agent", "crear un agente", "crear una sola task", "crea una sola task", "company:", "website:", "connector:")):
            continue
        if any(word in lower_cleaned for word in ("task", "tarea", "necesito", "quiero", "recibo", "buscar", "encontrar", "consultar", "leer", "resumir", "preparar", "enviar", "responder", "descargar", "descargarse", "descarregar", "baixar", "download", "summar", "find", "prepare", "send", "notify", "read")):
            tasks.append(cleaned)
    if not tasks and any(word in text.lower() for word in ("tasks", "tareas", "automate", "automatizar")):
        chunks = re.split(r"[.;]\s+", text)
        tasks = [chunk.strip() for chunk in chunks if len(chunk.strip()) > 28][:10]
    deduped: list[str] = []
    for task in tasks:
        if task and not any(existing.lower() == task.lower() for existing in deduped):
            deduped.append(task)
    return deduped[:10]


def task_name_from_prompt(prompt: str, fallback_index: int = 1) -> str:
    text = re.sub(r"^\s*\d+[\).:-]\s*", "", str(prompt or "")).strip()
    lower = text.lower()
    if not text:
        return f"Workflow {fallback_index}"
    if "bopa" in lower:
        if any(term in lower for term in ("pdf", "boletin", "butllet", "bulletin", "download", "descargar", "descarreg")):
            return "Download latest BOPA bulletin PDF"
        if any(term in lower for term in ("email", "cliente", "client")):
            return "Summarize BOPA update for client email"
        return "Summarize latest BOPA labor update"
    if any(term in lower for term in ("factura", "invoice")):
        if "holded" in lower and any(term in lower for term in ("email", "respuesta", "response")):
            return "Find Holded invoice and draft reply"
        if "holded" in lower:
            return "Retrieve latest Holded invoice"
        return "Handle client invoice request"
    if any(term in lower for term in ("telegram", "slack", "discord", "teams")):
        if any(term in lower for term in ("urgente", "urgent")):
            return "Send urgent team notification"
        return "Send team notification"
    if any(term in lower for term in ("clasificar", "classify", "nomina", "contrato", "consulta")):
        return "Classify client request"
    if any(term in lower for term in ("document", "documento", "fuente", "source", "knowledge", "conocimiento")):
        return "Answer from internal documents"
    if any(term in lower for term in ("email", "correo")):
        return "Process client email"

    words = re.findall(r"[A-Za-z0-9]+", text)
    title = " ".join(words[:7]).strip()
    if not title:
        return f"Workflow {fallback_index}"
    return title[:1].upper() + title[1:60]


def task_text_without_hints(text: str) -> str:
    marker = re.search(r"\b(?:pistas?|ayuda|hints?|pasos sugeridos|ruta sugerida)\s*(?:para [^:\n]+)?[:\n]", text, flags=re.IGNORECASE)
    return text[: marker.start()] if marker else text


def extract_hint_block(text: str) -> str:
    marker = re.search(r"\b(?:pistas?|ayuda|hints?|pasos sugeridos|ruta sugerida)\s*(?:para [^:\n]+)?[:\n]", text, flags=re.IGNORECASE)
    if not marker:
        return ""
    return text[marker.end() :]


def extract_task_metadata(user_message: str, task_prompt: str = "") -> dict[str, Any]:
    text = str(user_message or "")
    hint_block = extract_hint_block(text)
    hints: list[str] = []
    for line in hint_block.splitlines():
        cleaned = re.sub(r"^\s*(?:[-*]|\d+[\).:-])\s*", "", line).strip()
        if not cleaned:
            continue
        if re.search(r"\b(?:tarea|task)\s+se\s+considera\b", cleaned, flags=re.IGNORECASE):
            break
        hints.append(cleaned)
    if not hints and hint_block:
        hints = [item.strip() for item in re.split(r"\s*(?:;|\n)\s*", hint_block) if len(item.strip()) > 8][:10]

    urls = extract_urls(text)
    start_url = ""
    for url in urls:
        if "bopa.ad" in url.lower():
            start_url = url
            break
    if not start_url and urls:
        start_url = urls[0]

    lower = f"{text}\n{task_prompt}".lower()
    expected_artifacts: list[str] = []
    if "pdf" in lower or "boletin" in lower or "butllet" in lower:
        expected_artifacts.append("pdf_download")

    metadata: dict[str, Any] = {}
    if hints:
        metadata["hints"] = hints[:10]
    if start_url:
        metadata["startUrl"] = start_url
    if expected_artifacts:
        metadata["expectedArtifacts"] = expected_artifacts
    if "bopa.ad" in lower:
        metadata["site"] = "BOPA"
    return metadata


def hint_key(value: str) -> str:
    value = re.sub(r"^\s*(?:[-*]|\d+[\).:-])\s*", "", value)
    normalized = unicodedata.normalize("NFKD", value.lower())
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9:/.-]+", " ", ascii_text).strip(" .")


def merge_task_metadata(task: dict[str, Any], metadata: dict[str, Any]) -> None:
    if not metadata:
        return
    existing = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    merged = dict(existing)
    if metadata.get("hints"):
        current_hints = [str(item) for item in merged.get("hints", []) if item] if isinstance(merged.get("hints"), list) else []
        seen_hint_keys = {hint_key(item) for item in current_hints}
        for hint in metadata["hints"]:
            key = hint_key(str(hint))
            if hint and key not in seen_hint_keys:
                current_hints.append(hint)
                seen_hint_keys.add(key)
        merged["hints"] = current_hints[:10]
    for key, value in metadata.items():
        if key == "hints":
            continue
        if value not in ("", None, [], {}):
            merged[key] = value
    task["metadata"] = merged


def same_task_intent(existing: dict[str, Any], prompt: str, metadata: dict[str, Any]) -> bool:
    existing_prompt = str(existing.get("prompt") or "").lower()
    prompt_lower = str(prompt or "").lower()
    existing_metadata = existing.get("metadata") if isinstance(existing.get("metadata"), dict) else {}
    existing_artifacts = existing_metadata.get("expectedArtifacts") if isinstance(existing_metadata.get("expectedArtifacts"), list) else []
    artifacts = metadata.get("expectedArtifacts") if isinstance(metadata.get("expectedArtifacts"), list) else []
    both_pdf = (
        any("pdf" in str(item).lower() for item in existing_artifacts)
        or "pdf" in existing_prompt
        or "pdf" in str(existing.get("successCriteria") or "").lower()
    ) and (any("pdf" in str(item).lower() for item in artifacts) or "pdf" in prompt_lower)
    both_bopa = (
        existing_metadata.get("site") == "BOPA"
        or "bopa" in existing_prompt
        or "bopa.ad" in json.dumps(existing_metadata, ensure_ascii=False).lower()
    ) and (metadata.get("site") == "BOPA" or "bopa" in prompt_lower or "bopa.ad" in json.dumps(metadata, ensure_ascii=False).lower())
    latest_bulletin = any(term in existing_prompt for term in ("bolet", "butllet", "bulletin")) or any(term in prompt_lower for term in ("bolet", "butllet", "bulletin"))
    return bool(both_pdf and both_bopa and latest_bulletin)
