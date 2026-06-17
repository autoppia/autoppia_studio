import pytest
from fastapi import HTTPException

from app.repositories import ConnectorRepository
from app.request_scope import RequestScope, _decode_token_email


class _Collection:
    def __init__(self, doc):
        self.doc = dict(doc)
        self.deleted = False
        self.last_update_query = None
        self.last_delete_query = None

    async def find_one(self, query, projection=None):
        if self.deleted:
            return None
        for key, value in query.items():
            if self.doc.get(key) != value:
                return None
        return dict(self.doc)

    async def update_one(self, query, update):
        self.last_update_query = dict(query)
        self.doc.update(update.get("$set", {}))

    async def delete_one(self, query):
        self.last_delete_query = dict(query)
        self.deleted = True

        class _Result:
            deleted_count = 1

        return _Result()


def test_request_scope_rejects_email_mismatch():
    scope = RequestScope(email="owner@example.com", token_email="owner@example.com")

    with pytest.raises(HTTPException) as exc:
        scope.require_email("other@example.com")

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_repository_hides_foreign_owned_docs():
    repo = ConnectorRepository(
        _Collection({"connectorId": "conn-1", "email": "owner@example.com"}),
        RequestScope(email="other@example.com", token_email="other@example.com"),
    )

    with pytest.raises(HTTPException) as exc:
        await repo.by_id("conn-1")

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_repository_hides_docs_without_scope():
    repo = ConnectorRepository(
        _Collection({"connectorId": "conn-1", "email": "owner@example.com"}),
        RequestScope(),
    )

    with pytest.raises(HTTPException) as exc:
        await repo.by_id("conn-1")

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_repository_allows_owned_update():
    collection = _Collection({"connectorId": "conn-1", "email": "owner@example.com", "name": "Old"})
    repo = ConnectorRepository(collection, RequestScope(email="owner@example.com", token_email="owner@example.com"))

    doc = await repo.update_owned_one({"connectorId": "conn-1"}, {"$set": {"name": "New"}})

    assert doc["name"] == "New"
    assert collection.last_update_query == {"connectorId": "conn-1", "email": "owner@example.com"}


@pytest.mark.asyncio
async def test_repository_scopes_owned_delete_query():
    collection = _Collection({"connectorId": "conn-1", "email": "owner@example.com", "name": "Old"})
    repo = ConnectorRepository(collection, RequestScope(email="owner@example.com", token_email="owner@example.com"))

    deleted = await repo.delete_owned_one({"connectorId": "conn-1"})

    assert deleted == 1
    assert collection.last_delete_query == {"connectorId": "conn-1", "email": "owner@example.com"}


def test_invalid_jwt_fails_closed():
    with pytest.raises(HTTPException) as exc:
        _decode_token_email("not-a-valid-token")

    assert exc.value.status_code == 401
