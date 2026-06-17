#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from typing import Any

import requests


def request_json(method: str, url: str, *, headers: dict[str, str] | None = None, **kwargs: Any) -> tuple[int, dict[str, Any]]:
    response = requests.request(method, url, headers=headers, timeout=45, **kwargs)
    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text[:500]}
    return response.status_code, payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test the Automata public Agent API.")
    parser.add_argument("--base-url", default=os.getenv("AUTOMATA_API_BASE_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--email", default=os.getenv("AUTOMATA_SMOKE_EMAIL", "demo@autoppia.com"))
    parser.add_argument("--agent-id", default=os.getenv("AUTOMATA_SMOKE_AGENT_ID", "2627e359-cb90-4f65-a9ab-22a70e7ffead"))
    parser.add_argument("--prompt", default=os.getenv("AUTOMATA_SMOKE_PROMPT", "Leer el ultimo BOPA sobre temas laborales, resumirlo y preparar un email para un cliente."))
    parser.add_argument("--api-key", default=os.getenv("AUTOMATA_API_KEY", ""))
    parser.add_argument("--admin-key", default=os.getenv("AUTOMATA_API_KEY_ADMIN_TOKEN", ""))
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    created_key_id = ""
    api_key = args.api_key

    try:
        if not api_key:
            headers = {"x-admin-key": args.admin_key} if args.admin_key else {}
            status, payload = request_json(
                "POST",
                f"{base}/api-keys",
                headers=headers,
                json={"email": args.email, "name": "Automata API smoke test"},
            )
            print(f"create_key {status}")
            if status >= 300:
                print(payload)
                return 1
            created_key_id = str(payload["apiKey"]["id"])
            api_key = str(payload["apiKey"]["key"])

        headers = {"x-api-key": api_key}
        checks: list[tuple[str, int]] = []

        for name, path in (
            ("list_agents", "/api/v1/agents"),
            ("get_agent", f"/api/v1/agents/{args.agent_id}"),
            ("list_skills", f"/api/v1/agents/{args.agent_id}/skills"),
            ("runtime_contract", f"/api/v1/agents/{args.agent_id}/runtime-contract"),
        ):
            status, payload = request_json("GET", f"{base}{path}", headers=headers)
            checks.append((name, status))
            print(f"{name} {status}")
            if status >= 300:
                print(payload)
                return 1

        state: dict[str, Any] = {}
        current_url = "about:blank"
        final: dict[str, Any] | None = None
        for step_index in range(25):
            status, payload = request_json(
                "POST",
                f"{base}/api/v1/agents/{args.agent_id}/step",
                headers=headers,
                json={"prompt": args.prompt, "url": current_url, "step_index": step_index, "state_in": state},
            )
            print(
                f"step_{step_index} {status} done={payload.get('done')} "
                f"mode={payload.get('executionMode')} tools={[call.get('name') for call in payload.get('tool_calls', [])]}"
            )
            if status >= 300:
                print(payload)
                return 1
            state = payload.get("state_out") or state
            calls = payload.get("tool_calls") or []
            if calls and calls[0].get("name") == "browser.navigate":
                current_url = calls[0].get("arguments", {}).get("url", current_url)
            if payload.get("done"):
                final = payload
                break

        if not final:
            print("step loop did not finish")
            return 1
        print(f"final_content_len {len(final.get('content') or '')}")
        print(f"capability_match {(final.get('capability_match') or {}).get('name', '')}")
        return 0
    finally:
        if created_key_id:
            headers = {"x-admin-key": args.admin_key} if args.admin_key else {}
            status, _ = request_json("DELETE", f"{base}/api-keys/{created_key_id}", headers=headers)
            print(f"delete_key {status}")


if __name__ == "__main__":
    sys.exit(main())
