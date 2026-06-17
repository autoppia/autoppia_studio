from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import urllib.request

BOPA_MONTH_ENDPOINT = "https://bopaazurefunctions.azurewebsites.net/api/GetMonthButlletins"
BOPA_MONTH_CODE = "oEQCEj04L-FHloPFFtfdXyOZozUafYV_uqL6sQdePkF0AzFuZTJP3w=="
BOPA_SUMMARY_BASE_URL = "https://bopadocuments.blob.core.windows.net/bopa-documents/sumaris"


def parse_bopa_date(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def bopa_summary_pdf_url(*, year: int, number: str) -> str:
    prefix = f"{year - 1988:03d}"
    bulletin_number = str(number).strip().zfill(3)
    return f"{BOPA_SUMMARY_BASE_URL}/{prefix}/{prefix}{bulletin_number}.pdf"


def latest_bopa_pdf() -> dict[str, Any]:
    # BOPA's month endpoint accepts a date in the active month. Tomorrow avoids
    # edge cases around late-night UTC publication timestamps.
    query_date = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    api_url = f"{BOPA_MONTH_ENDPOINT}?code={BOPA_MONTH_CODE}&date={query_date}"
    with urllib.request.urlopen(api_url, timeout=30) as response:
        import json

        newsletters = json.loads(response.read().decode("utf-8"))

    now = datetime.now(timezone.utc)
    candidates = [
        item
        for item in newsletters
        if isinstance(item, dict) and item.get("dataPublicacio") and parse_bopa_date(str(item["dataPublicacio"])) <= now
    ]
    if not candidates:
        candidates = [item for item in newsletters if isinstance(item, dict) and item.get("dataPublicacio")]
    if not candidates:
        raise RuntimeError("BOPA API returned no published bulletins")

    latest = max(candidates, key=lambda item: parse_bopa_date(str(item["dataPublicacio"])))
    published = parse_bopa_date(str(latest["dataPublicacio"]))
    pdf_url = bopa_summary_pdf_url(year=published.year, number=str(latest.get("num") or ""))
    request = urllib.request.Request(pdf_url, method="HEAD")
    with urllib.request.urlopen(request, timeout=30) as response:
        content_type = response.headers.get("Content-Type", "")
        content_length = response.headers.get("Content-Length", "")
        if response.status >= 400 or "pdf" not in content_type.lower():
            raise RuntimeError(f"BOPA summary PDF check failed: HTTP {response.status} {content_type}")

    return {
        "apiUrl": api_url,
        "pdfUrl": pdf_url,
        "numBOPA": latest.get("numBOPA", ""),
        "number": latest.get("num", ""),
        "publishedAt": published.isoformat(),
        "isExtra": bool(latest.get("isExtra")),
        "contentType": content_type,
        "contentLength": content_length,
    }
