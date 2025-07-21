import os

import pytest
from dotenv import load_dotenv
from notte_sdk import NotteClient
from notte_sdk.errors import NotteAPIError

import notte


@pytest.fixture
def test_persona_id() -> str:
    return "7abb4f37-25a1-4409-98d9-c4c916918254"


@pytest.mark.skip(reason="This test is not working as expected")
def test_persona_in_local_agent():
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))

    with client.Persona(create_vault=True) as persona:
        with notte.Session() as session:
            agent = notte.Agent(session=session, max_steps=5, vault=persona.vault)
            _ = agent.run(task="Go to the persona's email and check for any new messages")


def test_persona_should_be_deleted_after_exit_context():
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
    persona_id = None
    with client.Persona() as persona:
        persona_id = persona.persona_id
    assert persona_id is not None
    with pytest.raises(NotteAPIError):
        _ = client.personas.get(persona_id)


def test_persona_with_vault_in_remote_agent():
    _ = load_dotenv()

    client = NotteClient()
    # Create a new persona with vault
    with client.Persona(create_vault=True) as persona, client.Session(headless=False) as session:
        # Add credentials to the persona's vault
        with pytest.raises(NotteAPIError, match="This vault can only store one email address accross all credentials"):
            _ = persona.vault.add_credentials(
                url="https://github.com/",
                email="<your-email>",
                password="<your-password>",  # pragma: allowlist secret
            )
        # add a new credentials with the same personal email
        _ = persona.vault.add_credentials(
            url="https://github.com/",
            email=persona.info.email,
            password="<your-password>",  # pragma: allowlist secret
        )

        # Run an agent with secure credential access
        agent = client.Agent(session=session, max_steps=1)
        _ = agent.run(task="try to login to github.com with the persona's credentials")


@pytest.mark.skip(reason="This test should not be run as it costs money")
def test_persona_phone_number_management(test_persona_id: str):
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
    persona = client.Persona(persona_id=test_persona_id)

    # Create persona without phone number initially
    assert persona.info is not None
    assert persona.info.phone_number == "+1 415 649 5623"

    # Create phone number for persona
    with pytest.raises(NotteAPIError):
        _ = persona.create_number()


@pytest.mark.skip(reason="This test should not be run as it costs money")
def test_persona_with_phone_number_creation():
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
    with pytest.raises(NotteAPIError, match="No more phone numbers available"):
        with client.Persona(create_phone_number=True) as persona:
            # Create persona with phone number
            assert persona.info is not None
            assert persona.info.phone_number is not None
            assert persona.info.status == "active"
            assert persona.info.first_name is not None
            assert persona.info.last_name is not None
            assert persona.info.email is not None

            # Test reading SMS messages (should be empty initially)
            sms_messages = persona.sms()
            assert len(sms_messages) == 0

            # Test reading emails (should be empty initially)
            emails = persona.emails()
            assert len(emails) == 0


def test_persona_with_vault_creation():
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))

    with client.Persona(create_vault=True) as persona:
        # Create persona with vault
        assert persona.info is not None
        assert persona.info.vault_id is not None
        assert persona.info.status == "active"
        assert persona.info.phone_number is None

        # Test vault access
        vault = persona.vault
        assert vault.vault_id == persona.info.vault_id

        # Add credentials to vault
        _ = vault.add_credentials(
            url="https://test.com",
            email=persona.info.email,
            password="testpassword",  # pragma: allowlist secret
        )

        # Verify credentials were added
        credentials = vault.get_credentials(url="https://test.com")
        assert credentials is not None
        assert credentials.get("email") == persona.info.email


def test_persona_email_reading_with_filters(test_persona_id: str):
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))

    persona = client.Persona(persona_id=test_persona_id)
    # Test reading emails with different filters
    all_emails = persona.emails()
    assert len(all_emails) >= 1

    # Test with limit
    limited_emails = persona.emails(limit=5)
    assert len(limited_emails) >= 1

    # Test with unread only
    unread_emails = persona.emails(only_unread=True)
    assert len(unread_emails) == 0


def test_persona_sms_reading_with_filters(test_persona_id: str):
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))

    persona = client.Persona(persona_id=test_persona_id)
    # Test reading SMS with different filters
    all_sms = persona.sms()
    assert len(all_sms) == 0

    # Test with limit
    limited_sms = persona.sms(limit=5)
    assert len(limited_sms) == 0

    # Test with unread only
    unread_sms = persona.sms(only_unread=True)
    assert len(unread_sms) == 0


def test_persona_get_operations():
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))

    # Create persona
    created_persona = client.personas.create()
    persona_id = created_persona.persona_id

    # Get persona by ID
    retrieved_persona = client.personas.get(persona_id)
    assert retrieved_persona.persona_id == persona_id
    assert retrieved_persona.status == "active"
    assert retrieved_persona.first_name is not None
    assert retrieved_persona.last_name is not None
    assert retrieved_persona.email is not None

    # Clean up
    _ = client.personas.delete(persona_id)


def test_persona_delete_operations():
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))

    # Create persona
    persona = client.personas.create()
    persona_id = persona.persona_id

    # Verify persona exists
    retrieved_persona = client.personas.get(persona_id)
    assert retrieved_persona.persona_id == persona_id

    # Delete persona
    delete_response = client.personas.delete(persona_id)
    assert delete_response.status == "success"
    assert delete_response.message == "Persona deleted successfully"

    # Verify persona is deleted
    with pytest.raises(NotteAPIError):
        _ = client.personas.get(persona_id)


def test_persona_without_vault_access():
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))

    with client.Persona() as persona:
        # Create persona without vault
        assert persona.info is not None
        assert persona.info.vault_id is None

        # Try to access vault should raise error
        with pytest.raises(ValueError, match="Persona has no vault"):
            _ = persona.vault


def test_persona_context_manager():
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))

    persona_id = None
    with client.Persona() as persona:
        persona_id = persona.persona_id
        assert persona.info is not None
        assert persona.persona_id == persona_id

        # Test persona operations within context
        emails = persona.emails()
        assert len(emails) == 0

    # Verify persona is deleted after context exit
    with pytest.raises(NotteAPIError):
        _ = client.personas.get(persona_id)


def test_persona_with_existing_id():
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))

    # Create persona first
    created_persona = client.personas.create()
    persona_id = created_persona.persona_id

    # Create persona instance with existing ID
    with client.Persona(persona_id) as persona:
        assert persona.persona_id == persona_id
        assert persona.info is not created_persona

    # Clean up
    _ = client.personas.delete(persona_id)


def test_persona_error_handling():
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))

    # Try to get non-existent persona
    with pytest.raises(NotteAPIError):
        _ = client.personas.get("non-existent-persona-id")

    # Try to delete non-existent persona
    with pytest.raises(NotteAPIError):
        _ = client.personas.delete("non-existent-persona-id")

    # Try to create phone number for non-existent persona
    with pytest.raises(NotteAPIError):
        _ = client.personas.create_number("non-existent-persona-id")

    # Try to delete phone number for non-existent persona
    with pytest.raises(NotteAPIError):
        _ = client.personas.delete_number("non-existent-persona-id")

    # Try to list emails for non-existent persona
    with pytest.raises(NotteAPIError):
        _ = client.personas.list_emails("non-existent-persona-id")

    # Try to list SMS for non-existent persona
    with pytest.raises(NotteAPIError):
        _ = client.personas.list_sms("non-existent-persona-id")
