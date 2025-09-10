import os
import tempfile
from collections.abc import Generator

import pytest
from dotenv import load_dotenv
from notte_sdk import NotteClient
from notte_sdk.endpoints.workflows import RemoteWorkflow
from notte_sdk.types import (
    DeleteWorkflowResponse,
    GetWorkflowResponse,
    GetWorkflowWithLinkResponse,
    ListWorkflowsResponse,
)


@pytest.fixture(scope="module")
def client():
    """Create a NotteClient instance for testing."""
    _ = load_dotenv()
    return NotteClient()


@pytest.fixture
def sample_workflow_content():
    """Sample valid script content for testing."""
    return '''from notte_sdk import NotteClient


def run():
    """Sample script that navigates to a URL and scrapes content."""
    from notte_sdk import NotteClient
    url = "https://example.com"
    client = NotteClient()
    with client.Session(headless=True, perception_type="fast") as session:
        session.execute({"type": "goto", "url": url})
        session.observe()
        result = session.scrape()
        return result
'''


@pytest.fixture
def updated_workflow_content():
    """Updated script content for testing updates."""
    return '''from notte_sdk import NotteClient


def run(url: str):
    """Updated sample script with different URL."""
    from notte_sdk import NotteClient
    client = NotteClient()
    with client.Session(headless=True, perception_type="fast") as session:
        session.execute({"type": "goto", "url": url})
        session.observe()
        agent = client.Agent(session=session, max_steps=1)
        _ = agent.run(task="goto google.com and search for 'notte agents'")
        result = session.scrape()
        return {"updated": True, "data": result}
'''


@pytest.fixture
def temp_workflow_file(sample_workflow_content: str) -> Generator[str, None, None]:
    """Create a temporary script file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        _ = f.write(sample_workflow_content)
        temp_path = f.name

    yield temp_path

    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def temp_updated_workflow_file(updated_workflow_content: str) -> Generator[str, None, None]:
    """Create a temporary updated script file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        _ = f.write(updated_workflow_content)
        temp_path = f.name

    yield temp_path

    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


class TestWorkflowsClient:
    """Test cases for WorkflowsClient CRUD operations."""

    def test_create_script(self, client: NotteClient, temp_workflow_file: str):
        """Test creating a new script."""
        response = client.workflows.create(workflow_path=temp_workflow_file)

        assert isinstance(response, GetWorkflowResponse)
        assert response.workflow_id is not None
        assert response.latest_version is not None
        assert response.status is not None

        # Store workflow_id for cleanup in other tests
        TestWorkflowsClient._test_workflow_id = response.workflow_id

    def test_get_script(self, client: NotteClient):
        """Test getting a script with download URL."""
        if not hasattr(TestWorkflowsClient, "_test_workflow_id"):
            pytest.skip("No script created to test get operation")

        response = client.workflows.get(workflow_id=TestWorkflowsClient._test_workflow_id)

        assert isinstance(response, GetWorkflowWithLinkResponse)
        assert response.workflow_id == TestWorkflowsClient._test_workflow_id
        assert response.url is not None
        # URL should be encrypted
        assert not response.url.startswith(("http://", "https://"))

    def test_list_workflows(self, client: NotteClient):
        """Test listing all workflows."""
        response = client.workflows.list()

        assert isinstance(response, ListWorkflowsResponse)
        assert isinstance(response.items, list)
        assert isinstance(response.page, int)
        assert isinstance(response.page_size, int)
        assert isinstance(response.has_next, bool)
        assert isinstance(response.has_previous, bool)

        # Check if our test script is in the list
        if hasattr(TestWorkflowsClient, "_test_workflow_id"):
            workflow_ids = [script.workflow_id for script in response.items]
            assert TestWorkflowsClient._test_workflow_id in workflow_ids

    def test_update_script(self, client: NotteClient, temp_updated_workflow_file: str):
        """Test updating an existing script."""
        if not hasattr(TestWorkflowsClient, "_test_workflow_id"):
            pytest.skip("No script created to test update operation")

        response = client.workflows.update(
            workflow_id=TestWorkflowsClient._test_workflow_id, workflow_path=temp_updated_workflow_file
        )

        assert isinstance(response, GetWorkflowResponse)
        assert response.workflow_id == TestWorkflowsClient._test_workflow_id
        assert response.latest_version is not None

    def test_delete_script(self, client: NotteClient):
        """Test deleting a script."""
        if not hasattr(TestWorkflowsClient, "_test_workflow_id"):
            pytest.skip("No script created to test delete operation")

        # Delete should return a proper response
        response = client.workflows.delete(workflow_id=TestWorkflowsClient._test_workflow_id)

        # Verify we get a proper delete response
        assert isinstance(response, DeleteWorkflowResponse)
        assert response.status == "success"
        assert response.message is not None

        # Verify script is deleted by trying to get it (should fail or return empty)
        try:
            _ = client.workflows.get(workflow_id=TestWorkflowsClient._test_workflow_id)
            # If we get here, the script might still exist with a different state
            # This depends on the API implementation
        except Exception:
            # Expected behavior - script no longer exists
            pass


@pytest.fixture
def remote_workflow(client: NotteClient) -> RemoteWorkflow:
    """Create a remote workflow using a specific workflow ID and decryption key."""
    return client.Workflow(
        workflow_id="9fb6d40e-c76a-4d44-a73a-aa7843f0f535",  # pragma: allowlist secret
        decryption_key="4ca0a0f585312d94028fee5e53480dbd03d8229ea0512a12b7422456d5100c98",  # pragma: allowlist secret
    )


def test_remote_workflow_get_url(remote_workflow: RemoteWorkflow):
    """Test getting script download URL."""
    url = remote_workflow.get_url()
    assert isinstance(url, str)
    assert url.startswith(("http://", "https://"))


def test_remote_workflow_download(remote_workflow: RemoteWorkflow):
    """Test downloading script content."""
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as temp_file:
        try:
            content = remote_workflow.download(temp_file.name)

            assert isinstance(content, str)
            assert "def run(url: str):" in content
            assert "from notte_sdk import NotteClient" in content

            # Verify file was created
            assert os.path.exists(temp_file.name)

            # Verify file content matches returned content
            with open(temp_file.name, "r") as f:
                file_content = f.read()
            assert file_content == content

        finally:
            if os.path.exists(temp_file.name):
                os.unlink(temp_file.name)


def test_remote_workflow_download_invalid_extension(remote_workflow: RemoteWorkflow):
    """Test downloading with invalid file extension."""
    with pytest.raises(ValueError, match="Workflow path must end with .py"):
        _ = remote_workflow.download("invalid_file.txt")


def test_remote_workflow_update(remote_workflow: RemoteWorkflow, temp_updated_workflow_file: str):
    """Test updating script through RemoteWorkflow."""
    original_version = remote_workflow.response.latest_version

    remote_workflow.update(temp_updated_workflow_file)

    # Version should have changed
    assert remote_workflow.response.latest_version != original_version


@pytest.mark.parametrize("local", [True, False])
def test_remote_workflow_run(remote_workflow: RemoteWorkflow, local: bool):
    """Test running a script through RemoteWorkflow."""
    # Note: This test assumes the script execution environment is properly set up
    # and that the sample script can run successfully
    result = remote_workflow.run(local=local, url="https://www.google.com")
    assert result is not None


class TestRemoteWorkflowFactory:
    """Test cases for RemoteWorkflowFactory functionality."""

    def test_factory_create_script(self, client: NotteClient, temp_workflow_file: str):
        """Test creating script through factory."""
        script = client.Workflow(workflow_path=temp_workflow_file)

        assert script is not None
        assert hasattr(script, "response")
        assert script.response.workflow_id is not None
        assert script.response.latest_version is not None

        # Cleanup
        try:
            script.delete()
        except Exception:
            pass

    def test_factory_get_existing_script(self, client: NotteClient, temp_workflow_file: str):
        """Test getting existing script through factory."""
        # First create a script
        response = client.workflows.create(workflow_path=temp_workflow_file)

        try:
            # Then get it through factory
            script = client.Workflow(workflow_id=response.workflow_id)

            assert script is not None
            assert script.response.workflow_id == response.workflow_id
            assert script.response.latest_version is not None

        finally:
            # Cleanup
            _ = client.workflows.delete(workflow_id=response.workflow_id)


class TestWorkflowValidation:
    """Test cases for script validation functionality."""

    def test_invalid_workflow_no_run_function(self, client: NotteClient):
        """Test that workflows without run function are rejected."""
        invalid_content = """import notte

def invalid_function():
    pass
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            _ = f.write(invalid_content)
            temp_path = f.name

        try:
            with pytest.raises(
                Exception, match="Python script must contain a 'run' function"
            ):  # Should raise validation error
                _ = client.workflows.create(workflow_path=temp_path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_invalid_workflow_forbidden_imports(self, client: NotteClient):
        """Test that workflows with forbidden imports are rejected."""
        invalid_content = """import os
import notte

def run():
    os.system("echo hello")  # This should be forbidden
    return "done"
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            _ = f.write(invalid_content)
            temp_path = f.name

        try:
            with pytest.raises(Exception, match="Import of 'os' is not allowed"):  # Should raise validation error
                _ = client.workflows.create(workflow_path=temp_path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_valid_workflow_allowed_imports(self, client: NotteClient):
        """Test that workflows with allowed imports are accepted."""
        valid_content = """import json
import datetime
import notte

def run():
    data = {"timestamp": datetime.datetime.now().isoformat()}
    json_data = json.dumps(data)

    with notte.Session(headless=True) as session:
        session.execute({"type": "goto", "url": "https://httpbin.org/get"})
        result = session.scrape()
        return {"json_data": json_data, "scrape_result": result}
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            _ = f.write(valid_content)
            temp_path = f.name

        try:
            response = client.workflows.create(workflow_path=temp_path)

            assert response.workflow_id is not None

            # Cleanup
            resp = client.workflows.delete(workflow_id=response.workflow_id)
            assert resp.status == "success"

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


# Integration test for end-to-end workflow
def test_end_to_end_workflow_workflow(client: NotteClient, sample_workflow_content: str, updated_workflow_content: str):
    """Test complete script lifecycle: create -> get -> update -> run -> delete."""
    workflow_id = None

    # Create script file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(sample_workflow_content)
        workflow_path = f.name

    # 0. Create script
    workflow = client.Workflow(
        workflow_id="77780976-6e58-47eb-b1ee-5b213734f930",
        decryption_key="b0a91a8ea2bf8c07c94eb2ba039761fcebde23a4171d38a399015541417ff396",  # pragma: allowlist secret
    )
    workflow_id = workflow.workflow_id
    assert workflow_id is not None
    # 1. Update script
    _ = workflow.update(workflow_path=workflow_path)

    # 2. List workflows (should include our script)
    # list_response = client.workflows.list(page_size=20)
    # workflow_ids = [s.workflow_id for s in list_response.items]
    # assert workflow_id in workflow_ids

    # 4. Update script
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        _ = f.write(updated_workflow_content)
        updated_workflow_path = f.name

    _ = workflow.update(workflow_path=updated_workflow_path)

    # 5. Test RemoteWorkflow functionality
    download_url = workflow.get_url()
    # should be encrypted
    assert download_url.startswith(("http://", "https://"))

    # 6. Download and verify content
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
        downloaded_content = workflow.download(f.name)
        assert "def run(url: str):" in downloaded_content
        assert "updated" in downloaded_content.lower() or "httpbin" in downloaded_content

    # Clean up temp files
    os.unlink(workflow_path)
    os.unlink(updated_workflow_path)
    os.unlink(f.name)
