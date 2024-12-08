import os
import uuid
from functools import wraps
from typing import Any, Literal

import dotenv
import pytest
from api.api_types import SessionRequest
from api.db.usage import log_request
from api.main import app, verify_session  # Import verify_session from main
from api.session import BrowserSession, SessionMetadata
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from tests.mock.mock_browser import MockBrowserDriver

dotenv.load_dotenv()


@pytest.fixture
def timeout() -> int:
    return 1


@pytest.fixture
def test_url() -> str:
    return "https://www.hf0.com/"


def async_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app), base_url="http://test")


def get_test_session_id() -> str:
    return f"test-{str(uuid.uuid4())}"


@pytest.fixture
def test_session_id() -> str:
    return get_test_session_id()


def get_api_key() -> str:
    api_key = os.environ.get("NOTTE_TEST_API_KEY")
    if api_key is None:
        raise ValueError("NOTTE_TEST_API_KEY is not set")
    return api_key


client = TestClient(app)


@pytest.fixture
def browser_session(test_session_id: str) -> BrowserSession:
    """Create a mock browser session"""
    return BrowserSession(
        browser=MockBrowserDriver(), metadata=SessionMetadata(session_id=test_session_id)  # type: ignore
    )


@pytest.fixture
async def mock_verify_session(browser_session: BrowserSession):
    """Mock verify_session using FastAPI's dependency override"""

    async def mock_verify(
        request: SessionRequest,
    ) -> BrowserSession:
        return browser_session

    def mock_log_request(endpoint: Literal["observe", "step", "chat"]):
        print(f"Logging request to {endpoint}")

        async def decorator(func):
            @wraps(func)
            async def wrapper(**kwargs):
                print(f"Logging request to {endpoint}")
                return await func(**kwargs)

            return wrapper

    # Store original dependency
    original = app.dependency_overrides.copy()

    # Override the dependency
    app.dependency_overrides[verify_session] = mock_verify
    app.dependency_overrides[log_request] = mock_log_request

    yield mock_verify

    # Restore original dependencies after test
    app.dependency_overrides = original


def test_health_check(mock_verify_session: Any) -> None:
    """Test the /health endpoint"""
    response = client.get("/health")
    assert response.status_code == 200


def get_nb_active_sessions() -> int:
    """Get the number of active sessions"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    return data["active_sessions"]


def close_session(session_id: str) -> None:
    """Close a session"""
    # nb_sessions = get_nb_active_sessions()
    # assert nb_sessions > 0
    response = client.post(
        "/sessions/close", json={"session_id": session_id}, headers={"Authorization": f"Bearer {get_api_key()}"}
    )
    assert response.status_code == 200
    # assert get_nb_active_sessions() == nb_sessions - 1


def create_session() -> str:
    """Create a session"""
    nb_sessions = get_nb_active_sessions()
    response = client.post("/sessions/create", headers={"Authorization": f"Bearer {get_api_key()}"})
    assert response.status_code == 200
    data = response.json()
    assert get_nb_active_sessions() == nb_sessions + 1
    return data["session_id"]


def test_create_close_session() -> None:
    """Test the /sessions/create and /sessions/close endpoints"""
    session_id = create_session()
    close_session(session_id)


@pytest.mark.parametrize("keep_alive", [True, False])
@pytest.mark.anyio
async def test_observe_endpoint(
    mock_verify_session: Any,
    test_session_id: str,
    keep_alive: bool,
    test_url: str,
) -> None:
    assert get_nb_active_sessions() == 0
    async with async_client() as client:
        response = await client.post(
            "/env/observe",
            json={"session_id": test_session_id, "url": test_url, "keep_alive": keep_alive, "timeout": 1},
            headers={"Authorization": f"Bearer {get_api_key()}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == test_session_id
        assert "actions" in data
        # TODO: test keep_alive
        # if keep_alive:
        #     assert get_nb_active_sessions() == 1
        #     close_session(test_session_id)
        # else:
        #     assert get_nb_active_sessions() == 0


@pytest.mark.anyio
async def test_step_endpoint(
    mock_verify_session: Any,
    test_session_id: str,
) -> None:
    """Test the /step endpoint"""
    async with async_client() as client:
        response = await client.post(
            "/env/step",
            json={"session_id": test_session_id, "action": "mock_id", "content": "test_value"},
            headers={"Authorization": f"Bearer {get_api_key()}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "test_session"
        assert "actions" in data
        assert len(data["actions"]) == 1
        assert data["actions"][0]["id"] == "mock_id"


@pytest.mark.anyio
async def test_chat_endpoint(mock_verify_session: Any, test_session_id: str) -> None:
    """Test the /chat endpoint"""
    async with async_client() as client:
        response = await client.post(
            "/env/chat",
            json={"session_id": test_session_id, "content": "Navigate to https://test.com", "keep_alive": True},
            headers={"Authorization": f"Bearer {get_api_key()}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == test_session_id

        # step message

        response = await client.post(
            "/chat",
            json={"session_id": "test_session", "content": "Take action L1"},
            headers={"Authorization": f"Bearer {get_api_key()}"},
        )

        assert "content" in data


@pytest.mark.anyio
@pytest.mark.parametrize(
    "endpoint,payload",
    [
        ("/env/observe", {"url": "https://test.com"}),
        ("/env/step", {"action": "mock_id", "content": "test_value"}),
        ("/env/chat", {"content": "Navigate to https://test.com"}),
    ],
)
async def test_invalid_session(endpoint: str, payload: dict) -> None:
    """Test endpoints with invalid session ID"""
    async with async_client() as client:
        response = await client.post(
            endpoint,
            json={"session_id": "invalid_session", **payload},
            headers={"Authorization": f"Bearer {get_api_key()}"},
        )
        assert response.status_code == 404


@pytest.mark.anyio
@pytest.mark.parametrize(
    "endpoint,payload", [("/env/observe", {}), ("/env/step", {"action": "mock_id"}), ("/env/chat", {})]
)
async def test_missing_required_fields(endpoint: str, payload: dict, mock_verify_session: Any) -> None:
    """Test endpoints with missing required fields"""
    async with async_client() as client:
        response = await client.post(
            endpoint,
            json={"session_id": "test_session", **payload},
            headers={"Authorization": f"Bearer {get_api_key()}"},
        )
        assert response.status_code == 422

    # test step with invalid session_id or empty session_id should raise NotteInternalError
    # test step with freshly closed session_id should raise NotteInternalError
