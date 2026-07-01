from __future__ import annotations

import os
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


class _UiSnapshotParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.headings: list[str] = []
        self.buttons: list[dict[str, str]] = []
        self.inputs: list[dict[str, str]] = []
        self.links: list[dict[str, str]] = []
        self.forms: list[dict[str, str]] = []
        self.texts: list[str] = []
        self._tag_stack: list[str] = []
        self._capture_link: dict[str, str] | None = None
        self._capture_button: dict[str, str] | None = None
        self._capture_title = False
        self._capture_heading: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = {key.lower(): str(value or "") for key, value in attrs}
        tag = tag.lower()
        self._tag_stack.append(tag)
        if tag == "title":
            self._capture_title = True
        elif tag in {"h1", "h2", "h3"}:
            self._capture_heading = tag
        elif tag == "button":
            self._capture_button = {
                "label": attrs_map.get("aria-label") or attrs_map.get("title") or attrs_map.get("id") or "",
                "id": attrs_map.get("id", ""),
                "type": attrs_map.get("type", ""),
            }
        elif tag == "input":
            self.inputs.append(
                {
                    "id": attrs_map.get("id", ""),
                    "name": attrs_map.get("name", ""),
                    "type": attrs_map.get("type", ""),
                    "placeholder": attrs_map.get("placeholder", ""),
                    "ariaLabel": attrs_map.get("aria-label", ""),
                }
            )
        elif tag == "textarea":
            self.inputs.append(
                {
                    "id": attrs_map.get("id", ""),
                    "name": attrs_map.get("name", ""),
                    "type": "textarea",
                    "placeholder": attrs_map.get("placeholder", ""),
                    "ariaLabel": attrs_map.get("aria-label", ""),
                }
            )
        elif tag == "select":
            self.inputs.append(
                {
                    "id": attrs_map.get("id", ""),
                    "name": attrs_map.get("name", ""),
                    "type": "select",
                    "placeholder": "",
                    "ariaLabel": attrs_map.get("aria-label", ""),
                }
            )
        elif tag == "a":
            self._capture_link = {
                "label": attrs_map.get("aria-label") or attrs_map.get("title") or "",
                "href": attrs_map.get("href", ""),
            }
        elif tag == "form":
            self.forms.append(
                {
                    "id": attrs_map.get("id", ""),
                    "name": attrs_map.get("name", ""),
                    "action": attrs_map.get("action", ""),
                    "method": attrs_map.get("method", ""),
                }
            )

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._capture_title = False
        elif tag in {"h1", "h2", "h3"}:
            self._capture_heading = None
        elif tag == "button" and self._capture_button is not None:
            self.buttons.append(self._capture_button)
            self._capture_button = None
        elif tag == "a" and self._capture_link is not None:
            self.links.append(self._capture_link)
            self._capture_link = None
        if self._tag_stack:
            self._tag_stack.pop()

    def handle_data(self, data: str) -> None:
        text = " ".join(str(data or "").split())
        if not text:
            return
        if self._capture_title:
            self.title = " ".join([self.title, text]).strip()
        if self._capture_heading:
            self.headings.append(text)
        if self._capture_button is not None:
            self._capture_button["label"] = " ".join([self._capture_button.get("label", ""), text]).strip()
        if self._capture_link is not None:
            self._capture_link["label"] = " ".join([self._capture_link.get("label", ""), text]).strip()
        if self._tag_stack and self._tag_stack[-1] not in {"script", "style"}:
            self.texts.append(text)


def collect_web_snapshot_from_html(*, url: str, html: str, max_items: int = 80) -> dict[str, Any]:
    parser = _UiSnapshotParser()
    parser.feed(html or "")
    visible_text = []
    seen: set[str] = set()
    for item in parser.texts:
        if item.lower() in seen:
            continue
        seen.add(item.lower())
        visible_text.append(item)
        if len(visible_text) >= max_items:
            break
    return {
        "url": url,
        "collectorMode": "html",
        "title": parser.title,
        "headings": parser.headings[:30],
        "buttons": [item for item in parser.buttons if any(item.values())][:max_items],
        "inputs": [item for item in parser.inputs if any(item.values())][:max_items],
        "links": [item for item in parser.links if item.get("label") or item.get("href")][:max_items],
        "forms": [item for item in parser.forms if any(item.values())][:30],
        "visibleText": visible_text,
        "stats": {
            "buttonCount": len(parser.buttons),
            "inputCount": len(parser.inputs),
            "linkCount": len(parser.links),
            "formCount": len(parser.forms),
            "textCount": len(parser.texts),
        },
    }


def _failed_snapshot(url: str, *, mode: str, error: str) -> dict[str, Any]:
    return {
        "url": url,
        "collectorMode": mode,
        "status": "failed",
        "error": error,
        "title": "",
        "headings": [],
        "buttons": [],
        "inputs": [],
        "links": [],
        "forms": [],
        "visibleText": [],
        "screenshots": [],
        "routes": [],
        "stats": {},
    }


def collect_web_snapshot_html(url: str, *, timeout_seconds: float = 2.0, max_bytes: int = 800_000) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "Autoppia-ICA-WebSourceCollector/0.1"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            content_type = str(response.headers.get("content-type") or "")
            raw = response.read(max_bytes)
        encoding = "utf-8"
        if "charset=" in content_type:
            encoding = content_type.split("charset=", 1)[1].split(";", 1)[0].strip() or "utf-8"
        html = raw.decode(encoding, errors="replace")
        snapshot = collect_web_snapshot_from_html(url=url, html=html)
        snapshot["status"] = "ok"
        snapshot["contentType"] = content_type
        snapshot.setdefault("screenshots", [])
        snapshot.setdefault("routes", [])
        return snapshot
    except (OSError, URLError, TimeoutError) as exc:
        return _failed_snapshot(url, mode="html", error=f"{type(exc).__name__}: {exc}")


def _playwright_eval_script() -> str:
    return """
    () => {
      const text = (el) => (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
      const attr = (el, name) => el.getAttribute(name) || '';
      const topText = Array.from(document.body ? document.body.querySelectorAll('h1,h2,h3,p,li,label,span,button,a') : [])
        .map(text).filter(Boolean).slice(0, 120);
      return {
        title: document.title || '',
        headings: Array.from(document.querySelectorAll('h1,h2,h3')).map(text).filter(Boolean).slice(0, 40),
        buttons: Array.from(document.querySelectorAll('button,[role="button"],input[type="button"],input[type="submit"]')).map((el) => ({
          label: text(el) || attr(el, 'aria-label') || attr(el, 'title') || attr(el, 'value') || attr(el, 'id'),
          id: attr(el, 'id'),
          type: attr(el, 'type') || attr(el, 'role')
        })).filter((item) => item.label || item.id).slice(0, 100),
        inputs: Array.from(document.querySelectorAll('input,textarea,select')).map((el) => ({
          id: attr(el, 'id'),
          name: attr(el, 'name'),
          type: el.tagName.toLowerCase() === 'select' ? 'select' : (attr(el, 'type') || el.tagName.toLowerCase()),
          placeholder: attr(el, 'placeholder'),
          ariaLabel: attr(el, 'aria-label')
        })).filter((item) => item.id || item.name || item.placeholder || item.ariaLabel).slice(0, 100),
        links: Array.from(document.querySelectorAll('a[href]')).map((el) => ({
          label: text(el) || attr(el, 'aria-label') || attr(el, 'title'),
          href: attr(el, 'href')
        })).filter((item) => item.label || item.href).slice(0, 100),
        forms: Array.from(document.querySelectorAll('form')).map((el) => ({
          id: attr(el, 'id'),
          name: attr(el, 'name'),
          action: attr(el, 'action'),
          method: attr(el, 'method')
        })).slice(0, 40),
        visibleText: Array.from(new Set(topText)).slice(0, 100),
        route: location.href
      };
    }
    """


def collect_web_snapshot_browser(url: str, *, timeout_seconds: float = 6.0, screenshot: bool = False) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return _failed_snapshot(url, mode="browser", error=f"playwright_unavailable:{type(exc).__name__}: {exc}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1365, "height": 900})
            page.goto(url, wait_until="domcontentloaded", timeout=int(timeout_seconds * 1000))
            try:
                page.wait_for_load_state("networkidle", timeout=1500)
            except Exception:
                pass
            data = page.evaluate(_playwright_eval_script())
            screenshots: list[dict[str, Any]] = []
            if screenshot:
                out_dir = Path(tempfile.gettempdir()) / "ica_web_snapshots"
                out_dir.mkdir(parents=True, exist_ok=True)
                safe_name = "".join(ch if ch.isalnum() else "_" for ch in url)[:80]
                path = out_dir / f"{safe_name}.png"
                page.screenshot(path=str(path), full_page=False)
                screenshots.append({"path": str(path), "kind": "viewport", "width": 1365, "height": 900})
            browser.close()
        stats = {
            "buttonCount": len(data.get("buttons") or []),
            "inputCount": len(data.get("inputs") or []),
            "linkCount": len(data.get("links") or []),
            "formCount": len(data.get("forms") or []),
            "textCount": len(data.get("visibleText") or []),
        }
        return {
            "url": url,
            "collectorMode": "browser",
            "status": "ok",
            "title": data.get("title") or "",
            "headings": data.get("headings") or [],
            "buttons": data.get("buttons") or [],
            "inputs": data.get("inputs") or [],
            "links": data.get("links") or [],
            "forms": data.get("forms") or [],
            "visibleText": data.get("visibleText") or [],
            "routes": [data.get("route") or url],
            "screenshots": screenshots,
            "stats": stats,
        }
    except Exception as exc:
        return _failed_snapshot(url, mode="browser", error=f"{type(exc).__name__}: {exc}")


def collect_web_snapshot(
    url: str,
    *,
    mode: str | None = None,
    timeout_seconds: float = 2.0,
    max_bytes: int = 800_000,
    screenshot: bool | None = None,
) -> dict[str, Any]:
    collector_mode = (mode or os.getenv("AUTOPPIA_ICA_WEB_COLLECTOR") or "html").strip().lower()
    wants_screenshot = bool(screenshot) if screenshot is not None else os.getenv("AUTOPPIA_ICA_WEB_COLLECTOR_SCREENSHOT", "").lower() in {"1", "true", "yes"}
    if collector_mode == "browser":
        return collect_web_snapshot_browser(url, timeout_seconds=max(timeout_seconds, 4.0), screenshot=wants_screenshot)
    if collector_mode == "auto":
        browser = collect_web_snapshot_browser(url, timeout_seconds=max(timeout_seconds, 4.0), screenshot=wants_screenshot)
        if browser.get("status") == "ok":
            return browser
        html = collect_web_snapshot_html(url, timeout_seconds=timeout_seconds, max_bytes=max_bytes)
        html["browserFallbackError"] = browser.get("error", "")
        html["collectorMode"] = "auto_html_fallback"
        return html
    return collect_web_snapshot_html(url, timeout_seconds=timeout_seconds, max_bytes=max_bytes)


def web_snapshot_material(*, name: str, url: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    snapshot = collect_web_snapshot(url)
    return {
        "kind": "website_snapshot",
        "name": f"{name} UI snapshot".strip(),
        "url": url,
        "content": "\n".join(snapshot.get("visibleText") or [])[:20_000],
        "metadata": {
            **(metadata or {}),
            "collector": "ica.web_source_collector",
            "snapshot": snapshot,
        },
    }
