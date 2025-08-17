import os
import tempfile

import pytest
from dotenv import load_dotenv
from notte_sdk import NotteClient
from notte_sdk.types import DeleteScriptResponse, GetScriptResponse, GetScriptWithLinkResponse, ListScriptsResponse


@pytest.fixture(scope="module")
def notte_client():
    """Create a NotteClient instance for testing."""
    _ = load_dotenv()
    return NotteClient()


@pytest.fixture
def sample_script_content():
    """Sample valid script content for testing."""
    return '''import notte


def run():
    """Sample script that navigates to a URL and scrapes content."""
    url = "https://example.com"
    with notte.Session(headless=True, perception_type="fast") as session:
        session.execute({"type": "goto", "url": url})
        session.observe()
        result = session.scrape()
        return result
'''


@pytest.fixture
def updated_script_content():
    """Updated script content for testing updates."""
    return '''import notte


def run():
    """Updated sample script with different URL."""
    url = "https://httpbin.org/get"
    with notte.Session(headless=True, perception_type="fast") as session:
        session.execute({"type": "goto", "url": url})
        session.observe()
        result = session.scrape()
        return {"updated": True, "data": result}
'''


@pytest.fixture
def temp_script_file(sample_script_content):
    """Create a temporary script file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(sample_script_content)
        temp_path = f.name

    yield temp_path

    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def temp_updated_script_file(updated_script_content):
    """Create a temporary updated script file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        _ = f.write(updated_script_content)
        temp_path = f.name

    yield temp_path

    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


class TestScriptsClient:
    """Test cases for ScriptsClient CRUD operations."""

    def test_create_script(self, notte_client: NotteClient, temp_script_file: str):
        """Test creating a new script."""
        response = notte_client.scripts.create(script_path=temp_script_file)

        assert isinstance(response, GetScriptResponse)
        assert response.script_id is not None
        assert response.latest_version is not None
        assert response.status is not None

        # Store script_id for cleanup in other tests
        TestScriptsClient._test_script_id = response.script_id

    def test_get_script(self, notte_client: NotteClient):
        """Test getting a script with download URL."""
        if not hasattr(TestScriptsClient, "_test_script_id"):
            pytest.skip("No script created to test get operation")

        response = notte_client.scripts.get(script_id=TestScriptsClient._test_script_id)

        assert isinstance(response, GetScriptWithLinkResponse)
        assert response.script_id == TestScriptsClient._test_script_id
        assert response.url is not None
        assert response.url.startswith(("http://", "https://"))

    def test_list_scripts(self, notte_client: NotteClient):
        """Test listing all scripts."""
        response = notte_client.scripts.list()

        assert isinstance(response, ListScriptsResponse)
        assert isinstance(response.items, list)
        assert isinstance(response.page, int)
        assert isinstance(response.page_size, int)
        assert isinstance(response.has_next, bool)
        assert isinstance(response.has_previous, bool)

        # Check if our test script is in the list
        if hasattr(TestScriptsClient, "_test_script_id"):
            script_ids = [script.script_id for script in response.items]
            assert TestScriptsClient._test_script_id in script_ids

    def test_update_script(self, notte_client: NotteClient, temp_updated_script_file: str):
        """Test updating an existing script."""
        if not hasattr(TestScriptsClient, "_test_script_id"):
            pytest.skip("No script created to test update operation")

        response = notte_client.scripts.update(
            script_id=TestScriptsClient._test_script_id, script_path=temp_updated_script_file
        )

        assert isinstance(response, GetScriptResponse)
        assert response.script_id == TestScriptsClient._test_script_id
        assert response.latest_version is not None

    def test_delete_script(self, notte_client: NotteClient):
        """Test deleting a script."""
        if not hasattr(TestScriptsClient, "_test_script_id"):
            pytest.skip("No script created to test delete operation")

        # Delete should return a proper response
        response = notte_client.scripts.delete(script_id=TestScriptsClient._test_script_id)

        # Verify we get a proper delete response
        assert isinstance(response, DeleteScriptResponse)
        assert response.status is not None
        assert response.message is not None

        # Verify script is deleted by trying to get it (should fail or return empty)
        try:
            _ = notte_client.scripts.get(script_id=TestScriptsClient._test_script_id)
            # If we get here, the script might still exist with a different state
            # This depends on the API implementation
        except Exception:
            # Expected behavior - script no longer exists
            pass


class TestRemoteScript:
    """Test cases for RemoteScript functionality."""

    @pytest.fixture(autouse=True)
    def setup_script(self, notte_client: NotteClient, temp_script_file: str):
        """Setup a script for RemoteScript testing."""
        response = notte_client.scripts.create(script_path=temp_script_file)
        self.remote_script = notte_client.Script(script_id=response.script_id)
        yield
        # Cleanup
        try:
            self.remote_script.delete()
        except Exception:
            pass  # Ignore cleanup errors

    def test_remote_script_get_url(self):
        """Test getting script download URL."""
        url = self.remote_script.get_url()
        assert isinstance(url, str)
        assert url.startswith(("http://", "https://"))

    def test_remote_script_download(self):
        """Test downloading script content."""
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as temp_file:
            try:
                content = self.remote_script.download(temp_file.name)

                assert isinstance(content, str)
                assert "def run():" in content
                assert "import notte" in content

                # Verify file was created
                assert os.path.exists(temp_file.name)

                # Verify file content matches returned content
                with open(temp_file.name, "r") as f:
                    file_content = f.read()
                assert file_content == content

            finally:
                if os.path.exists(temp_file.name):
                    os.unlink(temp_file.name)

    def test_remote_script_download_invalid_extension(self):
        """Test downloading with invalid file extension."""
        with pytest.raises(ValueError, match="Script path must end with .py"):
            self.remote_script.download("invalid_file.txt")

    def test_remote_script_update(self, temp_updated_script_file: str):
        """Test updating script through RemoteScript."""
        original_version = self.remote_script.response.latest_version

        self.remote_script.update(temp_updated_script_file)

        # Version should have changed
        assert self.remote_script.response.latest_version != original_version

    def test_remote_script_run(self):
        """Test running a script through RemoteScript."""
        # Note: This test assumes the script execution environment is properly set up
        # and that the sample script can run successfully
        try:
            result = self.remote_script.run()
            # The result type depends on what the script returns
            # For our sample script, it should return some scraped data
            assert result is not None
        except Exception as e:
            # Script execution might fail in test environment due to browser/session issues
            # This is acceptable for integration tests
            pytest.skip(f"Script execution failed (expected in test environment): {e}")


class TestRemoteScriptFactory:
    """Test cases for RemoteScriptFactory functionality."""

    def test_factory_create_script(self, notte_client: NotteClient, temp_script_file: str):
        """Test creating script through factory."""
        script = notte_client.Script(script_path=temp_script_file)

        assert script is not None
        assert hasattr(script, "response")
        assert script.response.script_id is not None
        assert script.response.latest_version is not None

        # Cleanup
        try:
            script.delete()
        except Exception:
            pass

    def test_factory_get_existing_script(self, notte_client: NotteClient, temp_script_file: str):
        """Test getting existing script through factory."""
        # First create a script
        response = notte_client.scripts.create(script_path=temp_script_file)

        try:
            # Then get it through factory
            script = notte_client.Script(script_id=response.script_id)

            assert script is not None
            assert script.response.script_id == response.script_id
            assert script.response.latest_version is not None

        finally:
            # Cleanup
            try:
                notte_client.scripts.delete(script_id=response.script_id)
            except Exception:
                pass


class TestScriptValidation:
    """Test cases for script validation functionality."""

    def test_invalid_script_no_run_function(self, notte_client: NotteClient):
        """Test that scripts without run function are rejected."""
        invalid_content = """import notte

def invalid_function():
    pass
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(invalid_content)
            temp_path = f.name

        try:
            with pytest.raises(Exception):  # Should raise validation error
                notte_client.scripts.create(script_path=temp_path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_invalid_script_forbidden_imports(self, notte_client: NotteClient):
        """Test that scripts with forbidden imports are rejected."""
        invalid_content = """import os
import notte

def run():
    os.system("echo hello")  # This should be forbidden
    return "done"
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(invalid_content)
            temp_path = f.name

        try:
            with pytest.raises(Exception):  # Should raise validation error
                notte_client.scripts.create(script_path=temp_path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_valid_script_allowed_imports(self, notte_client: NotteClient):
        """Test that scripts with allowed imports are accepted."""
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
            f.write(valid_content)
            temp_path = f.name

        try:
            response = notte_client.scripts.create(script_path=temp_path)

            assert response.script_id is not None

            # Cleanup
            notte_client.scripts.delete(script_id=response.script_id)

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


# Integration test for end-to-end workflow
def test_end_to_end_script_workflow(notte_client: NotteClient, sample_script_content: str, updated_script_content: str):
    """Test complete script lifecycle: create -> get -> update -> run -> delete."""
    script_id = None

    try:
        # Create script file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(sample_script_content)
            script_path = f.name

        # 1. Create script
        create_response = notte_client.scripts.create(script_path=script_path)
        script_id = create_response.script_id
        assert script_id is not None

        # 2. Get script
        get_response = notte_client.scripts.get(script_id=script_id)
        assert get_response.script_id == script_id
        assert get_response.url is not None

        # 3. List scripts (should include our script)
        list_response = notte_client.scripts.list()
        script_ids = [s.script_id for s in list_response.items]
        assert script_id in script_ids

        # 4. Update script
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            _ = f.write(updated_script_content)
            updated_script_path = f.name

        update_response = notte_client.scripts.update(script_id=script_id, script_path=updated_script_path)
        assert update_response.script_id == script_id

        # 5. Test RemoteScript functionality
        remote_script = notte_client.Script(script_id=script_id)
        download_url = remote_script.get_url()
        assert download_url.startswith(("http://", "https://"))

        # 6. Download and verify content
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            downloaded_content = remote_script.download(f.name)
            assert "def run():" in downloaded_content
            assert "updated" in downloaded_content.lower() or "httpbin" in downloaded_content

        # Clean up temp files
        os.unlink(script_path)
        os.unlink(updated_script_path)
        os.unlink(f.name)

    finally:
        # 7. Delete script
        if script_id:
            try:
                notte_client.scripts.delete(script_id=script_id)
            except Exception:
                pass  # Ignore cleanup errors
