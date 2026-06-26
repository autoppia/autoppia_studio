from app.services.connector_factory import summarize_connector_factory


def test_connector_factory_summarizes_tool_hardening_gaps():
    summary = summarize_connector_factory(
        [
            {
                "connectorId": "conn-1",
                "name": "Claims ERP",
                "capabilityDiscovery": {
                    "entityMapping": {"status": "mapped", "businessObjects": ["Claim"], "readyForToolBinding": True},
                    "toolSynthesis": {
                        "typedToolCount": 2,
                        "governedToolCount": 2,
                        "hardenedToolCount": 1,
                        "needsHardeningCount": 1,
                        "hardeningGaps": {"approval_policy": 1, "entity_bindings": 1},
                    },
                    "candidateTasks": {"recommended": True},
                    "ingestionPipeline": {"state": "ready", "readyStages": 5, "totalStages": 5, "playbook": []},
                },
            },
            {
                "connectorId": "conn-2",
                "name": "Mail",
                "capabilityDiscovery": {
                    "entityMapping": {"status": "source_ready"},
                    "toolSynthesis": {
                        "typedToolCount": 1,
                        "governedToolCount": 1,
                        "hardenedToolCount": 0,
                        "needsHardeningCount": 1,
                        "sendToolCount": 1,
                        "sendTools": ["smtp.send_email"],
                        "approvalRequiredTools": ["smtp.send_email"],
                        "hardeningGaps": {"entity_bindings": 1},
                    },
                    "ingestionPipeline": {
                        "state": "blocked",
                        "readyStages": 3,
                        "totalStages": 5,
                        "nextStage": {"label": "Generate typed tools"},
                        "playbook": [
                            {
                                "stage": "tool_synthesis",
                                "status": "pending",
                                "target": "capabilities",
                                "severity": "high",
                                "action": "Generate typed tools with schemas, side effects, scopes and entity bindings.",
                            }
                        ],
                    },
                },
            },
        ]
    )

    assert summary["entityMapped"] == 1
    assert summary["entitySourceReady"] == 1
    assert summary["typedToolReady"] == 2
    assert summary["hardenedToolCount"] == 1
    assert summary["needsHardeningCount"] == 2
    assert summary["sendToolCount"] == 1
    assert summary["sendTools"] == ["smtp.send_email"]
    assert summary["sendApprovalGate"] == {
        "required": True,
        "ready": True,
        "sendTools": ["smtp.send_email"],
        "approvalRequiredTools": ["smtp.send_email"],
        "uncoveredSendTools": [],
        "unknownSendToolCount": 0,
        "checks": {
            "sendToolsNamed": True,
            "sendToolsRequireApproval": True,
        },
        "hardeningPlaybook": [],
    }
    assert summary["toolHardeningGaps"] == [
        {"name": "entity_bindings", "count": 2},
        {"name": "approval_policy", "count": 1},
    ]
    assert summary["toolHardeningPlaybook"][0] == {
        "gap": "entity_bindings",
        "count": 2,
        "area": "entities",
        "severity": "medium",
        "action": "Bind input and output business entities before promoting reusable skills.",
    }
    assert summary["toolProductionGate"] == {
        "state": "needs_hardening",
        "ready": False,
        "totalTools": 3,
        "hardenedTools": 1,
        "needsHardening": 2,
        "typedConnectorCoverage": {"ready": 2, "total": 2},
        "checks": {
            "typedTools": True,
            "hardenedContracts": False,
            "schemasPoliciesScopesEntities": False,
        },
        "blockers": [
            {"name": "entity_bindings", "count": 2},
            {"name": "approval_policy", "count": 1},
        ],
        "hardeningPlaybook": summary["toolHardeningPlaybook"],
    }
    assert summary["factoryPipelineGate"] == {
        "state": "blocked",
        "ready": False,
        "checks": {
            "connectorsPresent": True,
            "ingestionComplete": False,
            "entityMappingComplete": False,
            "typedToolsReady": True,
            "candidateTasksSeeded": False,
            "toolProductionReady": False,
        },
        "blockers": [
            "ingestionComplete",
            "entityMappingComplete",
            "candidateTasksSeeded",
            "toolProductionReady",
        ],
        "hardeningPlaybook": [
            {
                "gap": "tool_production",
                "count": 2,
                "area": "tools",
                "severity": "high",
                "action": "Harden synthesized tools before exposing them as production capabilities.",
            },
            {
                "gap": "candidate_tasks",
                "count": 1,
                "area": "evals",
                "severity": "medium",
                "action": "Generate candidate benchmark tasks from discovered connector capabilities.",
            },
            {
                "gap": "entity_mapping",
                "count": 1,
                "area": "entities",
                "severity": "high",
                "action": "Map connector schemas or observations to business entities before tool binding.",
            },
            {
                "gap": "ingestion_pipeline",
                "count": 1,
                "area": "ingestion",
                "severity": "high",
                "action": "Complete connector ingestion with docs/auth/surface evidence before synthesis.",
            },
        ],
    }
    assert summary["ingestionPlaybook"] == [
        {
            "connectorId": "conn-2",
            "connectorName": "Mail",
            "stage": "tool_synthesis",
            "status": "pending",
            "target": "capabilities",
            "severity": "high",
            "action": "Generate typed tools with schemas, side effects, scopes and entity bindings.",
        }
    ]
    assert summary["sample"][0]["hardeningGaps"] == {"approval_policy": 1, "entity_bindings": 1}
    assert summary["sample"][1]["sendToolCount"] == 1
    assert summary["sample"][1]["sendTools"] == ["smtp.send_email"]
    assert summary["sample"][1]["sendApprovalGate"] == {
        "ready": True,
        "approvalRequiredTools": ["smtp.send_email"],
        "uncoveredSendTools": [],
        "unknownSendToolCount": 0,
    }
    assert any(gap["key"] == "tool_hardening" for gap in summary["gaps"])


def test_connector_factory_flags_send_tools_without_approval_coverage():
    summary = summarize_connector_factory(
        [
            {
                "connectorId": "conn-mail",
                "name": "Mail",
                "capabilityDiscovery": {
                    "entityMapping": {"status": "mapped", "readyForToolBinding": True},
                    "toolSynthesis": {
                        "typedToolCount": 1,
                        "governedToolCount": 1,
                        "hardenedToolCount": 0,
                        "needsHardeningCount": 1,
                        "sendToolCount": 1,
                        "sendTools": ["smtp.send_email"],
                        "hardeningGaps": {"approval_policy": 1},
                    },
                    "candidateTasks": {"recommended": True},
                    "ingestionPipeline": {"state": "ready", "readyStages": 5, "totalStages": 5},
                },
            }
        ]
    )

    assert summary["sendApprovalGate"] == {
        "required": True,
        "ready": False,
        "sendTools": ["smtp.send_email"],
        "approvalRequiredTools": [],
        "uncoveredSendTools": ["smtp.send_email"],
        "unknownSendToolCount": 0,
        "checks": {
            "sendToolsNamed": True,
            "sendToolsRequireApproval": False,
        },
        "hardeningPlaybook": [
            {
                "gap": "approval_policy",
                "count": 1,
                "area": "approvals",
                "severity": "high",
                "action": "Require human approval for write/send boundaries.",
            }
        ],
    }
    assert summary["sample"][0]["sendApprovalGate"] == {
        "ready": False,
        "approvalRequiredTools": [],
        "uncoveredSendTools": ["smtp.send_email"],
        "unknownSendToolCount": 0,
    }
