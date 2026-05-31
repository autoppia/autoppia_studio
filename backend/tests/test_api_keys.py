import pytest
from fastapi import HTTPException

from app.routes.api_keys import _object_id


def test_invalid_api_key_id_returns_bad_request():
    with pytest.raises(HTTPException) as exc:
        _object_id("not-an-object-id")

    assert exc.value.status_code == 400
