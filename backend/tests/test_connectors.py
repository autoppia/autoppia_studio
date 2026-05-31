import pytest

from app.routes import connectors as connectors_route


class _Result:
    def __init__(self, *, matched_count=1, deleted_count=1):
        self.matched_count = matched_count
        self.deleted_count = deleted_count


class _FakeConnectorsCollection:
    def __init__(self, doc):
        self.doc = dict(doc)
        self.last_update = None

    async def find_one(self, query, projection=None):
        if query.get("connectorId") != self.doc.get("connectorId"):
            return None
        return dict(self.doc)

    async def update_one(self, query, update):
        assert query["connectorId"] == self.doc["connectorId"]
        self.last_update = update["$set"]
        self.doc.update(self.last_update)
        return _Result()


def test_custom_api_toolkit_exposes_docs_generation_tools():
    connector = {
        "connectorId": "conn-1",
        "name": "Cloudflare",
        "type": "api",
        "category": "software",
        "status": "needs_auth",
        "provider": "custom",
        "generationStatus": "docs_provided",
        "config": {"docsUrl": "https://developers.cloudflare.com/api/"},
    }

    toolkit = connectors_route.connector_toolkit(connector)

    assert toolkit["name"] == "Cloudflare Generated API Toolkit"
    assert "api_docs_or_openapi" in toolkit["runtimeRequirements"]
    assert [tool["name"] for tool in toolkit["tools"]] == [
        "api.discover_schema",
        "api.generate_toolkit",
        "api.call",
    ]


@pytest.mark.asyncio
async def test_custom_api_test_requires_docs(monkeypatch):
    collection = _FakeConnectorsCollection(
        {
            "connectorId": "conn-1",
            "name": "Cloudflare",
            "type": "api",
            "provider": "custom",
            "status": "needs_auth",
            "config": {"apiKey": "secret"},
        }
    )
    monkeypatch.setattr(connectors_route, "connectors_collection", collection)

    result = await connectors_route.test_connector("conn-1")

    assert result["success"] is False
    assert result["connector"]["status"] == "needs_auth"
    assert "Missing API docs" in result["message"]


@pytest.mark.asyncio
async def test_custom_api_test_passes_with_docs_and_auth(monkeypatch):
    collection = _FakeConnectorsCollection(
        {
            "connectorId": "conn-1",
            "name": "Cloudflare",
            "type": "api",
            "provider": "custom",
            "status": "needs_auth",
            "generationStatus": "docs_provided",
            "config": {
                "apiKey": "secret",
                "baseUrl": "https://api.cloudflare.com/client/v4",
                "docsUrl": "https://developers.cloudflare.com/api/",
            },
        }
    )
    monkeypatch.setattr(connectors_route, "connectors_collection", collection)

    result = await connectors_route.test_connector("conn-1")

    assert result["success"] is True
    assert result["connector"]["status"] == "connected"
    assert result["connector"]["config"]["apiKey"] == connectors_route.SECRET_PLACEHOLDER
