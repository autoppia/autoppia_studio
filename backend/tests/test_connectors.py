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


class _FakeCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *args):
        return self

    async def __aiter__(self):
        for doc in self.docs:
            yield doc


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


@pytest.mark.parametrize(
    ("connector_type", "expected_tool", "expected_auth_field"),
    [
        ("cloudflare", "cloudflare.search", "apiToken"),
        ("slack", "slack.send_message", "botToken"),
        ("github", "github.create_issue", "personalAccessToken"),
        ("postgres", "postgres.search", "password"),
        ("bittensor_directory", "bittensor_directory.list_subnets", None),
    ],
)
def test_official_connector_toolkits_are_available(connector_type, expected_tool, expected_auth_field):
    connector = {
        "connectorId": "conn-1",
        "name": connector_type,
        "type": connector_type,
        "category": "software",
        "status": "needs_auth",
        "provider": "official",
        "config": {},
    }

    toolkit = connectors_route.connector_toolkit(connector)

    assert expected_tool in [tool["name"] for tool in toolkit["tools"]]
    if expected_auth_field:
        assert expected_auth_field in toolkit["authFields"]


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


@pytest.mark.asyncio
async def test_connector_create_moves_auth_fields_to_credential_refs(monkeypatch):
    created = []

    async def fake_create_credential_record(**kwargs):
        created.append(kwargs)
        return {"secretRef": f"secret://credential/{kwargs['metadata']['field']}"}

    monkeypatch.setattr(connectors_route, "create_credential_record", fake_create_credential_record)

    config, refs = await connectors_route._extract_connector_credentials(
        existing=None,
        email="user@example.com",
        company_id="company-1",
        connector_id="conn-1",
        connector_name="Holded",
        connector_type="holded",
        config={"apiKey": "holded-secret", "workspaceId": "ws-1"},
    )

    assert config == {"workspaceId": "ws-1"}
    assert refs == {"apiKey": "secret://credential/apiKey"}
    assert created[0]["value"] == "holded-secret"
    assert created[0]["credential_type"] == "apikey"


@pytest.mark.asyncio
async def test_connector_update_keeps_existing_ref_for_placeholder(monkeypatch):
    async def fail_create_credential_record(**kwargs):
        raise AssertionError("placeholder should not create a new credential")

    monkeypatch.setattr(connectors_route, "create_credential_record", fail_create_credential_record)

    config, refs = await connectors_route._extract_connector_credentials(
        existing={"credentialRefs": {"apiKey": "secret://credential/existing"}, "config": {"workspaceId": "old"}},
        email="user@example.com",
        company_id="company-1",
        connector_id="conn-1",
        connector_name="Holded",
        connector_type="holded",
        config={"apiKey": connectors_route.SECRET_PLACEHOLDER, "workspaceId": "new"},
    )

    assert config == {"workspaceId": "new"}
    assert refs == {"apiKey": "secret://credential/existing"}


@pytest.mark.asyncio
async def test_list_connectors_defaults_to_first_company(monkeypatch):
    class _Companies:
        async def find_one(self, query, projection=None, **kwargs):
            if query == {"email": "user@example.com"} or query == {"companyId": "company-1"}:
                return {"companyId": "company-1"}
            return None

    class _Connectors:
        def find(self, query, projection=None):
            assert query == {"email": "user@example.com", "companyId": "company-1"}
            return _FakeCursor([
                {
                    "connectorId": "conn-1",
                    "email": "user@example.com",
                    "companyId": "company-1",
                    "name": "Documents",
                    "type": "knowledge",
                    "category": "knowledge",
                    "status": "connected",
                    "config": {},
                }
            ])

    monkeypatch.setattr(connectors_route, "companies_collection", _Companies())
    monkeypatch.setattr(connectors_route, "connectors_collection", _Connectors())

    result = await connectors_route.list_connectors("user@example.com")

    assert result["connectors"][0]["connectorId"] == "conn-1"
