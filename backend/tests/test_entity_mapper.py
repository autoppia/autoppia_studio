from app.services.entity_mapper import propose_entities_from_openapi


def test_propose_entities_from_openapi_schemas_and_relationships():
    openapi = {
        "openapi": "3.1.0",
        "paths": {
            "/customers": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {"$ref": "#/components/schemas/CustomerRead"},
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
        "components": {
            "schemas": {
                "CustomerRead": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "format": "uuid"},
                        "name": {"type": "string"},
                        "policies": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/PolicyRead"},
                        },
                    },
                    "required": ["id", "name"],
                },
                "PolicyRead": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "format": "uuid"},
                        "customer_id": {"type": "string", "format": "uuid"},
                        "expires_at": {"type": "string", "format": "date-time"},
                    },
                },
                "HTTPValidationError": {
                    "type": "object",
                    "properties": {"detail": {"type": "array"}},
                },
            }
        },
    }

    proposals = propose_entities_from_openapi(openapi, source_url="https://example.com/openapi.json")
    by_name = {item["name"]: item for item in proposals}

    assert set(by_name) == {"Customer", "Policy"}
    assert by_name["Customer"]["fields"][0]["role"] == "identifier"
    assert by_name["Customer"]["relationships"][0]["target"] == "Policy"
    assert by_name["Customer"]["relationships"][0]["kind"] == "hasMany"
    assert by_name["Policy"]["fields"][2]["role"] == "date"
    assert by_name["Policy"]["fields"][1]["target"] == "Customer"
    assert by_name["Policy"]["relationships"][0]["target"] == "Customer"
    assert by_name["Policy"]["relationships"][0]["via"] == "customer_id"
