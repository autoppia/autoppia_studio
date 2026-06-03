import json

from pathlib import Path

from app.harvester.claude_cli import ACTION_SCHEMA, _build_prompt, _compact_connector, parse_harvester_output, redact_actions, redact_text
from app.services.iwa_modeling import canonical_tool_trajectory, iwa_task_payload


def test_parse_harvester_output_prefers_tool_trajectory():
    stdout = json.dumps(
        {
            "result": json.dumps(
                {
                    "success": True,
                    "confidence": 0.82,
                    "summary": "Logged in.",
                    "trajectory": [
                        {"name": "navigate", "arguments": {"url": "https://example.com"}},
                        {"name": "click", "arguments": {"selector": {"type": "attributeValueSelector", "attribute": "id", "value": "save"}}},
                    ],
                    "evidence": ["url reached"],
                }
            )
        }
    )

    result = parse_harvester_output(stdout)

    assert result.success is True
    assert result.confidence == 0.82
    assert result.actions[0]["action"] == "browser.navigate"
    assert result.trajectory[0]["name"] == "navigate"
    assert result.trajectory[1]["name"] == "click"
    assert result.evidence == ["url reached"]


def test_parse_harvester_output_accepts_claude_structured_output():
    stdout = json.dumps(
        {
            "type": "result",
            "structured_output": {
                "success": True,
                "confidence": 1,
                "summary": "ok",
                "trajectory": [],
            },
        }
    )

    result = parse_harvester_output(stdout)

    assert result.success is True
    assert result.confidence == 1
    assert result.actions == []


def test_redact_actions_replaces_raw_secret_values_with_placeholders():
    actions = [
        {"action": "browser.input", "args": {"text": "Passw0rd!"}},
        {"action": "api.call", "args": {"headers": {"Authorization": "Bearer sk_live_123"}}},
    ]

    redacted = redact_actions(
        actions,
        {
            "{{credential.smtp.password}}": "Passw0rd!",
            "{{credential.api.apiKey}}": "sk_live_123",
        },
    )

    assert redacted[0]["args"]["text"] == "{{credential.smtp.password}}"
    assert redacted[1]["args"]["headers"]["Authorization"] == "Bearer {{credential.api.apiKey}}"


def test_redact_text_masks_secrets_in_logs():
    text = "login with Passw0rd! and token sk_live_123"

    assert redact_text(text, {"{{password}}": "Passw0rd!", "{{apiKey}}": "sk_live_123"}) == "login with {{password}} and token {{apiKey}}"


def test_compact_connector_masks_secret_config_fields():
    secrets = {}
    compact = _compact_connector(
        {
            "connectorId": "smtp-1",
            "name": "SMTP",
            "type": "smtp",
            "config": {"smtpServer": "smtp.example.com", "password": "raw-pass", "apiKey": "raw-key"},
        },
        {},
        secrets,
    )

    assert compact["config"]["smtpServer"] == "smtp.example.com"
    assert compact["config"]["password"] == "{{credential.smtp-1.config.password}}"
    assert compact["config"]["apiKey"] == "{{credential.smtp-1.config.apiKey}}"
    assert secrets["{{credential.smtp-1.config.password}}"] == "raw-pass"
    assert secrets["{{credential.smtp-1.config.apiKey}}"] == "raw-key"


def test_harvester_prompt_forbids_real_write_actions():
    prompt = _build_prompt(task_file=Path("/tmp/task.json"), output_file=Path("/tmp/result.json"))

    assert "never execute real write/send/delete/payment actions" in prompt
    assert "do not actually send SMTP/Gmail/Telegram messages" in prompt
    assert "api.human_approval" in prompt


def test_harvester_schema_requires_tool_trajectory_not_actions():
    assert "trajectory" in ACTION_SCHEMA["required"]
    assert "actions" not in ACTION_SCHEMA["required"]


def test_iwa_task_payload_matches_subnet_clean_task_shape():
    payload = iwa_task_payload(
        {
            "taskId": "task-1",
            "prompt": "Add an event",
            "metadata": {
                "iwaProjectId": "autocalendar",
                "iwaStartUrl": "http://localhost:8011/?seed=7",
                "specifications": {"browser": "chromium"},
            },
        },
        {"websiteUrl": "http://fallback"},
    )

    assert payload["id"] == "task-1"
    assert payload["web_project_id"] == "autocalendar"
    assert payload["url"] == "http://localhost:8011/?seed=7"
    assert payload["prompt"] == "Add an event"
    assert payload["original_prompt"] == "Add an event"
    assert "tests" not in payload
    assert "use_case" not in payload


def test_canonical_tool_trajectory_accepts_internal_and_subnet_actions():
    trajectory = canonical_tool_trajectory(
        [
            {"action": "browser.navigate", "args": {"url": "http://localhost:8011/events?X-WebAgent-Id=abc"}},
            {"name": "click", "arguments": {"selector": {"type": "attributeValueSelector", "attribute": "id", "value": "save"}}},
        ],
        task_url="http://localhost:8011/?seed=7",
    )

    assert trajectory[0]["name"] == "navigate"
    assert trajectory[0]["arguments"]["url"] == "http://localhost:8011/events?seed=7"
    assert trajectory[1]["name"] == "click"


def test_canonical_tool_trajectory_normalizes_common_claude_browser_selectors():
    trajectory = canonical_tool_trajectory(
        [
            {"name": "type", "arguments": {"selector": {"type": "roleSelector", "role": "searchbox", "name": "Search Amazon"}, "text": "wireless mouse"}},
            {"name": "pressKey", "arguments": {"key": "Enter"}},
            {"name": "click", "arguments": {"selector": {"type": "cssSelector", "value": "#submit"}}},
        ]
    )

    assert trajectory[0]["name"] == "input"
    assert trajectory[0]["arguments"]["selector"]["type"] == "xpathSelector"
    assert trajectory[1] == {"name": "send_keys", "arguments": {"keys": "Enter"}}
    assert trajectory[2]["arguments"]["selector"] == {"type": "attributeValueSelector", "attribute": "id", "value": "submit", "case_sensitive": False}


def test_parse_harvester_output_infers_final_url_from_evidence():
    result = parse_harvester_output(
        json.dumps(
            {
                "success": True,
                "confidence": 1,
                "summary": "ok",
                "trajectory": [{"name": "navigate", "arguments": {"url": "https://www.amazon.com/"}}],
                "evidence": ["Product detail page loaded at https://www.amazon.com/Foo/dp/B004YAVF8I/ with title"],
            }
        )
    )

    assert result.final_url == "https://www.amazon.com/Foo/dp/B004YAVF8I/"
