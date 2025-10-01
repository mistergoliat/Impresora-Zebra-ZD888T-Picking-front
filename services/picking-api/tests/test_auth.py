import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

# Ensure the app package is importable when running tests from the repo root
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import auth as auth_utils
from app.deps import get_session
from app.main import app


class FakeResult:
    def __init__(self, user):
        self._user = user

    def scalar_one_or_none(self):
        return self._user


class FakeSession:
    def __init__(self, user):
        self._user = user

    async def execute(self, _query):
        return FakeResult(self._user)


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    user = type("User", (), {})()
    user.id = uuid.uuid4()
    user.username = "tester"
    user.password_hash = "hashed-password"
    user.role = "admin"
    user.active = True

    def fake_verify_password(password: str, password_hash: str) -> bool:
        return password == "s3cret" and password_hash == "hashed-password"

    monkeypatch.setattr(auth_utils, "verify_password", fake_verify_password)

    async def fake_form(self):
        return {"username": "tester", "password": "s3cret"}

    monkeypatch.setattr(Request, "form", fake_form, raising=False)

    async def override_get_session():
        yield FakeSession(user)

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_login_with_form_data(client: TestClient) -> None:
    response = client.post(
        "/auth/login",
        data={"username": "tester", "password": "s3cret"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert isinstance(payload["access_token"], str)
    assert payload["access_token"]


def test_login_with_json_body(client: TestClient) -> None:
    response = client.post(
        "/auth/login",
        json={"username": "tester", "password": "s3cret"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert isinstance(payload["access_token"], str)
    assert payload["access_token"]
