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
                    "ingestionPipeline": {"state": "ready", "readyStages": 5, "totalStages": 5},
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
                        "hardeningGaps": {"entity_bindings": 1},
                    },
                    "ingestionPipeline": {"state": "blocked", "readyStages": 3, "totalStages": 5, "nextStage": {"label": "Generate typed tools"}},
                },
            },
        ]
    )

    assert summary["entityMapped"] == 1
    assert summary["entitySourceReady"] == 1
    assert summary["typedToolReady"] == 2
    assert summary["hardenedToolCount"] == 1
    assert summary["needsHardeningCount"] == 2
    assert summary["toolHardeningGaps"] == [
        {"name": "entity_bindings", "count": 2},
        {"name": "approval_policy", "count": 1},
    ]
    assert summary["sample"][0]["hardeningGaps"] == {"approval_policy": 1, "entity_bindings": 1}
    assert any(gap["key"] == "tool_hardening" for gap in summary["gaps"])
